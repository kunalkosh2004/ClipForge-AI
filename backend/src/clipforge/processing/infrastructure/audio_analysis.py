"""Audio energy + beat-drop analysis using ffmpeg and numpy.

No audio ML dependencies required: the video's audio track is decoded to
mono PCM with ffmpeg and a short-window RMS energy profile is computed.
"Beat drops" are detected as local energy peaks above a threshold derived
from the clip's own statistics, which downstream rendering uses to time
punch zooms, transitions, and SFX.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from clipforge.common import logging as logging_mod

logger = logging_mod.get_logger(__name__)

SAMPLE_RATE = 44100
WINDOW_SECONDS = 0.25
CHUNK_SECONDS = 8.0
_MIN_PEAK_GAP_SECONDS = 0.4
_PEAK_THRESHOLD_MULT = 1.5
_PEAK_PROMINENCE = 0.5


def analyze_audio_energy(path: Path, timeout: int = 300) -> dict[str, Any]:
    """Return an energy profile and beat-drop timestamps for a media file.

    The result is intentionally best-effort: videos without an audio track or
    with a decode failure return an empty profile instead of raising, so the
    rest of the pipeline keeps working.
    """
    samples = _read_mono_samples(path, timeout)
    if samples.size == 0:
        return _empty_profile(has_audio=False)

    window = int(SAMPLE_RATE * WINDOW_SECONDS)
    energy = _windowed_rms(samples, window)

    peaks = _detect_peaks(energy, WINDOW_SECONDS)
    bpm = _estimate_bpm(peaks)

    return {
        "has_audio": True,
        "sample_rate": SAMPLE_RATE,
        "window_seconds": WINDOW_SECONDS,
        "energy": [round(float(v), 5) for v in energy],
        "peaks": [round(float(t), 3) for t in peaks],
        "bpm": round(float(bpm), 1) if bpm else None,
    }


def _read_mono_samples(path: Path, timeout: int) -> np.ndarray:
    cmd = [
        "ffmpeg",
        "-v", "error",
        "-i", str(path),
        "-ac", "1",
        "-ar", str(SAMPLE_RATE),
        "-f", "f32le",
        "-",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("audio_decode_failed", path=str(path), error=str(exc)[:200])
        return np.zeros(0, dtype=np.float32)
    if proc.returncode != 0:
        return np.zeros(0, dtype=np.float32)

    data = np.frombuffer(proc.stdout, dtype="<f4").astype(np.float64)
    if data.size == 0:
        return data
    peak = float(np.max(np.abs(data)))
    if peak > 1.0:
        data = data / peak
    return data


def _windowed_rms(samples: np.ndarray, window: int) -> np.ndarray:
    n = samples.size // window
    if n == 0:
        return np.zeros(0, dtype=np.float64)
    trimmed = samples[: n * window].reshape(n, window)
    rms = np.sqrt(np.mean(np.square(trimmed), axis=1))
    return np.maximum(rms, 1e-5)


def _detect_peaks(energy: np.ndarray, window_seconds: float) -> list[float]:
    if energy.size < 4:
        return []

    # Smooth with a 3-tap moving average so transients don't create clumps.
    kernel = np.ones(3) / 3.0
    padded = np.concatenate(([energy[0], energy[0]], energy, [energy[-1], energy[-1]]))
    smooth = np.convolve(padded, kernel, mode="valid")

    mean = float(np.mean(smooth))
    std = float(np.std(smooth))
    threshold = max(mean + _PEAK_THRESHOLD_MULT * std, mean * 1.5)

    times: list[float] = []
    last_peak = -_MIN_PEAK_GAP_SECONDS
    for i in range(1, energy.size - 1):
        val = float(energy[i])
        left = float(energy[i - 1])
        right = float(energy[i + 1])
        if val < threshold or val < left or val < right:
            continue
        floor = float(min(energy[max(0, i - 3): i + 1]))
        prominence = (val - floor) / max(val, 1e-6)
        if prominence < _PEAK_PROMINENCE:
            continue
        t = i * window_seconds
        if t - last_peak < _MIN_PEAK_GAP_SECONDS:
            continue
        times.append(t)
        last_peak = t

    return times


def _estimate_bpm(peaks: list[float]) -> float | None:
    if len(peaks) < 2:
        return None
    intervals = [b - a for a, b in zip(peaks, peaks[1:], strict=False)]
    median = float(np.median([i for i in intervals if i > 0.25]))
    if median <= 0:
        return None
    bpm = 60.0 / median
    if bpm < 70 or bpm > 180:
        return None
    return bpm


def _empty_profile(has_audio: bool = True) -> dict[str, Any]:
    return {
        "has_audio": has_audio,
        "sample_rate": SAMPLE_RATE,
        "window_seconds": WINDOW_SECONDS,
        "energy": [],
        "peaks": [],
        "bpm": None,
    }
