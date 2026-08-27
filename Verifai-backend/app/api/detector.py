import logging

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.dependencies import CurrentUser
from app.core.config import settings
from app.core.rate_limit import limiter
from app.schemas import TextDetectionRequest, TextDetectionResponse
from app.services.text_detector import (
    TextDetector,
    TextModelError,
    TextModelUnavailableError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/detector", tags=["Detection"])

text_detector = TextDetector(
    settings.text_model_path,
    device=settings.text_model_device,
    ai_label_id=settings.text_model_ai_label_id,
    max_length=settings.text_model_max_length,
    stride=settings.text_model_stride,
    batch_size=settings.text_model_batch_size,
    review_threshold=settings.text_model_review_threshold,
)


@router.post("/text", response_model=TextDetectionResponse)
@limiter.limit(settings.rate_limit_text_detection)
def detect_text(
    payload: TextDetectionRequest,
    request: Request,
    response: Response,
    user: CurrentUser,
) -> TextDetectionResponse:
    del user
    try:
        result = text_detector.analyze(payload.text)
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
    return TextDetectionResponse(**result.__dict__)
