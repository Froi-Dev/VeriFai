import asyncio
import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile, status

from app.ContentDetector.text_detector import (
    TextDetector,
    TextModelError,
    TextModelUnavailableError,
)
from app.FakeNewsAnalyzer.image_fact_checker import (
    GeminiImageDetector,
    ImagePreprocessingError,
    OcrUnavailableError,
    prepare_image,
)
from app.ContentDetector.scan_router import record_scan
from app.Global.cache import cache_key, result_cache
from app.Global.config import settings
from app.Global.dependencies import CurrentPrincipal
from app.Global.providers import gemini_vision_client
from app.Global.rate_limit import limiter
from app.Global.schemas import ImageDetectionResponse, TextDetectionRequest, TextDetectionResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/detector", tags=["Detection"])

text_detector = TextDetector(
    settings.text_model_path,
    device=settings.text_model_device,
    ai_label_id=settings.text_model_ai_label_id,
    max_length=settings.text_model_max_length,
    stride=settings.text_model_stride,
    batch_size=settings.text_model_batch_size,
    max_concurrent_inferences=settings.text_model_max_concurrent_inferences,
    review_threshold=settings.text_model_review_threshold,
)
image_detector = GeminiImageDetector(gemini_vision_client)
text_inference_semaphore = asyncio.Semaphore(settings.text_model_max_concurrent_inferences)
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


@router.post("/text", response_model=TextDetectionResponse)
@limiter.limit(settings.rate_limit_text_detection)
async def detect_text(
    payload: TextDetectionRequest,
    request: Request,
    response: Response,
    user: CurrentPrincipal,
) -> TextDetectionResponse:
    async def produce() -> dict:
        async with text_inference_semaphore:
            result = await asyncio.to_thread(text_detector.analyze, payload.text)
            return result.__dict__

    try:
        async with asyncio.timeout(settings.text_analysis_deadline_seconds):
            result, cache_hit = await result_cache.get_or_compute(
                cache_key(
                    "text",
                    f"{settings.text_model_path.resolve()}\0{payload.text}",
                    version="v5",
                ),
                settings.text_result_cache_seconds,
                produce,
            )
    except TimeoutError as exc:
        logger.warning("Text analysis exceeded its end-to-end deadline")
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
        logger.exception("Text detection request failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Text analysis could not be completed",
        ) from exc
    response.headers["X-Cache"] = "HIT" if cache_hit else "MISS"
    validated = TextDetectionResponse(**result)
    record_scan(
        user_id=user.user_id,
        filename=payload.text[:54] + ("…" if len(payload.text) > 54 else ""),
        media_type="text",
        confidence_score=round(validated.confidence * 100, 2),
        is_synthetic=(validated.classification == "Likely AI-generated"),
        artifacts=validated.model_dump(),
    )
    return validated


@router.post("/image", response_model=ImageDetectionResponse)
@limiter.limit(settings.rate_limit_image_detection)
async def detect_image(
    request: Request,
    response: Response,
    user: CurrentPrincipal,
    image: Annotated[UploadFile, File()],
) -> ImageDetectionResponse:
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

    if not image_detector.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image AI detection is not configured",
        )

    async def produce() -> dict:
        prepared = await asyncio.to_thread(
            prepare_image,
            image_bytes,
            max_pixels=settings.image_ocr_max_pixels,
            max_source_pixels=settings.image_ocr_max_source_pixels,
        )
        return await image_detector.analyze(prepared)

    try:
        async with asyncio.timeout(settings.image_analysis_deadline_seconds):
            result, cache_hit = await result_cache.get_or_compute(
                cache_key("image-ai", image_bytes, version="v1"),
                settings.image_result_cache_seconds,
                produce,
            )
    except TimeoutError as exc:
        logger.warning("Image AI detection exceeded its end-to-end deadline")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Image analysis timed out; please try again",
        ) from exc
    except ImagePreprocessingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except (OcrUnavailableError, httpx.HTTPError) as exc:
        logger.warning("Gemini image analysis is temporarily unavailable", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image AI detection is temporarily unavailable; please try again",
        ) from exc
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Gemini returned an invalid image analysis", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The image analysis provider returned an invalid result",
        ) from exc
    response.headers["X-Cache"] = "HIT" if cache_hit else "MISS"
    validated = ImageDetectionResponse.model_validate(result)
    record_scan(
        user_id=user.user_id,
        filename=image.filename or "image_scan",
        media_type="media",
        confidence_score=float(validated.confidence),
        is_synthetic=(validated.classification in ("Likely AI-generated", "Manipulation suspected")),
        artifacts=validated.model_dump(),
    )
    return validated
