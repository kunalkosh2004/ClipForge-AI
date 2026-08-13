import asyncio

from sqlalchemy import select

from clipforge.common.ids import uuid7
from clipforge.config import get_settings
from clipforge.container import build_container
from clipforge.db import models as orm
from clipforge.db.session import SessionLocal


async def seed() -> None:
    settings = get_settings()
    container = build_container(settings)

    async with SessionLocal() as session:
        email = "demo@clipforge.ai"
        stmt = select(orm.User).where(orm.User.email == email)
        existing = await session.scalar(stmt)
        if existing is not None:
            print(f"Seed user already exists: {email}")
            return

        user_id = uuid7()
        password_hash = container.identity_hasher.hash_password("demo1234")
        user = orm.User(
            id=user_id,
            email=email,
            password_hash=password_hash,
            full_name="Demo User",
            role=orm.UserRole.USER,
            is_active=True,
        )
        session.add(user)

        project_id = uuid7()
        project = orm.Project(
            id=project_id,
            owner_id=user_id,
            name="Demo Project",
            status=orm.ProjectStatus.ACTIVE,
        )
        session.add(project)

        await session.commit()
        print(f"Seeded demo user: {email} / demo1234")
        print(f"Seeded project: {project.name} ({project.id})")


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
