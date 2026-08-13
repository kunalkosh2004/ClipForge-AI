import uuid
from abc import ABC, abstractmethod

from clipforge.identity.domain.entities import TokenPayload, User


class UserRepository(ABC):
    @abstractmethod
    async def get_by_email(self, email: str) -> User | None:
        """Return the user with this email, or None."""

    @abstractmethod
    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Return the user with this id, or None."""

    @abstractmethod
    async def create(self, user: User) -> User:
        """Persist a new user and return it with generated fields populated."""


class PasswordHasher(ABC):
    @abstractmethod
    def hash_password(self, password: str) -> str:
        """Return a salted, algorithm-tagged password hash."""

    @abstractmethod
    def verify_password(self, password: str, hashed: str) -> bool:
        """Return True when password matches hashed."""


class TokenService(ABC):
    @abstractmethod
    def create_access_token(self, user_id: uuid.UUID, role: str) -> tuple[str, int]:
        """Return a signed access token and its expiry unix timestamp."""

    @abstractmethod
    def create_refresh_token(self, user_id: uuid.UUID) -> tuple[str, int]:
        """Return a signed refresh token and its expiry unix timestamp."""

    @abstractmethod
    def decode_token(self, token: str, expected_type: str = "access") -> TokenPayload:
        """Return the token claims. Raises AuthenticationError when invalid or wrong type."""
