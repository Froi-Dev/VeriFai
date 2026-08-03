from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.core.config import settings
from app.core.middleware import SecurityHeadersMiddleware
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.db import engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    yield
    engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    # Disable interactive docs in production to hide the API schema
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)

# ---------------------------------------------------------------------------
# State & exception handlers
# ---------------------------------------------------------------------------
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]

# ---------------------------------------------------------------------------
# Middleware (applied bottom-to-top, so security headers wrap everything)
# ---------------------------------------------------------------------------
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.trusted_host_list,
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth_router, prefix=settings.api_v1_prefix)


# ---------------------------------------------------------------------------
# Health-check endpoints
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
@limiter.limit(settings.rate_limit_health)
def health(request: Request) -> dict[str, str]:
    return {"status": "ok"}


@app.get(f"{settings.api_v1_prefix}/health", tags=["Health"])
@limiter.limit(settings.rate_limit_health)
def api_health(request: Request) -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
