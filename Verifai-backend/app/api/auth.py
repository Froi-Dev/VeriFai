from fastapi import APIRouter, HTTPException, Request, status

from app.api.dependencies import CurrentUser, DatabaseSession, TokenData
from app.core.config import settings
from app.core.rate_limit import limiter
from app.schemas import (
    AuthResponse,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    UserResponse,
)
from app.services.auth import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidCredentialsError,
    authenticate_user,
    register_user,
    revoke_session,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _user_response(user: CurrentUser) -> UserResponse:
    return UserResponse(id=str(user.user_id), name=user.username, email=user.email)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_register)
def register(payload: RegisterRequest, request: Request, db: DatabaseSession) -> AuthResponse:
    try:
        user, token = register_user(
            db,
            name=payload.name,
            email=str(payload.email),
            password=payload.password,
            ip_address=_client_ip(request),
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc
    return AuthResponse(token=token.encoded, user=_user_response(user))


@router.post("/login", response_model=AuthResponse)
@limiter.limit(settings.rate_limit_login)
def login(payload: LoginRequest, request: Request, db: DatabaseSession) -> AuthResponse:
    try:
        user, token = authenticate_user(
            db,
            email=str(payload.email),
            password=payload.password,
            ip_address=_client_ip(request),
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except InactiveUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive",
        ) from exc
    return AuthResponse(token=token.encoded, user=_user_response(user))


@router.get("/me", response_model=UserResponse)
@limiter.limit(settings.rate_limit_me)
def me(request: Request, user: CurrentUser) -> UserResponse:
    return _user_response(user)


@router.post("/logout", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_logout)
def logout(
    request: Request,
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
    return MessageResponse(message="Signed out successfully")
