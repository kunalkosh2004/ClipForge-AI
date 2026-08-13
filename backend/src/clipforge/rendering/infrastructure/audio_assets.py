"""Programmatic music bed and SFX synthesis.

The editing presets reference a music bed and sound effects, but shipping
licensed audio assets is out of scope. These generators produce simple,
deterministic tracks at render time with numpy (already a dependency) so the
audio engine has real inputs without external files. Drop-in royalty-free
assets can replace them later without touching the render pipeline.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 44100


def generate_music_bed(
    path: Path,
    duration_seconds: float,
    bpm: float | None = None,
    volume: float = 0.25,
) -> Path:
    """A soft ambient pad with a kick pulse locked to `bpm` (default 100)."""
    bpm = bpm if bpm and 70 <= bpm <= 180 else 100.0
    n = int(SAMPLE_RATE * max(duration_seconds, 0.5))
    t = np.arange(n, dtype=np.float64) / SAMPLE_RATE

    # A-minor pad: A2, C3, E3 with a sub root for warmth.
    freqs = (110.0, 130.81, 164.81, 55.0)
    pad = np.zeros(n, dtype=np.float64)
    for i, f in enumerate(freqs):
        detune = 1.0 + 0.0015 * i
        tone = np.sin(2 * np.pi * f * detune * t + 0.2 * i)
        if i < len(freqs) - 1:
            tone += 0.35 * np.sin(2 * np.pi * f * 2 * detune * t)
        pad += tone / len(freqs)

    # Half-time amplitude pulse breathes with the beat.
    pulse = 0.75 + 0.25 * np.sin(2 * np.pi * (bpm / 120.0) * t)
    pad = pad * pulse

    # Kick on every beat: short decaying sine at the root octave.
    kick_interval = 60.0 / bpm
    beat = 0.0
    while beat < duration_seconds:
        local = t - beat
        mask = (local >= 0) & (local < 0.28)
        kick = np.sin(2 * np.pi * 55.0 * local[mask]) * np.exp(-local[mask] * 20.0)
        pad[mask] += 1.6 * kick
        beat += kick_interval

    peak = float(np.max(np.abs(pad))) or 1.0
    pad = pad / peak * volume
    _write_wav(path, pad)
    return path


def generate_sfx(path: Path, kind: str, duration: float = 1.0) -> Path:
    """A single-synth effect: `boom` (beat-drop thump) or `whoosh` (riser)."""
    samples = _boom(duration) if kind == "boom" else _whoosh(duration)
    _write_wav(path, samples)
    return path


def _boom(duration: float) -> np.ndarray:
    n = int(SAMPLE_RATE * duration)
    t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
    sweep = 85.0 - 40.0 * (t / duration)
    phase = 2 * np.pi * np.cumsum(sweep) / SAMPLE_RATE
    env = np.exp(-t * 5.0)
    signal = np.sin(phase) * env
    signal += 0.4 * np.sin(2 * np.pi * 55.0 * t) * env
    return signal * 0.8


def _whoosh(duration: float) -> np.ndarray:
    n = int(SAMPLE_RATE * duration)
    rng = np.random.default_rng(42)
    noise = rng.standard_normal(n)
    # Cheap one-pole lowpass for body.
    filtered = _lowpass(noise, 0.12)
    t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
    env = np.sin(np.pi * t / duration) ** 2
    return filtered * env * 0.6


def _lowpass(signal: np.ndarray, alpha: float) -> np.ndarray:
    out = np.empty_like(signal)
    prev = 0.0
    for i, x in enumerate(signal):
        prev = prev + alpha * (x - prev)
        out[i] = prev
    return out


def _write_wav(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(data.tobytes())


def silence_frames(seconds: float) -> np.ndarray:
    return np.zeros(int(SAMPLE_RATE * seconds), dtype=np.float64)


if __name__ == "__main__":
    # Quick smoke test: render a 10s bed + effects into the current directory.
    out = Path("assets-out")
    out.mkdir(exist_ok=True)
    generate_music_bed(out / "bed.wav", 10.0, bpm=120)
    generate_sfx(out / "boom.wav", "boom")
    generate_sfx(out / "whoosh.wav", "whoosh")
    print("generated:", [p.name for p in out.iterdir()])
