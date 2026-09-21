"""Request and response security middleware."""

import re
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.Global.config import settings

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

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


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        supplied = request.headers.get("x-request-id", "")
        request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class RequestTooLargeError(Exception):
    pass


class RequestSizeLimitMiddleware:
    """Count ASGI body chunks without reading or caching the complete request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > settings.max_request_bytes:
                    response = JSONResponse(
                        status_code=413, content={"detail": "Request too large"}
                    )
                    await response(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse(
                    status_code=400, content={"detail": "Invalid request"}
                )
                await response(scope, receive, send)
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > settings.max_request_bytes:
                    raise RequestTooLargeError
            return message

        await self.app(scope, limited_receive, send)


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
        is_allowed_tunnel = bool(
            origin
            and (
                origin.endswith(".trycloudflare.com")
                or origin.endswith(".loca.lt")
            )
        )
        if (
            request.method not in self.SAFE_METHODS
            and origin
            and origin.rstrip("/") not in settings.allowed_origins
            and not origin.startswith("chrome-extension://")
            and not is_allowed_tunnel
        ):
            return JSONResponse(status_code=403, content={"detail": "Origin not allowed"})
        return await call_next(request)
