import uuid

import pytest

from clipforge.analysis.application.service import AnalysisService
from clipforge.analysis.domain.entities import AnalysisResultRecord, TranscriptRecord
from clipforge.analysis.domain.ports import AnalysisResultRepository, TranscriptRepository
from clipforge.common.errors import EntityNotFoundError


class FakeTranscriptRepo(TranscriptRepository):
    def __init__(self) -> None:
        self._store: dict[uuid.UUID, TranscriptRecord] = {}

    async def get_by_video_id(self, video_id: uuid.UUID) -> TranscriptRecord | None:
        for t in self._store.values():
            if t.video_id == video_id:
                return t
        return None

    async def create(self, transcript: TranscriptRecord) -> TranscriptRecord:
        self._store[transcript.id] = transcript
        return transcript


class FakeAnalysisRepo(AnalysisResultRepository):
    def __init__(self) -> None:
        self._store: dict[uuid.UUID, AnalysisResultRecord] = {}

    async def get_by_video_id(self, video_id: uuid.UUID) -> AnalysisResultRecord | None:
        for a in self._store.values():
            if a.video_id == video_id:
                return a
        return None

    async def create(self, result: AnalysisResultRecord) -> AnalysisResultRecord:
        self._store[result.id] = result
        return result


class FakeVideoRepo:
    def __init__(self) -> None:
        self._videos: dict[uuid.UUID, object] = {}

    async def get_by_id(self, video_id: uuid.UUID) -> object | None:
        return self._videos.get(video_id)

    def seed(self, video_id: uuid.UUID, obj: object) -> None:
        self._videos[video_id] = obj


class FakeNotifier:
    async def publish(self, event: dict) -> None:
        pass


class FakeStorage:
    async def delete(self, key: str) -> None:
        pass


@pytest.fixture
def repos() -> tuple[FakeVideoRepo, FakeTranscriptRepo, FakeAnalysisRepo]:
    return FakeVideoRepo(), FakeTranscriptRepo(), FakeAnalysisRepo()


@pytest.fixture
def service(repos: tuple) -> AnalysisService:
    videos, transcripts, analyses = repos
    return AnalysisService(
        videos=videos,
        transcripts=transcripts,
        analysis_results=analyses,
        ai=None,
        storage=FakeStorage(),
        notifier=FakeNotifier(),
    )


@pytest.mark.asyncio
async def test_get_transcript_not_found(service: AnalysisService) -> None:
    with pytest.raises(EntityNotFoundError):
        await service.get_transcript(uuid.uuid4())


@pytest.mark.asyncio
async def test_get_analysis_not_found(service: AnalysisService) -> None:
    with pytest.raises(EntityNotFoundError):
        await service.get_analysis_result(uuid.uuid4())


@pytest.mark.asyncio
async def test_upsert_transcript(service: AnalysisService, repos: tuple) -> None:
    _, transcripts, _ = repos
    vid = uuid.uuid4()
    t = TranscriptRecord(
        video_id=vid,
        language="en",
        segments=[{"start": 0, "end": 1, "text": "hi", "confidence": 0.9}],
    )
    result = await transcripts.create(t)
    assert result.video_id == vid
    found = await service.get_transcript(vid)
    assert found.id == result.id


@pytest.mark.asyncio
async def test_upsert_analysis(service: AnalysisService, repos: tuple) -> None:
    _, _, analyses = repos
    vid = uuid.uuid4()
    a = AnalysisResultRecord(
        video_id=vid,
        understanding={"scenes": []},
        editing_plan={"clips": []},
        ai_model="mock",
    )
    result = await analyses.create(a)
    assert result.video_id == vid
    found = await service.get_analysis_result(vid)
    assert found.id == result.id
