import uuid
from abc import ABC, abstractmethod

from clipforge.analysis.domain.entities import AnalysisResultRecord, TranscriptRecord


class TranscriptRepository(ABC):
    @abstractmethod
    async def get_by_video_id(self, video_id: uuid.UUID) -> TranscriptRecord | None:
        """Return the transcript for a video, or None."""

    @abstractmethod
    async def create(self, transcript: TranscriptRecord) -> TranscriptRecord:
        """Persist a transcript and return it with generated fields populated."""


class AnalysisResultRepository(ABC):
    @abstractmethod
    async def get_by_video_id(self, video_id: uuid.UUID) -> AnalysisResultRecord | None:
        """Return the analysis result for a video, or None."""

    @abstractmethod
    async def create(self, result: AnalysisResultRecord) -> AnalysisResultRecord:
        """Persist an analysis result and return it with generated fields populated."""
