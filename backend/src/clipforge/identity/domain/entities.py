import uuid
from dataclasses import dataclass, field
from datetime import datetime

from clipforge.common.ids import uuid7


@dataclass(frozen=True)
class User:
    email: str
    password_hash: str
    full_name: str | None = None
    role: str = "user"
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: uuid.UUID = field(default_factory=uuid7)


@dataclass(frozen=True)
class TokenPayload:
    user_id: uuid.UUID
    role: str
    exp: datetime
