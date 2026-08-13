import asyncio
from pathlib import Path
from typing import Any

from clipforge.intelligence.workers.base import IntelligenceWorker
from clipforge.timeline.domain.engine import build_timeline


class TimelineWorker(IntelligenceWorker):
    """Shot-level emphasis, punch-in, and cut timing from M1 artifacts.

    Pure artifact computation: consumes the scene, motion, and beat payloads
    and never reads the source video (`needs_source = False`), so the
    pipeline skips the download entirely for this node.
    """

    kind = "timeline"
    version = "timeline-v1"
    input_artifacts = ("scene", "motion", "beat")
    needs_source = False

    async def detect(
        self, source_path: Path | None, params: dict[str, Any]
    ) -> dict[str, Any]:
        return await asyncio.to_thread(_build_timeline, params)

    def validate(self, payload: dict[str, Any]) -> None:
        super().validate(payload)
        if not isinstance(payload.get("shots"), list):
            raise ValueError("timeline payload must include a shots list")
        if not isinstance(payload.get("punch_ins"), list):
            raise ValueError("timeline payload must include a punch_ins list")


def _build_timeline(params: dict[str, Any]) -> dict[str, Any]:
    artifacts = params.get("artifacts") or {}
    return build_timeline(
        scenes=artifacts.get("scene"),
        motion=artifacts.get("motion"),
        beats=artifacts.get("beat"),
    )
