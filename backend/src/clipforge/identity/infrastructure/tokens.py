import uuid
from datetime import UTC, datetime, timedelta

import jwt

from clipforge.common.errors import AuthenticationError
from clipforge.identity.domain.entities import TokenPayload
from clipforge.identity.domain.ports import TokenService


class JWTTokenService(TokenService):
    def __init__(
        self,
        secret: str,
        algorithm: str,
        expire_minutes: int,
        refresh_expire_days: int = 30,
    ) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._expire_minutes = expire_minutes
        self._refresh_expire_days = refresh_expire_days

    def create_access_token(self, user_id: uuid.UUID, role: str) -> tuple[str, int]:
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=self._expire_minutes)
        payload = {
            "sub": str(user_id),
            "role": role,
            "type": "access",
            "iat": now,
            "exp": expires_at,
        }
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        return token, int(expires_at.timestamp())

    def create_refresh_token(self, user_id: uuid.UUID) -> tuple[str, int]:
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=self._refresh_expire_days)
        payload = {
            "sub": str(user_id),
            "type": "refresh",
            "iat": now,
            "exp": expires_at,
        }
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        return token, int(expires_at.timestamp())

    def decode_token(self, token: str, expected_type: str = "access") -> TokenPayload:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.PyJWTError as exc:
            raise AuthenticationError("invalid or expired token") from exc

        token_type = payload.get("type", "access")
        if token_type != expected_type:
            raise AuthenticationError(
                f"expected {expected_type} token, got {token_type}"
            )

        sub = payload.get("sub")
        exp = payload.get("exp")
        role = payload.get("role")
        if not isinstance(sub, str) or not isinstance(exp, int):
            raise AuthenticationError("malformed token claims")
        if expected_type == "access" and not isinstance(role, str):
            raise AuthenticationError("malformed token claims")

        try:
            user_id = uuid.UUID(sub)
        except ValueError as exc:
            raise AuthenticationError("malformed token subject") from exc

        return TokenPayload(
            user_id=user_id,
            role=role or "user",
            exp=datetime.fromtimestamp(exp, tz=UTC),
        )
