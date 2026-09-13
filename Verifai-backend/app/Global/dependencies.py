from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.Auth.auth_service import get_active_session_user
from app.Auth.models import User
from app.Global.config import settings
from app.Global.db import SessionLocal, get_db
from app.Global.security import TokenPayload, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)
DatabaseSession = Annotated[Session, Depends(get_db)]


def get_token_payload(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    access_cookie: Annotated[str | None, Cookie(alias=settings.access_cookie_name)] = None,
) -> TokenPayload:
    token = access_cookie
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if not token:
        raise _unauthorized()
    try:
        return decode_access_token(token)
    except ValueError as exc:
        raise _unauthorized() from exc


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


TokenData = Annotated[TokenPayload, Depends(get_token_payload)]


def get_current_user(db: DatabaseSession, payload: TokenData) -> User:
    user = get_active_session_user(
        db, payload.user_id, payload.session_id, payload.generation
    )
    if user is None:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass(frozen=True, slots=True)
class UserPrincipal:
    """Detached identity for long-running routes that must not hold a DB connection."""

    user_id: int
    role: str


def get_current_principal(payload: TokenData) -> UserPrincipal:
    with SessionLocal() as db:
        user = get_active_session_user(
            db, payload.user_id, payload.session_id, payload.generation
        )
        if user is None:
            raise _unauthorized()
        return UserPrincipal(user_id=user.user_id, role=user.role)


CurrentPrincipal = Annotated[UserPrincipal, Depends(get_current_principal)]


def require_roles(*allowed_roles: str) -> Callable[..., User]:
    def dependency(user: CurrentUser) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return user

    return dependency


CurrentAdmin = Annotated[User, Depends(require_roles("admin"))]
