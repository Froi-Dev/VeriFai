from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.Auth.models import ScanResult, User
from app.Global.db import SessionLocal
from app.ContentDetector.scan_router import (
    _build_scan_item,
    _compute_stats,
    record_scan,
)
from app.Global.dependencies import get_current_principal, UserPrincipal
from app.main import app


def test_build_scan_item_text():
    scan = ScanResult(
        id=12,
        user_id=1,
        filename="Breaking news announcement text",
        media_type="text",
        confidence_score=92.4,
        is_synthetic=True,
        artifacts={"ai_probability": 0.92, "human_probability": 0.08, "chunks_analyzed": 1},
        created_at=datetime.now(timezone.utc),
    )
    item = _build_scan_item(scan)
    assert item.id == "VF-0012"
    assert item.kind == "text"
    assert item.confidence == 92
    assert item.aiConfidence == 92
    assert item.humanConfidence == 8
    assert item.classification == "Likely AI-generated"


def test_build_scan_item_media():
    scan = ScanResult(
        id=34,
        user_id=1,
        filename="photo.jpg",
        media_type="media",
        confidence_score=85.0,
        is_synthetic=False,
        artifacts={"classification": "Likely authentic", "authentic_probability": 85},
        created_at=datetime.now(timezone.utc),
    )
    item = _build_scan_item(scan)
    assert item.id == "VF-0034"
    assert item.kind == "media"
    assert item.confidence == 85
    assert item.classification == "Likely authentic"


def test_record_and_get_user_scans():
    with SessionLocal() as db:
        user = User(
            username="scan_test_user",
            email="scan_test_user@example.com",
            password_hash="dummy_hash_for_testing",
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.user_id

    try:
        # Record a test scan
        scan = record_scan(
            user_id=user_id,
            filename="Test text scan sample",
            media_type="text",
            confidence_score=78.5,
            is_synthetic=True,
            artifacts={"classification": "Likely AI-generated"},
        )
        assert scan is not None
        assert scan.id > 0

        stats = _compute_stats(user_id)
        assert stats.total >= 1
        assert stats.textCount >= 1
        assert len(stats.weeklyScans) == 7
        today_slot = [s for s in stats.weeklyScans if s.isToday]
        assert len(today_slot) == 1
        assert today_slot[0].count >= 1

        # Test via API endpoint using dependency override
        client = TestClient(app)
        app.dependency_overrides[get_current_principal] = lambda: UserPrincipal(user_id=user_id, role="user")
        try:
            response = client.get("/api/v1/scans")
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert "stats" in data
            assert data["stats"]["total"] >= 1
            assert any(item["name"] == "Test text scan sample" for item in data["items"])

            # Test single item deletion
            delete_resp = client.delete(f"/api/v1/scans/{scan.id}")
            assert delete_resp.status_code == 200

            # Test clear all scans
            clear_resp = client.delete("/api/v1/scans")
            assert clear_resp.status_code == 200
            cleared_stats = client.get("/api/v1/scans/stats").json()
            assert cleared_stats["total"] == 0
        finally:
            app.dependency_overrides.clear()
    finally:
        with SessionLocal() as db:
            from sqlalchemy import delete
            db.execute(delete(ScanResult).where(ScanResult.user_id == user_id))
            db.execute(delete(User).where(User.user_id == user_id))
            db.commit()

