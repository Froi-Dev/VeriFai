"""Durable rolling quotas. All reservations commit before inference, including cache hits."""

import hashlib
import hmac
import time
import uuid

from fastapi import HTTPException, Request
from sqlalchemy import Float, ForeignKey, Integer, String, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from app.Global.config import settings
from app.Global.db import Base, SessionLocal

LIMITS = {"text": 3, "image": 2, "news": 1}
COOKIE = "verifai_guest"
TTL = 30 * 86400


class GuestIdentity(Base):
    __tablename__ = "guest_identities"
    identity_hash: Mapped[str] = mapped_column(String(64), primary_key=True)


class GuestSession(Base):
    __tablename__ = "guest_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    identity_hash: Mapped[str] = mapped_column(ForeignKey("guest_identities.identity_hash"))
    fingerprint_hash: Mapped[str] = mapped_column(String(64))
    consent_version: Mapped[str] = mapped_column(String(20), default="2026-09-v1")
    created_at: Mapped[float] = mapped_column(Float)
    expires_at: Mapped[float] = mapped_column(Float)


class GuestUsage(Base):
    __tablename__ = "guest_usage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    identity_hash: Mapped[str] = mapped_column(
        ForeignKey("guest_identities.identity_hash"), index=True
    )
    kind: Mapped[str] = mapped_column(String(10))
    used_at: Mapped[float] = mapped_column(Float, index=True)


def digest(value: str) -> str:
    return hmac.new(
        settings.jwt_secret.get_secret_value().encode(),
        ("guest:v1:" + value).encode(),
        hashlib.sha256,
    ).hexdigest()


def identity(request: Request) -> str:
    # Never trust arbitrary X-Forwarded-For. Configure the server's trusted proxy list.
    address = request.client.host if request.client else "unknown"
    return digest(f"{address}\0{request.headers.get('user-agent', '')}")


def ensure_identity(key: str) -> None:
    with SessionLocal() as db:
        if db.get(GuestIdentity, key) is not None:
            return
        try:
            db.add(GuestIdentity(identity_hash=key))
            db.commit()
        except IntegrityError:
            db.rollback()  # Concurrent issuance shares the same identity row.


def issue(request: Request, fingerprint: str) -> str:
    key = identity(request)
    ensure_identity(key)
    token = str(uuid.uuid4())
    now = time.time()
    with SessionLocal() as db:
        db.add(
            GuestSession(
                token_hash=digest(token),
                identity_hash=key,
                fingerprint_hash=digest(fingerprint),
                created_at=now,
                expires_at=now + TTL,
            )
        )
        db.commit()
    return token


def quota(request: Request, consume: str | None = None) -> dict:
    token = request.headers.get("x-guest-token") or request.cookies.get(COOKIE)
    if not token or len(token) > 100:
        raise HTTPException(401, "Guest consent required")
    now = time.time()
    current = identity(request)
    with SessionLocal() as db:
        session = db.get(GuestSession, digest(token))
        if session is None or session.expires_at <= now:
            raise HTTPException(401, "Guest session expired; accept consent again")
        owner = session.identity_hash
    ensure_identity(current)
    with SessionLocal() as db:
        keys = sorted({owner, current})
        # UPDATE takes a database write lock (also works in SQLite tests). Consistent
        # ordering avoids deadlocks across tokens and networks; no process-local counters.
        for key in keys:
            db.execute(
                update(GuestIdentity)
                .where(GuestIdentity.identity_hash == key)
                .values(identity_hash=key)
            )
        meters = {}
        for kind, limit in LIMITS.items():
            counts = [
                db.scalar(
                    select(func.count())
                    .select_from(GuestUsage)
                    .where(
                        GuestUsage.identity_hash == key,
                        GuestUsage.kind == kind,
                        GuestUsage.used_at > now - 86400,
                    )
                )
                or 0
                for key in keys
            ]
            used = max(counts)
            meters[kind] = {
                "limit": limit,
                "used": min(used, limit),
                "remaining": max(0, limit - used),
            }
        if consume:
            if meters[consume]["remaining"] == 0:
                raise HTTPException(
                    403,
                    {
                        "code": "QUOTA_EXCEEDED",
                        "message": "Quota Exceeded",
                        "scanner": consume,
                        "quotas": meters,
                    },
                )
            for key in keys:
                db.add(GuestUsage(identity_hash=key, kind=consume, used_at=now))
            meters[consume]["used"] += 1
            meters[consume]["remaining"] -= 1
        db.commit()
    return {"quotas": meters, "window_hours": 24, "expires_at": session.expires_at}


def require_quota(kind: str):
    def dependency(request: Request):
        return quota(request, consume=kind)

    return dependency
