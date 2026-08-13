from abc import ABC, abstractmethod

from clipforge.rendering.domain.framing import FramingPlan, TrackPoint


class FramingAnalyzer(ABC):
    @abstractmethod
    def analyze(
        self,
        source_path: str,
        source_width: int,
        source_height: int,
    ) -> list[TrackPoint]:
        """Subject-center track (normalized coords, seconds from clip start).

        Empty list means no subject could be tracked — callers fall back to a
        center crop. This is a blocking call; run it in a worker thread.
        """


class CaptionRenderer(ABC):
    @abstractmethod
    async def render_captions(
        self,
        source_path: str,
        ass_path: str,
        output_path: str,
        width: int | None = None,
        height: int | None = None,
        framing: FramingPlan | None = None,
    ) -> None:
        """Burn the subtitles from an ASS file into the source clip.

        When width/height are given, the source is first scaled/cropped onto
        the target canvas (portrait canvases cover-crop, landscape canvases
        contain-pad) so the ASS PlayRes matches the output. A framing plan
        replaces the portrait center-crop with a subject-tracking crop.
        """
