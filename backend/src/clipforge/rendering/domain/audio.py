"""Audio engine for music bed, ducking, and sound effects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from clipforge.rendering.domain.styles import AudioConfig


@dataclass(frozen=True)
class MusicTrack:
    path: str
    volume_db: float
    duck_db: float
    loop: bool = True
    fade_in: float = 2.0
    fade_out: float = 2.0


@dataclass(frozen=True)
class SoundEffect:
    path: str
    time: float
    volume_db: float = 0.0


@dataclass
class AudioPlan:
    music: MusicTrack | None = None
    sfx: list[SoundEffect] = field(default_factory=list)

    def to_filter_chain(self, clip_duration: float) -> list[str]:
        filters = []

        if self.music:
            music_vol = 10 ** (self.music.volume_db / 20)
            filters.append(
                f"amovie={self.music.path}:loop={int(self.music.loop)},"
                f"volume={music_vol},"
                f"afade=t=in:st=0:d={self.music.fade_in},"
                f"afade=t=out:st={clip_duration - self.music.fade_out}:"
                f"d={self.music.fade_out}[music]"
            )

        for sfx in self.sfx:
            sfx_vol = 10 ** (sfx.volume_db / 20)
            filters.append(
                f"amovie={sfx.path},"
                f"volume={sfx_vol},"
                f"adelay={int(sfx.time * 1000)}|{int(sfx.time * 1000)}[sfx{self.sfx.index(sfx)}]"
            )

        return filters


class AudioEngine:
    def __init__(self, config: AudioConfig):
        self.config = config

    def build_plan(
        self,
        clip_duration: float,
        music_path: str | None = None,
        sfx_triggers: list[dict[str, Any]] | None = None,
        volume_db: float | None = None,
    ) -> AudioPlan:
        plan = AudioPlan()

        if self.config.music_enabled and music_path:
            plan.music = MusicTrack(
                path=music_path,
                volume_db=volume_db if volume_db is not None else self.config.music_volume_db,
                duck_db=self.config.music_duck_db,
            )

        if self.config.sfx_enabled and sfx_triggers:
            for trigger in sfx_triggers:
                plan.sfx.append(SoundEffect(
                    path=trigger.get("path", ""),
                    time=trigger.get("time", 0),
                    volume_db=trigger.get("volume_db", 0),
                ))

        return plan