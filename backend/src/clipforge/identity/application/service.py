import uuid

from clipforge.common.errors import (
    AuthenticationError,
    ConflictError,
    EntityNotFoundError,
    ForbiddenError,
)
from clipforge.identity.application import schemas
from clipforge.identity.domain import entities, ports


class IdentityService:
    def __init__(
        self,
        users: ports.UserRepository,
        hasher: ports.PasswordHasher,
        tokens: ports.TokenService,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._tokens = tokens

    async def register(self, request: schemas.RegisterRequest) -> schemas.TokenResponse:
        existing = await self._users.get_by_email(request.email)
        if existing is not None:
            raise ConflictError("email already registered")
        password_hash = self._hasher.hash_password(request.password)
        user = await self._users.create(
            entities.User(
                email=request.email,
                password_hash=password_hash,
                full_name=request.full_name,
            )
        )
        return self._issue_token(user)

    async def login(self, request: schemas.LoginRequest) -> schemas.TokenResponse:
        user = await self._users.get_by_email(request.email)
        if user is None or not self._hasher.verify_password(request.password, user.password_hash):
            raise AuthenticationError("invalid email or password")
        if not user.is_active:
            raise ForbiddenError("account disabled")
        return self._issue_token(user)

    async def refresh(self, request: schemas.RefreshRequest) -> schemas.TokenResponse:
        payload = self._tokens.decode_token(request.refresh_token, expected_type="refresh")
        user = await self._users.get_by_id(payload.user_id)
        if user is None:
            raise AuthenticationError("token subject not found")
        if not user.is_active:
            raise ForbiddenError("account disabled")
        return self._issue_token(user)

    async def get_user(self, user_id: uuid.UUID) -> schemas.UserResponse:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise EntityNotFoundError("user not found")
        return schemas.UserResponse.model_validate(user)

    def _issue_token(self, user: entities.User) -> schemas.TokenResponse:
        access_token, expires_in = self._tokens.create_access_token(user.id, user.role)
        refresh_token, _ = self._tokens.create_refresh_token(user.id)
        return schemas.TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )
