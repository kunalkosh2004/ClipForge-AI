from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.api.deps import get_container
from clipforge.common.errors import AuthenticationError
from clipforge.db.session import get_db
from clipforge.identity.domain.entities import User
from clipforge.identity.infrastructure.repositories import SQLAlchemyUserRepository

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None:
        # Browser EventSource cannot send an Authorization header, so allow
        # the access token via query param (used by the SSE status stream).
        query_token = request.query_params.get("token")
        if query_token:
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=query_token)
    if credentials is None:
        raise AuthenticationError("missing bearer token")
    container = get_container(request)
    payload = container.identity_tokens.decode_token(
        credentials.credentials, expected_type="access"
    )
    user = await SQLAlchemyUserRepository(session).get_by_id(payload.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("token subject not found or disabled")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
