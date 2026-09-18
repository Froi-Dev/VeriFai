import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.ContentDetector.text_detector import (
    TextModelError,
    TextModelUnavailableError,
)
from app.Global.cache import cache_key, result_cache
from app.Global.config import settings
from app.Global.rate_limit import limiter
from app.Global.schemas import (
    NewsVerificationRequest,
    NewsVerificationResponse,
    TextDetectionRequest,
    TextDetectionResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/guest", tags=["Guest"])


@router.post("/detect-text", response_model=TextDetectionResponse)
@limiter.limit(settings.rate_limit_guest_text_detection)
async def guest_detect_text(
    payload: TextDetectionRequest,
    request: Request,
    response: Response,
) -> TextDetectionResponse:
    """Unauthenticated text detection for landing-page visitors.

    Uses the same model and caching as the authenticated endpoint but does
    **not** persist scan results to the database.  Rate-limited by IP.
    """
    # Import the shared detector instance lazily so this module does not
    # create a second TextDetector or interfere with startup ordering.
    from app.ContentDetector.detector import text_detector, text_inference_semaphore

    async def produce() -> dict:
        async with text_inference_semaphore:
            loop = asyncio.get_running_loop()
            t0 = loop.time()
            result = await asyncio.to_thread(text_detector.analyze, payload.text)
            elapsed_ms = round((loop.time() - t0) * 1000.0, 1)
            data = result.__dict__.copy()
            data["inference_time_ms"] = elapsed_ms
            data["signals"] = list(data.get("signals", ()))
            return data

    try:
        async with asyncio.timeout(settings.text_analysis_deadline_seconds):
            result, cache_hit = await result_cache.get_or_compute(
                cache_key(
                    "text",
                    f"{settings.text_model_path.resolve()}\0{payload.text}",
                    version="v6",
                ),
                settings.text_result_cache_seconds,
                produce,
            )
    except TimeoutError as exc:
        logger.warning("Guest text analysis exceeded its end-to-end deadline")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Text analysis timed out; please try again",
        ) from exc
    except TextModelUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Text detection is temporarily unavailable",
        ) from exc
    except TextModelError as exc:
        logger.exception("Guest text detection request failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Text analysis could not be completed",
        ) from exc

    response.headers["X-Cache"] = "HIT" if cache_hit else "MISS"
    result_data = dict(result)
    result_data["cached"] = cache_hit
    return TextDetectionResponse(**result_data)


@router.post("/verify-news", response_model=NewsVerificationResponse)
@limiter.limit(settings.rate_limit_news_verification)
async def guest_verify_news(
    payload: NewsVerificationRequest,
    request: Request,
    response: Response,
) -> NewsVerificationResponse:
    """Unauthenticated news verification for extension users and landing visitors."""
    from app.FakeNewsAnalyzer.news import news_verifier

    async def produce() -> dict:
        return await news_verifier.verify(payload.text)

    try:
        async with asyncio.timeout(settings.news_analysis_deadline_seconds):
            result, cache_hit = await result_cache.get_or_compute(
                cache_key("news", payload.text, version="v8"),
                settings.news_result_cache_seconds,
                produce,
                cache_when=lambda value: value.get("status") == "SUCCESS",
            )
    except TimeoutError as exc:
        logger.warning("Guest news verification exceeded its end-to-end deadline")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="News verification timed out; please try again",
        ) from exc
    except Exception as exc:
        logger.exception("Guest news verification request failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="News verification could not be completed",
        ) from exc

    response.headers["X-Cache"] = "HIT" if cache_hit else "MISS"
    return NewsVerificationResponse.model_validate(result)
