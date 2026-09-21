from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, Response, status

from app.Auth.auth_service import (
    EmailAlreadyRegisteredError,
    IdempotencyConflictError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidPasswordResetError,
    InvalidSessionError,
    PasswordPolicyError,
    SessionLimitError,
    authenticate_user,
    claim_idempotency_key,
    list_sessions,
    refresh_session,
    register_user,
    release_idempotency_key,
    request_password_reset,
    reset_password,
    revoke_all_sessions,
    revoke_session,
)
from app.Auth.email import password_reset_delivery_is_configured, send_password_reset_email
from app.Auth.models import AuthSession
from app.Global.config import settings
from app.Global.db import SessionLocal
from app.Global.dependencies import CurrentUser, DatabaseSession, TokenData
from app.Global.rate_limit import limiter
from app.Global.schemas import (
    AuthResponse,
    LoginRequest,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
    SessionResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/extension-token")
def extension_token(user: CurrentUser, payload: TokenData, response: Response):
    """Explicit user connection; short-lived token retains session revocation checks."""
    from app.Global.security import create_access_token
    token = create_access_token(user.user_id, payload.session_id, payload.generation)
    response.headers["Cache-Control"] = "no-store"
    return {"access_token": token.encoded, "expires_at": token.expires_at}


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _user_response(user: CurrentUser) -> UserResponse:
    return UserResponse(
        id=str(user.user_id), name=user.username, email=user.email, role=user.role
    )


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    common = {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "domain": settings.cookie_domain,
    }
    response.set_cookie(
        settings.access_cookie_name,
        access_token,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
        **common,
    )
    response.set_cookie(
        settings.refresh_cookie_name,
        refresh_token,
        max_age=settings.refresh_token_expire_days * 86400,
        path=f"{settings.api_v1_prefix}/auth",
        **common,
    )


def _clear_auth_cookies(response: Response) -> None:
    common = {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "domain": settings.cookie_domain,
    }
    response.delete_cookie(settings.access_cookie_name, path="/", **common)
    response.delete_cookie(
        settings.refresh_cookie_name,
        path=f"{settings.api_v1_prefix}/auth",
        **common,
    )


def _deliver_password_reset(
    email: str, token: str, idempotency_key: str, request_fingerprint: str
) -> None:
    if send_password_reset_email(email, token):
        return
    with SessionLocal() as db:
        release_idempotency_key(
            db,
            scope="password-reset-request",
            key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_register)
def register(
    payload: RegisterRequest, request: Request, response: Response, db: DatabaseSession
) -> AuthResponse:
    try:
        result = register_user(
            db,
            name=payload.name,
            email=str(payload.email),
            password=payload.password,
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    _set_auth_cookies(response, result.access_token.encoded, result.refresh_token)
    return AuthResponse(user=_user_response(result.user), access_token=result.access_token.encoded)


@router.post("/login", response_model=AuthResponse)
@limiter.limit(settings.rate_limit_login)
def login(
    payload: LoginRequest, request: Request, response: Response, db: DatabaseSession
) -> AuthResponse:
    try:
        result = authenticate_user(
            db,
            email=str(payload.email),
            password=payload.password,
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from exc
    except SessionLimitError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Active-session limit reached; sign out another device before continuing",
        ) from exc
    except InactiveUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive",
        ) from exc
    _set_auth_cookies(response, result.access_token.encoded, result.refresh_token)
    return AuthResponse(user=_user_response(result.user), access_token=result.access_token.encoded)


@router.post("/refresh", response_model=AuthResponse)
@limiter.limit(settings.rate_limit_refresh)
def refresh(request: Request, response: Response, db: DatabaseSession) -> AuthResponse:
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Session expired")
    try:
        result = refresh_session(
            db,
            refresh_token=token,
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )
    except InvalidSessionError as exc:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Session expired") from exc
    _set_auth_cookies(response, result.access_token.encoded, result.refresh_token)
    return AuthResponse(user=_user_response(result.user), access_token=result.access_token.encoded)


@router.get("/me", response_model=UserResponse)
@limiter.limit(settings.rate_limit_me)
def me(request: Request, response: Response, user: CurrentUser) -> UserResponse:
    return _user_response(user)


@router.get("/sessions", response_model=list[SessionResponse])
@limiter.limit(settings.rate_limit_me)
def sessions(
    request: Request,
    response: Response,
    user: CurrentUser,
    token_data: TokenData,
    db: DatabaseSession,
):
    return [
        _session_response(item, token_data.session_id)
        for item in list_sessions(db, user.user_id)
    ]


def _session_response(session: AuthSession, current_id: str) -> SessionResponse:
    return SessionResponse(
        id=session.session_id,
        created_at=session.created_at,
        last_seen_at=session.last_seen_at,
        expires_at=min(session.idle_expires_at, session.expires_at),
        current=session.session_id == current_id,
    )


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_logout)
def delete_session(
    session_id: str,
    request: Request,
    response: Response,
    user: CurrentUser,
    token_data: TokenData,
    db: DatabaseSession,
) -> MessageResponse:
    if not revoke_session(
        db, session_id=session_id, user=user, ip_address=_client_ip(request)
    ):
        raise HTTPException(status_code=404, detail="Session not found")
    if session_id == token_data.session_id:
        _clear_auth_cookies(response)
    return MessageResponse(message="Session revoked")


@router.post("/logout", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_logout)
def logout(
    request: Request,
    response: Response,
    db: DatabaseSession,
    user: CurrentUser,
    token_data: TokenData,
) -> MessageResponse:
    revoke_session(
        db,
        session_id=token_data.session_id,
        user=user,
        ip_address=_client_ip(request),
    )
    _clear_auth_cookies(response)
    return MessageResponse(message="Signed out successfully")


@router.post("/logout-all", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_logout)
def logout_all(
    request: Request, response: Response, db: DatabaseSession, user: CurrentUser
) -> MessageResponse:
    revoke_all_sessions(db, user=user, ip_address=_client_ip(request))
    _clear_auth_cookies(response)
    return MessageResponse(message="Signed out on all devices")


@router.post("/password-reset/request", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_password_reset)
def password_reset_request(
    payload: PasswordResetRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: DatabaseSession,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
) -> MessageResponse:
    # This is checked before account lookup, so the response reveals only a
    # deployment-wide outage and never whether the email address is registered.
    if not password_reset_delivery_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password reset email delivery is temporarily unavailable",
        )
    try:
        is_new = claim_idempotency_key(
            db,
            scope="password-reset-request",
            key=idempotency_key,
            request_fingerprint=str(payload.email).lower(),
        )
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key was already used for a different request",
        ) from exc
    if is_new:
        email = str(payload.email)
        token = request_password_reset(
            db, email=email, ip_address=_client_ip(request)
        )
        if token:
            background_tasks.add_task(
                _deliver_password_reset,
                email,
                token,
                idempotency_key,
                email.lower(),
            )
    return MessageResponse(
        message="If that account exists, password reset instructions will be sent"
    )


@router.post("/password-reset/confirm", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_password_reset)
def password_reset_confirm(
    payload: PasswordResetConfirmRequest,
    request: Request,
    response: Response,
    db: DatabaseSession,
) -> MessageResponse:
    try:
        reset_password(
            db,
            token=payload.token,
            new_password=payload.password,
            ip_address=_client_ip(request),
        )
    except InvalidPasswordResetError as exc:
        raise HTTPException(
            status_code=400, detail="Password reset link is invalid or expired"
        ) from exc
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    _clear_auth_cookies(response)
    return MessageResponse(message="Password reset successfully; please sign in again")
