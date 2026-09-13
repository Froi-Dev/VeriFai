import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import delete, select

from app.Auth.models import ScanResult
from app.Global.config import settings
from app.Global.db import SessionLocal
from app.Global.dependencies import CurrentPrincipal
from app.Global.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scans", tags=["Scans"])


def record_scan(
    user_id: int,
    filename: str,
    media_type: str,
    confidence_score: float,
    is_synthetic: bool | None = None,
    artifacts: Any = None,
) -> ScanResult | None:
    """Safely persist a scan result to the database without throwing exceptions."""
    try:
        with SessionLocal() as db:
            scan = ScanResult(
                user_id=user_id,
                filename=filename,
                media_type=media_type,
                confidence_score=confidence_score,
                is_synthetic=is_synthetic,
                artifacts=artifacts,
            )
            db.add(scan)
            db.commit()
            db.refresh(scan)
            return scan
    except Exception:
        logger.exception("Failed to persist scan result for user %s", user_id)
        return None


class DayScanCount(BaseModel):
    date: str
    label: str
    count: int
    isToday: bool


class ScanStatsResponse(BaseModel):
    total: int
    textCount: int
    mediaCount: int
    newsCount: int
    weeklyTotal: int
    weeklyScans: list[DayScanCount]


class ScanItemResponse(BaseModel):
    id: str
    db_id: int
    kind: Literal["text", "media", "news"]
    name: str
    createdAt: datetime
    classification: str
    confidence: int
    confidenceLabel: str | None = None
    aiConfidence: int | None = None
    humanConfidence: int | None = None
    chunksAnalyzed: int | None = None
    scoreIsCalibrated: bool | None = None
    scoreInterpretation: str | None = None
    artifacts: Any = None


class ScanListResponse(BaseModel):
    items: list[ScanItemResponse]
    stats: ScanStatsResponse


def _build_scan_item(scan: ScanResult) -> ScanItemResponse:
    raw_kind = (scan.media_type or "text").lower()
    if raw_kind in ("image", "media", "photo"):
        kind: Literal["text", "media", "news"] = "media"
    elif raw_kind in ("news", "fakenews"):
        kind = "news"
    else:
        kind = "text"

    artifacts = scan.artifacts if isinstance(scan.artifacts, dict) else {}
    confidence = int(round(scan.confidence_score))

    classification = (
        artifacts.get("classification")
        or artifacts.get("overall_verdict")
        or artifacts.get("verdict")
    )
    if not classification or not isinstance(classification, str):
        if scan.is_synthetic is True:
            classification = (
                "Fake news" if kind == "news" else "Likely AI-generated"
            )
        elif scan.is_synthetic is False:
            classification = (
                "Real news" if kind == "news" else "Likely human-written"
            )
        else:
            classification = "Review recommended"

    confidence_label = (
        artifacts.get("confidenceLabel")
        or artifacts.get("overall_confidence")
        or ("HIGH" if confidence >= 80 else "MEDIUM" if confidence >= 55 else "LOW")
    )

    ai_conf = artifacts.get("ai_probability")
    if ai_conf is not None:
        ai_conf = int(round(ai_conf * 100)) if ai_conf <= 1.0 else int(round(ai_conf))

    human_conf = artifacts.get("human_probability") or artifacts.get("authentic_probability")
    if human_conf is not None:
        human_conf = int(round(human_conf * 100)) if human_conf <= 1.0 else int(round(human_conf))

    return ScanItemResponse(
        id=f"VF-{scan.id:04d}",
        db_id=scan.id,
        kind=kind,
        name=scan.filename,
        createdAt=scan.created_at or datetime.now(timezone.utc),
        classification=classification,
        confidence=confidence,
        confidenceLabel=str(confidence_label) if confidence_label else None,
        aiConfidence=ai_conf,
        humanConfidence=human_conf,
        chunksAnalyzed=artifacts.get("chunks_analyzed"),
        scoreIsCalibrated=artifacts.get("score_is_calibrated"),
        scoreInterpretation=artifacts.get("score_interpretation"),
        artifacts=scan.artifacts,
    )


def _compute_stats(user_id: int) -> ScanStatsResponse:
    with SessionLocal() as db:
        scans = db.scalars(
            select(ScanResult).where(ScanResult.user_id == user_id)
        ).all()

    total = len(scans)
    text_count = 0
    media_count = 0
    news_count = 0

    for s in scans:
        k = (s.media_type or "text").lower()
        if k in ("image", "media", "photo"):
            media_count += 1
        elif k in ("news", "fakenews"):
            news_count += 1
        else:
            text_count += 1

    # Weekly scans for the last 7 days ending today
    now_utc = datetime.now(timezone.utc)
    today_date = now_utc.date()
    daily_counts: dict[str, int] = {}
    day_labels: dict[str, str] = {}
    day_is_today: dict[str, bool] = {}

    for i in range(7):
        target_date = today_date - timedelta(days=(6 - i))
        date_str = target_date.isoformat()
        daily_counts[date_str] = 0
        day_labels[date_str] = target_date.strftime("%a")
        day_is_today[date_str] = (i == 6)

    for s in scans:
        if s.created_at:
            s_date = s.created_at.astimezone(timezone.utc).date().isoformat()
            if s_date in daily_counts:
                daily_counts[s_date] += 1

    weekly_scans = [
        DayScanCount(
            date=d_str,
            label=day_labels[d_str],
            count=daily_counts[d_str],
            isToday=day_is_today[d_str],
        )
        for d_str in daily_counts
    ]
    weekly_total = sum(d.count for d in weekly_scans)

    return ScanStatsResponse(
        total=total,
        textCount=text_count,
        mediaCount=media_count,
        newsCount=news_count,
        weeklyTotal=weekly_total,
        weeklyScans=weekly_scans,
    )


@router.get("", response_model=ScanListResponse)
@limiter.limit(settings.rate_limit_me)
def get_user_scans(
    request: Request,
    response: Response,
    user: CurrentPrincipal,
    limit: int = 50,
) -> ScanListResponse:
    """Retrieve the user's scan history and aggregated stats."""
    with SessionLocal() as db:
        scans = db.scalars(
            select(ScanResult)
            .where(ScanResult.user_id == user.user_id)
            .order_by(ScanResult.created_at.desc(), ScanResult.id.desc())
            .limit(min(max(1, limit), 100))
        ).all()

    items = [_build_scan_item(s) for s in scans]
    stats = _compute_stats(user.user_id)
    return ScanListResponse(items=items, stats=stats)


@router.get("/stats", response_model=ScanStatsResponse)
@limiter.limit(settings.rate_limit_me)
def get_user_scan_stats(
    request: Request,
    response: Response,
    user: CurrentPrincipal,
) -> ScanStatsResponse:
    """Retrieve aggregated stats for dashboard counters and graph."""
    return _compute_stats(user.user_id)


@router.delete("/{scan_id}")
@limiter.limit(settings.rate_limit_me)
def delete_user_scan(
    scan_id: int,
    request: Request,
    response: Response,
    user: CurrentPrincipal,
) -> dict[str, Any]:
    """Delete a single scan owned by the current user."""
    with SessionLocal() as db:
        result = db.execute(
            delete(ScanResult).where(
                ScanResult.id == scan_id, ScanResult.user_id == user.user_id
            )
        )
        db.commit()
        if result.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scan result not found",
            )
    return {"message": "Scan deleted successfully", "id": scan_id}


@router.delete("")
@limiter.limit(settings.rate_limit_me)
def clear_user_scans(
    request: Request,
    response: Response,
    user: CurrentPrincipal,
) -> dict[str, Any]:
    """Clear all scan history for the current user."""
    with SessionLocal() as db:
        db.execute(
            delete(ScanResult).where(ScanResult.user_id == user.user_id)
        )
        db.commit()
    return {"message": "Scan history cleared successfully"}
