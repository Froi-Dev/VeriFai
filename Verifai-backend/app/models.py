from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "public"}

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column("password", Text, nullable=False)
    email_verified: Mapped[bool | None] = mapped_column(Boolean, default=False)
    mfa_enabled: Mapped[bool | None] = mapped_column(Boolean, default=False)
    failed_login_attempts: Mapped[int | None] = mapped_column(Integer, default=0)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SessionRecord(Base):
    __tablename__ = "session_records"
    __table_args__ = {"schema": "public"}

    token: Mapped[str] = mapped_column(String(255), primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(20), nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("public.users.user_id"), nullable=True
    )
    email: Mapped[str | None] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = {"schema": "public"}

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("public.users.user_id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String)
    msg: Mapped[str | None] = mapped_column(String)
    type: Mapped[str | None] = mapped_column(String)
    timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

