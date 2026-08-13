
from clipforge.analysis.infrastructure.subtitles import segments_to_srt, segments_to_vtt


def test_srt_export() -> None:
    segments = [
        {"start": 0.0, "end": 2.5, "text": "Hello world", "confidence": 0.95},
        {"start": 2.5, "end": 5.0, "text": "Second segment", "confidence": 0.90},
    ]
    srt = segments_to_srt(segments)
    assert "1\n00:00:00,000 --> 00:00:02,500\nHello world" in srt
    assert "2\n00:00:02,500 --> 00:00:05,000\nSecond segment" in srt


def test_vtt_export() -> None:
    segments = [
        {"start": 0.0, "end": 2.5, "text": "Hello world", "confidence": 0.95},
    ]
    vtt = segments_to_vtt(segments)
    assert vtt.startswith("WEBVTT\n\n")
    assert "00:00:00.000 --> 00:00:02.500" in vtt
    assert "Hello world" in vtt


def test_srt_empty() -> None:
    srt = segments_to_srt([])
    assert srt == ""


def test_vtt_empty() -> None:
    vtt = segments_to_vtt([])
    assert vtt == "WEBVTT\n"
