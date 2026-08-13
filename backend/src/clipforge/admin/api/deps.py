from typing import Annotated

from fastapi import Depends

from clipforge.common.errors import ForbiddenError
from clipforge.identity.api.deps import get_current_user
from clipforge.identity.domain.entities import User


async def get_admin_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != "admin":
        raise ForbiddenError("admin role required")
    return user


AdminUser = Annotated[User, Depends(get_admin_user)]
