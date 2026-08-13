import uuid
from datetime import UTC, datetime, timedelta

import pytest

from clipforge.common.errors import AuthenticationError, ConflictError
from clipforge.identity.application.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
)
from clipforge.identity.application.service import IdentityService
from clipforge.identity.domain.entities import TokenPayload, User


class FakeUserRepository:
    def __init__(self) -> None:
        self._users: dict[uuid.UUID, User] = {}
        self._by_email: dict[str, User] = {}

    async def get_by_email(self, email: str) -> User | None:
        return self._by_email.get(email)

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._users.get(user_id)

    async def create(self, user: User) -> User:
        self._users[user.id] = user
        self._by_email[user.email] = user
        return user


class FakeHasher:
    def hash_password(self, password: str) -> str:
        return f"hashed:{password}"

    def verify_password(self, password: str, hashed: str) -> bool:
        return hashed == f"hashed:{password}"


class FakeTokenService:
    def __init__(self) -> None:
        self._access_tokens: dict[str, TokenPayload] = {}
        self._refresh_tokens: dict[str, TokenPayload] = {}

    def create_access_token(self, user_id: uuid.UUID, role: str) -> tuple[str, int]:
        token = f"access:{user_id}"
        self._access_tokens[token] = TokenPayload(
            user_id=user_id, role=role, exp=datetime.now(UTC) + timedelta(hours=1)
        )
        return token, int((datetime.now(UTC) + timedelta(hours=1)).timestamp())

    def create_refresh_token(self, user_id: uuid.UUID) -> tuple[str, int]:
        token = f"refresh:{user_id}"
        self._refresh_tokens[token] = TokenPayload(
            user_id=user_id, role="user", exp=datetime.now(UTC) + timedelta(days=30)
        )
        return token, int((datetime.now(UTC) + timedelta(days=30)).timestamp())

    def decode_token(self, token: str, expected_type: str = "access") -> TokenPayload:
        tokens = self._access_tokens if expected_type == "access" else self._refresh_tokens
        if token not in tokens:
            raise AuthenticationError(f"invalid {expected_type} token")
        return tokens[token]


@pytest.fixture
def service() -> IdentityService:
    return IdentityService(
        users=FakeUserRepository(),
        hasher=FakeHasher(),
        tokens=FakeTokenService(),
    )


@pytest.mark.asyncio
async def test_register_success(service: IdentityService) -> None:
    req = RegisterRequest(email="new@example.com", password="pass12345")
    result = await service.register(req)
    assert result.access_token.startswith("access:")
    assert result.refresh_token.startswith("refresh:")
    assert result.token_type == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email(service: IdentityService) -> None:
    req = RegisterRequest(email="dup@example.com", password="pass12345")
    await service.register(req)
    with pytest.raises(ConflictError):
        await service.register(req)


@pytest.mark.asyncio
async def test_login_success(service: IdentityService) -> None:
    await service.register(RegisterRequest(email="a@b.com", password="pass12345"))
    result = await service.login(LoginRequest(email="a@b.com", password="pass12345"))
    assert result.access_token.startswith("access:")
    assert result.refresh_token.startswith("refresh:")


@pytest.mark.asyncio
async def test_login_wrong_password(service: IdentityService) -> None:
    await service.register(RegisterRequest(email="a@b.com", password="pass12345"))
    with pytest.raises(AuthenticationError):
        await service.login(LoginRequest(email="a@b.com", password="wrong"))


@pytest.mark.asyncio
async def test_login_nonexistent_user(service: IdentityService) -> None:
    with pytest.raises(AuthenticationError):
        await service.login(LoginRequest(email="no@b.com", password="pass12345"))


@pytest.mark.asyncio
async def test_refresh_success(service: IdentityService) -> None:
    reg = await service.register(RegisterRequest(email="a@b.com", password="pass12345"))
    result = await service.refresh(RefreshRequest(refresh_token=reg.refresh_token))
    assert result.access_token.startswith("access:")
    assert result.refresh_token.startswith("refresh:")


@pytest.mark.asyncio
async def test_refresh_with_access_token_fails(service: IdentityService) -> None:
    reg = await service.register(RegisterRequest(email="a@b.com", password="pass12345"))
    with pytest.raises(AuthenticationError):
        await service.refresh(RefreshRequest(refresh_token=reg.access_token))
