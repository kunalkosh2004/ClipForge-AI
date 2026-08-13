from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.api.deps import get_container
from clipforge.db.session import get_db
from clipforge.identity.api.deps import CurrentUser
from clipforge.usage.application.schemas import AIUsageSummaryResponse
from clipforge.usage.application.service import AIUsageService
from clipforge.usage.infrastructure.repositories import SQLAlchemyAIModelUsageRepository

router = APIRouter(tags=["ai"])


@router.get("/ai/usage", response_model=AIUsageSummaryResponse)
async def get_ai_usage(
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> AIUsageSummaryResponse:
    container = get_container(request)
    service = AIUsageService(
        usage=SQLAlchemyAIModelUsageRepository(session),
        settings=container.settings,
    )
    return await service.summary_for_today()
