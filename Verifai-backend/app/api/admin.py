from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select

from app.api.dependencies import CurrentAdmin, DatabaseSession
from app.core.config import settings
from app.core.rate_limit import limiter
from app.models import User
from app.schemas import AdminUserResponse

router = APIRouter(prefix="/admin", tags=["Administration"])


@router.get("/users", response_model=list[AdminUserResponse])
@limiter.limit(settings.rate_limit_me)
def list_users(
    request: Request,
    response: Response,
    admin: CurrentAdmin,
    db: DatabaseSession,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[AdminUserResponse]:
    users = db.scalars(select(User).order_by(User.user_id).offset(offset).limit(limit))
    return [
        AdminUserResponse(
            id=str(user.user_id),
            name=user.username,
            email=user.email,
            role=user.role,
            active=user.is_active,
        )
        for user in users
    ]
