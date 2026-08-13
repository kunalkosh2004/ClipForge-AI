"""Transition engine for clip-to-clip transitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from clipforge.rendering.domain.styles import TransitionConfig


@dataclass(frozen=True)
class TransitionPlan:
    type: str
    duration: float
    params: dict[str, Any] = field(default_factory=dict)

    def to_filter_chain(self, prev_stream: str, curr_stream: str, out_stream: str) -> list[str]:
        if self.type == "cut" or self.duration <= 0:
            return [f"[{curr_stream}]copy[{out_stream}]"]

        if self.type == "crossfade":
            return [
                f"[{prev_stream}][{curr_stream}]xfade=transition=fade:"
                f"duration={self.duration}:offset=0[{out_stream}]"
            ]

        if self.type == "fade":
            return [
                f"[{prev_stream}]fade=t=out:st=0:d={self.duration}[v0];"
                f"[{curr_stream}]fade=t=in:st=0:d={self.duration}[v1];"
                f"[v0][v1]overlay[{out_stream}]"
            ]

        if self.type == "slide":
            direction = self.params.get("direction", "left")
            if direction == "left":
                expr = f"x='if(lt(t,{self.duration}),-W*(1-t/{self.duration}),0)'"
            elif direction == "right":
                expr = f"x='if(lt(t,{self.duration}),W*(1-t/{self.duration}),0)'"
            elif direction == "up":
                expr = f"y='if(lt(t,{self.duration}),-H*(1-t/{self.duration}),0)'"
            else:
                expr = f"y='if(lt(t,{self.duration}),H*(1-t/{self.duration}),0)'"
            return [
                f"[{curr_stream}]setpts=PTS-STARTPTS,"
                f"pad=W*2:H:W:0,"
                f"crop=W:H:{expr}[v1];"
                f"[{prev_stream}]setpts=PTS-STARTPTS[v0];"
                f"[v0][v1]overlay=shortest=1[{out_stream}]"
            ]

        if self.type == "zoom":
            return [
                f"[{curr_stream}]setpts=PTS-STARTPTS,"
                f"zoompan=z='if(lt(t,{self.duration}),1+(t/{self.duration})*0.5,1)':"
                f"d={int(self.duration * 30)}:s=1920x1080[v1];"
                f"[{prev_stream}]setpts=PTS-STARTPTS[v0];"
                f"[v0][v1]overlay=shortest=1[{out_stream}]"
            ]

        if self.type == "glitch":
            return [
                f"[{curr_stream}]setpts=PTS-STARTPTS,"
                f"geq='if(lt(t,{self.duration}),"
                f"random(0)*30+st(0,random(0))*10,"
                f"p(X,Y))'[v1];"
                f"[{prev_stream}]setpts=PTS-STARTPTS[v0];"
                f"[v0][v1]overlay=shortest=1[{out_stream}]"
            ]

        if self.type == "wipe":
            return [
                f"[{prev_stream}][{curr_stream}]xfade=transition=wipeleft:"
                f"duration={self.duration}:offset=0[{out_stream}]"
            ]

        return [f"[{curr_stream}]copy[{out_stream}]"]


class TransitionEngine:
    def __init__(self, config: TransitionConfig):
        self.config = config

    def build_plan(self) -> TransitionPlan:
        if not self.config.enabled:
            return TransitionPlan(type="cut", duration=0)
        return TransitionPlan(
            type=self.config.type,
            duration=self.config.duration,
            params={"easing": self.config.easing}
        )