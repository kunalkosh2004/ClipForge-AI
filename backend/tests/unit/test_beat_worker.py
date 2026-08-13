from pathlib import Path

import pytest

from clipforge.intelligence.workers.beat import (
    BeatWorker,
    _detect_beats_energy,
    _detect_beats_librosa,
)


@pytest.mark.asyncio
async def test_beat_worker_energy_engine_on_audio(tone_video: Path) -> None:
    worker = BeatWorker(engine="energy")
    payload = await worker.detect(tone_video, {})
    assert payload["engine"] == "energy"
    assert payload["has_audio"] is True
    assert isinstance(payload["peaks"], list)
    assert isinstance(payload["energy"], list)


@pytest.mark.asyncio
async def test_beat_worker_energy_engine_no_audio(static_video: Path) -> None:
    worker = BeatWorker(engine="energy")
    payload = await worker.detect(static_video, {})
    assert payload["has_audio"] is False
    assert payload["peaks"] == []


def test_energy_detector_normalizes_profile(tone_video: Path) -> None:
    payload = _detect_beats_energy(tone_video)
    assert set(payload) >= {"engine", "has_audio", "peaks", "bpm", "energy"}


@pytest.mark.asyncio
async def test_beat_worker_librosa_engine(tone_video: Path) -> None:
    pytest.importorskip("librosa", reason="librosa not installed")
    worker = BeatWorker(engine="librosa")
    payload = await worker.detect(tone_video, {})
    assert payload["engine"] == "librosa"
    assert payload["has_audio"] is True
    assert isinstance(payload["peaks"], list)


def test_librosa_detector_normalizes_profile(tone_video: Path) -> None:
    pytest.importorskip("librosa", reason="librosa not installed")
    payload = _detect_beats_librosa(tone_video)
    assert payload["engine"] == "librosa"
    assert payload["bpm"] is None or payload["bpm"] >= 0
