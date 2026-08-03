"""Rate limiting configuration using slowapi.

Uses an in-memory store by default. For multi-worker / multi-instance
deployments, switch to a Redis-backed store by installing ``redis``
and changing the ``storage_uri`` parameter.
"""

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

limiter = Limiter(key_func=get_remote_address)


async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """Return a structured JSON 429 response with a Retry-After header."""
    retry_after = exc.detail.split("per")[-1].strip() if "per" in exc.detail else "60"
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Too many requests. Please slow down.",
            "retry_after": retry_after,
        },
        headers={"Retry-After": retry_after},
    )
