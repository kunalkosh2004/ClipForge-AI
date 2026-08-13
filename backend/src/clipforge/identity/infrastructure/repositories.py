import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.db import models as orm
from clipforge.identity.domain.entities import User
from clipforge.identity.domain.ports import UserRepository


class SQLAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        row = await self._session.scalar(select(orm.User).where(orm.User.email == email))
        return _to_domain(row) if row is not None else None

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        row = await self._session.get(orm.User, user_id)
        return _to_domain(row) if row is not None else None

    async def create(self, user: User) -> User:
        row = orm.User(
            email=user.email,
            password_hash=user.password_hash,
            full_name=user.full_name,
            role=orm.UserRole(user.role),
            is_active=user.is_active,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_domain(row)


def _to_domain(row: orm.User) -> User:
    return User(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        full_name=row.full_name,
        role=row.role.value,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
