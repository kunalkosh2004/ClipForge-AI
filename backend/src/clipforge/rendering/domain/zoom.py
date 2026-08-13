"""Zoom engine for punch zoom, emphasis zoom, and auto-zoom effects."""

from __future__ import annotations

from dataclasses import dataclass

from clipforge.rendering.domain.styles import ZoomConfig


@dataclass(frozen=True)
class ZoomKeyframe:
    time: float
    scale: float
    x: float = 0.5
    y: float = 0.5


@dataclass(frozen=True)
class ZoomPlan:
    keyframes: list[ZoomKeyframe]

    def to_filter_expr(self, width: int, height: int) -> str:
        if not self.keyframes or all(kf.scale == 1.0 for kf in self.keyframes):
            return f"scale={width}:{height}"

        # Each zoom "peak" becomes a Gaussian pulse centered on its keyframe
        # time. ffmpeg filter option values cannot contain commas (the option
        # parser splits on `,` and `:`), so we avoid if()/lt()-style piecewise
        # expressions entirely and sum single-argument exp() terms instead.
        pulses: list[tuple[float, float, float]] = []  # (time, amp, width)
        kfs = self.keyframes
        for i, kf in enumerate(kfs):
            if kf.scale <= 1.0:
                continue
            if i > 0 and kfs[i - 1].scale >= kf.scale:
                continue
            if i + 1 < len(kfs) and kfs[i + 1].scale > kf.scale:
                continue
            end_time = kfs[i + 1].time if i + 1 < len(kfs) else kf.time + 1.0
            dur = max(end_time - kf.time, 0.2)
            pulses.append((kf.time, kf.scale - 1.0, dur))

        if not pulses:
            return f"scale={width}:{height}"

        terms: list[str] = []
        for time, amp, dur in pulses:
            sigma = max(dur / 3.0, 0.1)
            dt = f"(t-{time:.3f})"
            terms.append(
                f"{amp:.6f}*exp(-0.5*({dt}*{dt}/{sigma * sigma:.6f}))"
            )
        s_expr = "1.0+" + "+".join(terms)
        return (
            f"scale=w=iw*({s_expr}):h=ih*({s_expr}):eval=frame,"
            f"crop=out_w={width}:out_h={height}:x=0.5*(iw-{width}):y=0.5*(ih-{height})"
        )


class ZoomEngine:
    def __init__(self, config: ZoomConfig):
        self.config = config

    def build_zoom_plan(
        self,
        clip_duration: float,
        emphasis_times: list[float] | None = None,
        keyword_times: list[float] | None = None,
    ) -> ZoomPlan:
        keyframes = [ZoomKeyframe(time=0.0, scale=1.0, x=0.5, y=0.5)]

        if self.config.punch_zoom_enabled and clip_duration > 1.0:
            punch_time = min(0.5, clip_duration * 0.1)
            keyframes.append(ZoomKeyframe(
                time=punch_time,
                scale=self.config.punch_zoom_scale,
                x=0.5, y=0.5
            ))
            keyframes.append(ZoomKeyframe(
                time=punch_time + self.config.punch_zoom_duration,
                scale=1.0,
                x=0.5, y=0.5
            ))

        if self.config.emphasis_zoom_enabled and emphasis_times:
            for t in emphasis_times:
                if 0 < t < clip_duration:
                    keyframes.append(ZoomKeyframe(
                        time=t,
                        scale=self.config.emphasis_zoom_scale,
                        x=0.5, y=0.5
                    ))
                    keyframes.append(ZoomKeyframe(
                        time=min(t + self.config.emphasis_zoom_duration, clip_duration),
                        scale=1.0,
                        x=0.5, y=0.5
                    ))

        if self.config.auto_zoom_on_keywords and keyword_times:
            for t in keyword_times:
                if 0 < t < clip_duration:
                    keyframes.append(ZoomKeyframe(
                        time=t,
                        scale=1.05,
                        x=0.5, y=0.5
                    ))
                    keyframes.append(ZoomKeyframe(
                        time=min(t + 0.3, clip_duration),
                        scale=1.0,
                        x=0.5, y=0.5
                    ))

        keyframes.append(ZoomKeyframe(time=clip_duration, scale=1.0, x=0.5, y=0.5))
        keyframes.sort(key=lambda k: k.time)

        return ZoomPlan(keyframes=keyframes)