"""Request and response security middleware."""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "0",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-site",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if request.url.scheme == "https" or settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload"
            )
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > settings.max_request_bytes:
                    return JSONResponse(status_code=413, content={"detail": "Request too large"})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid request"})
        if request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()
            if len(body) > settings.max_request_bytes:
                return JSONResponse(status_code=413, content={"detail": "Request too large"})
        return await call_next(request)


class ExposureProtectionMiddleware(BaseHTTPMiddleware):
    """Never serve repository metadata or environment files through the API host."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path_parts = {part.casefold() for part in request.url.path.split("/") if part}
        if ".git" in path_parts or any(part.startswith(".env") for part in path_parts):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        return await call_next(request)


class OriginProtectionMiddleware(BaseHTTPMiddleware):
    """Reject browser cross-site mutations, including login CSRF."""

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        origin = request.headers.get("origin")
        if (
            request.method not in self.SAFE_METHODS
            and origin
            and origin.rstrip("/") not in settings.allowed_origins
        ):
            return JSONResponse(status_code=403, content={"detail": "Origin not allowed"})
        return await call_next(request)
