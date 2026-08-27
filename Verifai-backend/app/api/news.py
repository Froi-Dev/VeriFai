import logging

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.dependencies import CurrentUser
from app.core.config import settings
from app.core.rate_limit import limiter
from app.schemas import NewsVerificationRequest, NewsVerificationResponse
from app.services.news_verifier import NewsVerifier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/news", tags=["News verification"])
news_verifier = NewsVerifier(settings)


@router.post("/verify", response_model=NewsVerificationResponse)
@limiter.limit(settings.rate_limit_news_verification)
async def verify_news(
    payload: NewsVerificationRequest,
    request: Request,
    response: Response,
    user: CurrentUser,
) -> NewsVerificationResponse:
    del user
    try:
        result = await news_verifier.verify(payload.text)
    except Exception as exc:
        logger.exception("News verification request failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="News verification could not be completed",
        ) from exc
    return NewsVerificationResponse.model_validate(result)
