from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request as StarletteRequest

from app.ContentDetector import guest_quota as service
from app.ContentDetector.guest_router import router


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'guests.db'}", connect_args={"timeout": 30})
    tables = [
        service.GuestIdentity.__table__,
        service.GuestSession.__table__,
        service.GuestUsage.__table__,
    ]
    service.Base.metadata.create_all(engine, tables=tables)
    monkeypatch.setattr(service, "SessionLocal", sessionmaker(engine, expire_on_commit=False))
    yield engine
    engine.dispose()


def request(token=None, ip="192.0.2.1", ua="Test Chrome"):
    headers = [(b"user-agent", ua.encode())]
    if token:
        headers.append((b"x-guest-token", token.encode()))
    return StarletteRequest({"type": "http", "client": (ip, 123), "headers": headers})


def test_all_limits_and_independent_scanners(database):
    token = service.issue(request(), "canvas")
    for kind, limit in service.LIMITS.items():
        for _ in range(limit):
            service.quota(request(token), kind)
        with pytest.raises(HTTPException) as error:
            service.quota(request(token), kind)
        assert error.value.status_code == 403
        assert error.value.detail["code"] == "QUOTA_EXCEEDED"


def test_clearing_cookies_and_changing_canvas_does_not_reset(database):
    token = service.issue(request(), "canvas-a")
    service.quota(request(token), "news")
    replacement = service.issue(request(), "canvas-b")
    assert replacement != token
    assert service.quota(request(replacement))["quotas"]["news"]["remaining"] == 0


def test_shared_extension_token_and_network_change(database):
    token = service.issue(request(), "canvas")
    service.quota(request(token), "news")
    assert service.quota(request(token, ip="192.0.2.2"))["quotas"]["news"]["remaining"] == 0
    fresh = service.issue(request(ip="192.0.2.3"), "canvas")
    with pytest.raises(HTTPException):
        service.quota(request(fresh), "news")  # Current identity is also enforced.


def test_rolling_window_and_session_expiry(database):
    with patch.object(service.time, "time", return_value=100000):
        token = service.issue(request(), "canvas")
        service.quota(request(token), "news")
    with patch.object(service.time, "time", return_value=186401):
        assert service.quota(request(token))["quotas"]["news"]["remaining"] == 1
    with patch.object(service.time, "time", return_value=100000 + service.TTL + 1):
        with pytest.raises(HTTPException) as error:
            service.quota(request(token))
        assert error.value.status_code == 401


def test_atomic_parallel_reservations(database):
    token = service.issue(request(), "canvas")

    def consume(_):
        try:
            service.quota(request(token), "text")
            return 200
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(consume, range(12)))
    assert statuses.count(200) == 3
    assert statuses.count(403) == 9


def test_consent_cookie_and_route_guards(database):
    app = FastAPI()
    app.include_router(router)

    @app.post("/scan", dependencies=[Depends(service.require_quota("news"))])
    def scan():
        return {"ok": True}

    with TestClient(app) as client:
        assert client.post("/scan").status_code == 401
        payload = {
            "essential": True,
            "quota_tracking": True,
            "device_terms": False,
            "fingerprint": "canvas",
        }
        assert client.post("/guest/consent", json=payload).status_code == 422
        payload["device_terms"] = True
        response = client.post("/guest/consent", json=payload)
        assert response.status_code == 200
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "Max-Age=2592000" in response.headers["set-cookie"]
        assert client.post("/scan").status_code == 200
        assert client.post("/scan").status_code == 403
        client.cookies.clear()
        assert (
            client.get(
                "/guest/quota", headers={"X-Guest-Token": response.json()["guest_token"]}
            ).json()["quotas"]["news"]["remaining"]
            == 0
        )
        assert client.get("/guest/quota", headers={"X-Guest-Token": "forged"}).status_code == 401


@pytest.mark.parametrize(
    "path,kind",
    [
        ("/guest/detect-text", "text"),
        ("/guest/detect-image", "image"),
        ("/guest/verify-news", "news"),
    ],
)
def test_actual_scanners_block_before_inference(database, path, kind):
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        token = client.post(
            "/guest/consent",
            json={
                "essential": True,
                "quota_tracking": True,
                "device_terms": True,
                "fingerprint": "canvas",
            },
        ).json()["guest_token"]
        req = request(token, ip="testclient", ua="testclient")
        for _ in range(service.LIMITS[kind]):
            service.quota(req, kind)
        response = (
            client.post(path, json={"text": "A long enough sample text for testing."})
            if kind != "image"
            else client.post(path, files={"image": ("image.png", b"image", "image/png")})
        )
        assert response.status_code == 403
