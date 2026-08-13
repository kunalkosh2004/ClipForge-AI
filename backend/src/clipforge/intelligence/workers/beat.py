import asyncio
from pathlib import Path
from typing import Any

from clipforge.common import logging as logging_mod
from clipforge.intelligence.workers.base import IntelligenceWorker
from clipforge.processing.infrastructure.audio_analysis import analyze_audio_energy

logger = logging_mod.get_logger(__name__)


class BeatWorker(IntelligenceWorker):
    """Audio beat profile: energy peaks (beat drops) + BPM.

    Two interchangeable engines behind the same artifact schema:
    - `energy` (default): the platform's proven ffmpeg+numpy energy analysis
      (no ML deps).
    - `librosa`: `librosa.beat.beat_track` (tempo-aware, richer onsets) for
      higher-quality beats when the dependency is available.
    """

    kind = "beat"
    version = "beat-v1"
    input_artifacts = ("metadata",)

    def __init__(self, engine: str = "energy") -> None:
        self._engine = engine

    async def detect(
        self, source_path: Path | None, params: dict[str, Any]
    ) -> dict[str, Any]:
        assert source_path is not None  # beat detection always needs the source
        if self._engine == "librosa":
            return await asyncio.to_thread(_detect_beats_librosa, source_path)
        return await asyncio.to_thread(_detect_beats_energy, source_path)


def _detect_beats_energy(path: Path) -> dict[str, Any]:
    profile = analyze_audio_energy(path)
    return {
        "engine": "energy",
        "has_audio": bool(profile.get("has_audio")),
        "peaks": profile.get("peaks", []),
        "bpm": profile.get("bpm"),
        "energy": profile.get("energy", []),
        "sample_rate": profile.get("sample_rate"),
        "window_seconds": profile.get("window_seconds"),
    }


def _detect_beats_librosa(path: Path) -> dict[str, Any]:
    try:
        import librosa
    except ImportError as exc:
        raise RuntimeError("librosa is not installed") from exc

    y, sr = librosa.load(str(path), mono=True)
    if y.size == 0:
        return {
            "engine": "librosa",
            "has_audio": False,
            "peaks": [],
            "bpm": None,
            "energy": [],
        }
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    return {
        "engine": "librosa",
        "has_audio": True,
        "peaks": [round(float(t), 3) for t in beat_times],
        "bpm": round(float(tempo), 1),
        "energy": [],
    }
