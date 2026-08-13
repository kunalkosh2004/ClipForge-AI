from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.api.deps import get_container
from clipforge.db.session import get_db
from clipforge.identity.api.deps import CurrentUser
from clipforge.identity.application import schemas
from clipforge.identity.application.service import IdentityService
from clipforge.identity.infrastructure.repositories import SQLAlchemyUserRepository

router = APIRouter(prefix="/auth", tags=["auth"])


def _service(request: Request, session: AsyncSession) -> IdentityService:
    container = get_container(request)
    return IdentityService(
        users=SQLAlchemyUserRepository(session),
        hasher=container.identity_hasher,
        tokens=container.identity_tokens,
    )


@router.post("/register", response_model=schemas.TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: schemas.RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> schemas.TokenResponse:
    return await _service(request, session).register(payload)


@router.post("/login", response_model=schemas.TokenResponse)
async def login(
    payload: schemas.LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> schemas.TokenResponse:
    return await _service(request, session).login(payload)


@router.post("/refresh", response_model=schemas.TokenResponse)
async def refresh(
    payload: schemas.RefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> schemas.TokenResponse:
    return await _service(request, session).refresh(payload)


@router.get("/me", response_model=schemas.UserResponse)
async def me(user: CurrentUser) -> schemas.UserResponse:
    return schemas.UserResponse.model_validate(user)
