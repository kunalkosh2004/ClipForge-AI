import pytest

from clipforge.ai.mock_provider import MockAIProvider
from clipforge.common.ports import VideoInput


@pytest.fixture
def ai() -> MockAIProvider:
    return MockAIProvider()


@pytest.mark.asyncio
async def test_transcribe(ai: MockAIProvider) -> None:
    video = VideoInput(storage_uri="test.mp4", mime_type="video/mp4", duration_seconds=60.0)
    result = await ai.transcribe(video)
    assert result.language == "en"
    assert len(result.segments) > 0
    assert result.segments[0].text != ""


@pytest.mark.asyncio
async def test_analyze_video(ai: MockAIProvider) -> None:
    video = VideoInput(storage_uri="test.mp4", mime_type="video/mp4", duration_seconds=300.0)
    result = await ai.analyze_video(video)
    assert result.duration_seconds == 300.0
    assert len(result.scenes) == 3
    assert result.topics == ["mock"]


@pytest.mark.asyncio
async def test_generate_editing_plan(ai: MockAIProvider) -> None:
    video = VideoInput(storage_uri="test.mp4", mime_type="video/mp4", duration_seconds=60.0)
    plan = await ai.generate_editing_plan(video)
    assert len(plan.clips) >= 1
    assert plan.clips[0].hook is not None
    assert plan.thumbnail_text == "Mock Thumbnail"


@pytest.mark.asyncio
async def test_direct(ai: MockAIProvider) -> None:
    video = VideoInput(storage_uri="test.mp4", mime_type="video/mp4", duration_seconds=60.0)
    blueprint = await ai.direct(video)
    assert blueprint.preset == "podcast"
    assert len(blueprint.clips) >= 1
    assert len(blueprint.timeline.events) > 0
    tracks = {e.track for e in blueprint.timeline.events}
    assert {"camera", "subtitle", "emoji", "effects", "cta"}.issubset(tracks)
