import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.Auth.admin import router as admin_router
from app.Auth.auth_router import router as auth_router
from app.ContentDetector.detector import router as detector_router
from app.ContentDetector.detector import text_detector
from app.ContentDetector.guest_router import router as guest_router
from app.ContentDetector.scan_router import router as scan_router
from app.FakeNewsAnalyzer.news import image_fact_checker, news_verifier
from app.FakeNewsAnalyzer.news import router as news_router
from app.Global.cache import result_cache
from app.Global.config import settings
from app.Global.db import Base, engine
from app.Global.middleware import (
    ExposureProtectionMiddleware,
    OriginProtectionMiddleware,
    RequestIdMiddleware,
    RequestSizeLimitMiddleware,
    RequestTooLargeError,
    SecurityHeadersMiddleware,
)
from app.Global.rate_limit import limiter, rate_limit_exceeded_handler

# VeriFai API Main Application
# Settings updated with gemini-3.5-flash-lite adjudicator and refreshed Serper config
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Ensure database schema is initialized on first boot in cloud environments
    try:
        import app.Auth.models  # noqa: F401
        import app.ContentDetector.guest_quota  # noqa: F401
        Base.metadata.create_all(bind=engine)
        logger.info("Database schema verified/created successfully")
    except Exception:
        logger.exception("Failed to initialize database tables on startup")


    if settings.text_analyzer_backend == "roberta" and settings.text_model_warmup:
        try:
            await asyncio.to_thread(text_detector.warmup)
        except Exception:
            # Keep health and non-detector routes available; detector requests
            # return their existing 503 until deployment fixes the model.
            logger.exception("Text detector startup warmup failed")
    if settings.image_ocr_warmup:
        try:
            await asyncio.to_thread(image_fact_checker.warmup)
        except Exception:
            logger.exception("Image OCR startup warmup failed")
    try:
        yield
    finally:
        await image_fact_checker.aclose(close_news_verifier=False)
        await news_verifier.aclose()
        await result_cache.close()
        engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="1.1.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "field": ".".join(str(part) for part in error["loc"] if part != "body"),
                "message": error["msg"],
            }
        )
    return JSONResponse(
        status_code=422,
        content={
            "detail": errors,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "request_id": getattr(request.state, "request_id", None),
        },
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.exception(
        "Unhandled API error on %s %s request_id=%s: %s",
        request.method,
        request.url.path,
        request_id,
        exc,
    )
    headers: dict[str, str] = {}
    origin = request.headers.get("origin")
    if origin and (
        origin.rstrip("/") in settings.allowed_origins
        or origin.endswith(".workers.dev")
        or origin.endswith(".pages.dev")
    ):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred", "request_id": request_id},
        headers=headers,
    )



@app.exception_handler(RequestTooLargeError)
async def request_too_large_handler(request: Request, exc: RequestTooLargeError):
    del request, exc
    return JSONResponse(status_code=413, content={"detail": "Request too large"})


# Middleware execution in Starlette/FastAPI:
# Middlewares run in REVERSE order of addition (outermost added LAST).
# CORSMiddleware must be added last so it handles OPTIONS preflights first
# before TrustedHostMiddleware or HTTPSRedirectMiddleware evaluate the request.
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(ExposureProtectionMiddleware)
app.add_middleware(OriginProtectionMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
if settings.is_production:
    app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=r"^(chrome-extension://.*|https://.*\.workers\.dev|https://.*\.pages\.dev|https://.*\.trycloudflare\.com|https://.*\.loca\.lt)$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Cache"],
    max_age=600,
)


app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(admin_router, prefix=settings.api_v1_prefix)
app.include_router(detector_router, prefix=settings.api_v1_prefix)
app.include_router(news_router, prefix=settings.api_v1_prefix)
app.include_router(scan_router, prefix=settings.api_v1_prefix)
app.include_router(guest_router, prefix=settings.api_v1_prefix)


def _readiness_response() -> JSONResponse:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("Database readiness check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "disconnected"},
        )
    return JSONResponse(content={"status": "ok", "database": "connected"})


@app.get("/live", tags=["Health"])
def liveness(request: Request, response: Response) -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health", tags=["Health"])
@limiter.limit(settings.rate_limit_health)
def health(request: Request, response: Response) -> Response:
    return _readiness_response()


@app.get(f"{settings.api_v1_prefix}/health", tags=["Health"])
@limiter.limit(settings.rate_limit_health)
def api_health(request: Request, response: Response) -> Response:
    return _readiness_response()
