import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile, status

from app.ContentDetector.scan_router import record_scan
from app.FakeNewsAnalyzer.fast_verifier import FastNewsVerifier
from app.FakeNewsAnalyzer.image_fact_checker import (
    ImagePreprocessingError,
    OcrUnavailableError,
    PhilippineImageFactChecker,
)
from app.FakeNewsAnalyzer.news_verifier import NewsVerifier
from app.Global.cache import cache_key, result_cache
from app.Global.config import settings
from app.Global.dependencies import CurrentPrincipal
from app.Global.providers import gemini_vision_client
from app.Global.rate_limit import limiter
from app.Global.schemas import (
    ImageVerificationResponse,
    NewsVerificationRequest,
    NewsVerificationResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/news", tags=["News verification"])
news_verifier = FastNewsVerifier(
    settings, gemini_client=gemini_vision_client, fallback=NewsVerifier(settings),
)
image_fact_checker = PhilippineImageFactChecker(
    settings,
    vision_client=gemini_vision_client,
    news_verifier=news_verifier,
)
SUPPORTED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/heic",
    "image/heif",
    "image/heic-sequence",
    "image/heif-sequence",
    "image/x-heic",
    "image/x-heif",
    "application/octet-stream",
}


@router.post("/verify", response_model=NewsVerificationResponse)
@limiter.limit(settings.rate_limit_news_verification)
async def verify_news(
    payload: NewsVerificationRequest,
    request: Request,
    response: Response,
    user: CurrentPrincipal,
) -> NewsVerificationResponse:
    async def produce() -> dict:
        return await news_verifier.verify(payload.text)

    try:
        async with asyncio.timeout(settings.news_analysis_deadline_seconds):
            result, cache_hit = await result_cache.get_or_compute(
                cache_key("news", payload.text, version="v10-claim-breakdown"),
                settings.news_result_cache_seconds,
                produce,
                cache_when=lambda value: value.get("status") == "SUCCESS",
            )
    except TimeoutError as exc:
        logger.warning("News verification exceeded its end-to-end deadline")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="News verification timed out; please try again",
        ) from exc
    except Exception as exc:
        logger.exception("News verification request failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="News verification could not be completed",
        ) from exc
    response.headers["X-Cache"] = "HIT" if cache_hit else "MISS"
    validated = NewsVerificationResponse.model_validate(result)
    record_scan(
        user_id=user.user_id,
        filename=payload.text[:54] + ("…" if len(payload.text) > 54 else ""),
        media_type="news",
        confidence_score=float(validated.confidence),
        is_synthetic=(validated.verdict in ("FALSE", "LIKELY_FALSE", "MISLEADING")),
        artifacts=validated.model_dump(),
    )
    return validated


@router.post("/verify-image", response_model=ImageVerificationResponse)
@limiter.limit(settings.rate_limit_news_verification)
async def verify_news_image(
    request: Request,
    response: Response,
    user: CurrentPrincipal,
    image: Annotated[UploadFile, File()],
) -> ImageVerificationResponse:
    if image.content_type not in SUPPORTED_IMAGE_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPEG, PNG, WEBP, GIF, HEIC, and HEIF images are supported",
        )
    try:
        image_bytes = await image.read(settings.image_ocr_max_bytes + 1)
    finally:
        await image.close()
    if len(image_bytes) > settings.image_ocr_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The image exceeds the 10 MB upload limit",
        )
    if not image_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The image is empty")

    async def produce() -> dict:
        return await image_fact_checker.analyze(image_bytes)

    try:
        async with asyncio.timeout(settings.image_analysis_deadline_seconds):
            result, cache_hit = await result_cache.get_or_compute(
                cache_key("image", image_bytes, version="v14-claim-breakdown"),
                settings.image_result_cache_seconds,
                produce,
                cache_when=lambda value: (
                    value.get("status") == "success"
                    and (value.get("verification") or {}).get("status") == "SUCCESS"
                ),
            )
    except TimeoutError as exc:
        logger.warning("Image fact-check exceeded its end-to-end deadline")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Image fact-checking timed out; please try again",
        ) from exc
    except ImagePreprocessingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OcrUnavailableError as exc:
        logger.exception("Image OCR is unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image OCR is temporarily unavailable",
        ) from exc
    except Exception as exc:
        logger.exception("Image fact-check request failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Image fact-checking could not be completed",
        ) from exc
    response.headers["X-Cache"] = "HIT" if cache_hit else "MISS"
    validated = ImageVerificationResponse.model_validate(result)
    record_scan(
        user_id=user.user_id,
        filename=image.filename or "news_image",
        media_type="news",
        confidence_score=float(validated.confidence),
        is_synthetic=(
            validated.classification in ("FAKE", "FALSE")
            or validated.overall_verdict in ("FALSE", "MOSTLY_FALSE")
        ),
        artifacts=validated.model_dump(),
    )
    return validated

