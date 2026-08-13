from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from clipforge.ai.gemini_provider import GeminiProvider
from clipforge.common.errors import ProviderError
from clipforge.common.ports import AIModelUsage
from clipforge.config import Settings
from clipforge.usage.application.service import AIUsageService
from clipforge.usage.domain.entities import AIModelUsageRecord
from clipforge.usage.domain.ports import AIModelUsageRepository


class FakeUsageRepository(AIModelUsageRepository):
    def __init__(self, rows: list[AIModelUsageRecord]) -> None:
        self._rows = rows

    async def record(self, usage: AIModelUsageRecord) -> None:
        self._rows.append(usage)

    async def usage_for_day(self, day: date) -> list[AIModelUsageRecord]:
        return [r for r in self._rows if r.date == day]


def _record(
    total: int,
    day: date,
    operation: str = "transcribe",
    model: str = "gemini-2.5-flash",
    key: str = "key-1",
) -> AIModelUsageRecord:
    return AIModelUsageRecord(
        date=day,
        model=model,
        key=key,
        operation=operation,
        prompt_tokens=10,
        response_tokens=total - 10,
        total_tokens=total,
    )


@pytest.mark.asyncio
async def test_summary_aggregates_today_only() -> None:
    today = date.today()
    rows = [
        _record(100, today, "analyze_video"),
        _record(50, today, "transcribe"),
        _record(30, today - timedelta(days=1), "transcribe"),
    ]
    service = AIUsageService(FakeUsageRepository(rows), Settings(ai_provider="mock"))
    summary = await service.summary_for_today()
    assert summary.tokens_used == 150
    assert summary.requests == 2
    assert summary.requests_remaining == summary.request_limit - 2
    assert len(summary.keys) == 1
    assert summary.keys[0].requests == 2


@pytest.mark.asyncio
async def test_summary_groups_by_api_key() -> None:
    today = date.today()
    rows = [
        _record(100, today, key="key-1"),
        _record(50, today, key="key-2"),
        _record(25, today, key="key-1"),
    ]
    service = AIUsageService(FakeUsageRepository(rows), Settings(ai_provider="mock"))
    summary = await service.summary_for_today()
    assert summary.requests == 3
    assert len(summary.keys) == 2
    by_key = {k.key: k for k in summary.keys}
    assert by_key["key-1"].requests == 2
    assert by_key["key-1"].tokens_used == 125
    assert by_key["key-2"].requests == 1
    assert by_key["key-2"].requests_remaining == 19


@pytest.mark.asyncio
async def test_summary_empty_day() -> None:
    service = AIUsageService(FakeUsageRepository([]), Settings(ai_provider="mock"))
    summary = await service.summary_for_today()
    assert summary.tokens_used == 0
    assert summary.requests == 0
    assert summary.keys == []
    assert summary.tokens_remaining == summary.token_limit


@pytest.mark.asyncio
async def test_summary_never_negative_remaining() -> None:
    today = date.today()
    settings = Settings(ai_provider="mock", gemini_daily_token_limit=100)
    rows = [_record(300, today)]
    service = AIUsageService(FakeUsageRepository(rows), settings)
    summary = await service.summary_for_today()
    assert summary.tokens_remaining == 0
    assert summary.requests_remaining == settings.gemini_daily_request_limit - 1


@pytest.mark.asyncio
async def test_gemini_provider_records_usage_metadata() -> None:
    captured: list[AIModelUsage] = []

    async def on_usage(usage: AIModelUsage) -> None:
        captured.append(usage)

    provider = GeminiProvider(api_key="test-key", on_usage=on_usage)

    from google.genai import types

    class FakeResponse:
        text = '{"ok": true}'
        usage_metadata = types.UsageMetadata(
            prompt_token_count=40,
            response_token_count=60,
            total_token_count=100,
        )

    # _record_usage now requires model parameter
    await provider._record_usage(FakeResponse(), "transcribe", "key-1", "gemini-flash-latest")
    assert len(captured) == 1
    assert captured[0].operation == "transcribe"
    assert captured[0].model == "gemini-flash-latest"
    assert captured[0].key == "key-1"
    assert captured[0].prompt_tokens == 40
    assert captured[0].response_tokens == 60
    assert captured[0].total_tokens == 100


@pytest.mark.asyncio
async def test_gemini_provider_usage_error_does_not_raise() -> None:
    async def on_usage(usage: AIModelUsage) -> None:
        raise RuntimeError("boom")

    provider = GeminiProvider(api_key="test-key", on_usage=on_usage)

    from google.genai import types

    class FakeResponse:
        text = '{"ok": true}'
        usage_metadata = types.UsageMetadata(total_token_count=5)

    await provider._record_usage(FakeResponse(), "analyze_video", "key-1", "gemini-flash-latest")
    await provider._record_usage(object(), "analyze_video", "key-1", "gemini-flash-latest")


@pytest.mark.asyncio
async def test_gemini_provider_falls_back_across_api_keys() -> None:
    used_keys: list[str] = []

    class FakeModel:
        def __init__(self, label: str) -> None:
            self.label = label

        def generate_content(self, model: str, contents: list[Any], config: Any) -> Any:
            used_keys.append(self.label)
            if self.label == "key-1":
                raise Exception("401 quota")

            class FakeUsage:
                prompt_token_count = 5
                response_token_count = 5
                total_token_count = 10

            class FakeResponse:
                text = '{"ok": true}'
                usage_metadata = FakeUsage()

            return FakeResponse()

    provider = GeminiProvider(api_key="k1", api_keys=["k2", "k3"])
    # New structure: dict keyed by model
    provider._clients = {
        "gemini-flash-latest": [
            ("key-1", SimpleNamespace(models=FakeModel("key-1"))),
            ("key-2", SimpleNamespace(models=FakeModel("key-2"))),
            ("key-3", SimpleNamespace(models=FakeModel("key-3"))),
        ]
    }
    parsed = await provider._generate("prompt", operation="transcribe")
    assert parsed == {"ok": True}
    assert used_keys == ["key-1", "key-2"]
    assert provider.KEY == "key-2"


@pytest.mark.asyncio
async def test_gemini_provider_all_keys_fail_raises() -> None:
    class FakeModel:
        def generate_content(self, model: str, contents: list[Any], config: Any) -> Any:
            raise Exception("429 quota")

    provider = GeminiProvider(api_key="k1", api_keys=["k2"])
    provider._clients = {
        "gemini-flash-latest": [
            ("key-1", SimpleNamespace(models=FakeModel())),
            ("key-2", SimpleNamespace(models=FakeModel())),
        ]
    }
    with pytest.raises(ProviderError):
        await provider._generate("prompt", operation="analyze_video")


@pytest.mark.asyncio
async def test_gemini_provider_falls_back_across_models() -> None:
    """Test that provider falls back to next model when current model fails."""
    used_models: list[str] = []

    class FakeModel:
        def generate_content(self, model: str, contents: list[Any], config: Any) -> Any:
            used_models.append(model)
            if model == "gemini-flash-latest":
                raise Exception("model not found: gemini-flash-latest has been retired")

            class FakeUsage:
                prompt_token_count = 5
                response_token_count = 5
                total_token_count = 10

            class FakeResponse:
                text = '{"ok": true}'
                usage_metadata = FakeUsage()

            return FakeResponse()

    provider = GeminiProvider(
        api_key="k1",
        models=["gemini-flash-latest", "gemini-1.5-flash", "gemini-1.5-pro"]
    )
    provider._clients = {
        "gemini-flash-latest": [
            ("key-1", SimpleNamespace(models=FakeModel())),
        ],
        "gemini-1.5-flash": [
            ("key-1", SimpleNamespace(models=FakeModel())),
        ],
        "gemini-1.5-pro": [
            ("key-1", SimpleNamespace(models=FakeModel())),
        ],
    }
    parsed = await provider._generate("prompt", operation="transcribe")
    assert parsed == {"ok": True}
    # Should have tried flash-latest first, then fallen back to 1.5-flash
    assert used_models == ["gemini-flash-latest", "gemini-1.5-flash"]
    assert provider.MODEL == "gemini-1.5-flash"


@pytest.mark.asyncio
async def test_settings_parses_comma_separated_api_keys() -> None:
    settings = Settings(
        ai_provider="gemini",
        gemini_api_keys="k1, k2, k3",
    )
    assert [k.get_secret_value() for k in settings.gemini_api_keys] == ["k1", "k2", "k3"]


def test_settings_gemini_keys_dedupes_and_orders_primary_first() -> None:
    settings = Settings(
        ai_provider="gemini",
        gemini_api_key="primary",
        gemini_api_keys=["dup", "backup", "dup"],
    )
    assert [k.get_secret_value() for k in settings.gemini_keys()] == [
        "primary",
        "dup",
        "backup",
    ]
