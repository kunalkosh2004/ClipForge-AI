from pydantic import BaseModel, Field


class AIModelUsageSummary(BaseModel):
    key: str
    model: str
    requests: int = Field(ge=0)
    request_limit: int = Field(ge=0)
    requests_remaining: int = Field(ge=0)
    tokens_used: int = Field(ge=0)
    token_limit: int = Field(ge=0)
    tokens_remaining: int = Field(ge=0)


class AIUsageSummaryResponse(BaseModel):
    date: str
    keys: list[AIModelUsageSummary]
    tokens_used: int = Field(ge=0)
    token_limit: int = Field(ge=0)
    tokens_remaining: int = Field(ge=0)
    requests: int = Field(ge=0)
    request_limit: int = Field(ge=0)
    requests_remaining: int = Field(ge=0)
