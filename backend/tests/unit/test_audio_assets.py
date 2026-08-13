import wave

import numpy as np
import pytest

from clipforge.processing.infrastructure import audio_analysis
from clipforge.processing.infrastructure.audio_analysis import SAMPLE_RATE
from clipforge.rendering.infrastructure.audio_assets import (
    SAMPLE_RATE as ASSET_SAMPLE_RATE,
)
from clipforge.rendering.infrastructure.audio_assets import (
    generate_music_bed,
    generate_sfx,
)


def _beat_signal(beat_times: tuple[float, ...], duration: float = 6.0) -> np.ndarray:
    n = int(SAMPLE_RATE * duration)
    t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
    signal = 0.1 * np.sin(2 * np.pi * 220 * t)
    for beat_time in beat_times:
        signal += 0.9 * np.exp(-np.abs(t - beat_time) * 20.0)
    return signal


def _write_wav(path, samples: np.ndarray) -> None:
    data = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(data.tobytes())


def test_analyze_energy_detects_beat_peaks(monkeypatch) -> None:
    monkeypatch.setattr(
        audio_analysis,
        "_read_mono_samples",
        lambda path, timeout: _beat_signal((1.0, 2.0, 3.0, 4.0)),
    )
    profile = audio_analysis.analyze_audio_energy(None)
    assert profile["has_audio"] is True
    assert len(profile["energy"]) > 0
    assert len(profile["peaks"]) >= 3
    for expected in (1.0, 2.0, 3.0, 4.0):
        assert any(abs(p - expected) <= 0.4 for p in profile["peaks"])


def test_analyze_energy_estimates_bpm(monkeypatch) -> None:
    monkeypatch.setattr(
        audio_analysis,
        "_read_mono_samples",
        lambda path, timeout: _beat_signal((1.0, 1.75, 2.5, 3.25, 4.0), duration=12.0),
    )
    profile = audio_analysis.analyze_audio_energy(None)
    assert profile["bpm"] is not None
    assert 70 <= profile["bpm"] <= 90  # 60/0.75 = 80


def test_analyze_energy_silent_returns_empty_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        audio_analysis,
        "_read_mono_samples",
        lambda path, timeout: np.zeros(int(SAMPLE_RATE), dtype=np.float32),
    )
    profile = audio_analysis.analyze_audio_energy(None)
    assert profile["has_audio"] is True
    assert profile["peaks"] == []
    assert profile["bpm"] is None


def test_analyze_energy_decode_failure_returns_empty_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        audio_analysis, "_read_mono_samples", lambda path, timeout: np.zeros(0, dtype=np.float32)
    )
    profile = audio_analysis.analyze_audio_energy(None)
    assert profile["has_audio"] is False
    assert profile["peaks"] == []


def test_generate_music_bed_writes_wav(tmp_path) -> None:
    path = generate_music_bed(tmp_path / "bed.wav", duration_seconds=2.0, bpm=120)
    assert path.exists()
    with wave.open(str(path), "rb") as wav:
        assert wav.getframerate() == ASSET_SAMPLE_RATE
        assert wav.getsampwidth() == 2
        assert wav.getnchannels() == 1
        assert wav.getnframes() == int(ASSET_SAMPLE_RATE * 2.0)


def test_generate_sfx_boom_and_whoosh(tmp_path) -> None:
    boom = generate_sfx(tmp_path / "boom.wav", "boom", duration=1.0)
    whoosh = generate_sfx(tmp_path / "whoosh.wav", "whoosh", duration=1.0)
    assert boom.exists() and whoosh.exists()
    for path in (boom, whoosh):
        with wave.open(str(path), "rb") as wav:
            assert wav.getnframes() == ASSET_SAMPLE_RATE


@pytest.mark.parametrize("bpm", [None, 60, 200, 130])
def test_generate_music_bed_clamps_bpm(tmp_path, bpm) -> None:
    path = generate_music_bed(tmp_path / f"bed_{bpm}.wav", duration_seconds=1.0, bpm=bpm)
    assert path.exists()
