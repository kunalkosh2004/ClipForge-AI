import pytest

from clipforge.ai.gemini_provider import (
    _clamp_transcript_to_duration,
    _coerce_scene_times,
    _merge_chunk_transcripts,
    _schema_for_gemini,
    _splice_fill_into_transcript,
    _transcript_gaps,
)
from clipforge.common.ports import Transcript, TranscriptSegment, Word
from clipforge.common.times import parse_timestamp
from clipforge.directing.domain.blueprint import EditingBlueprint


def test_parse_timestamp_numeric() -> None:
    assert parse_timestamp(90) == 90.0
    assert parse_timestamp(1.5) == 1.5


def test_parse_timestamp_mmss_strings() -> None:
    assert parse_timestamp("00:45") == 45.0
    assert parse_timestamp("01:20") == 80.0
    assert parse_timestamp("1:02:30") == 3750.0


def test_parse_timestamp_invalid() -> None:
    with pytest.raises(ValueError):
        parse_timestamp("not-a-time")


def test_coerce_scene_times_converts_strings() -> None:
    data = {
        "scenes": [
            {"start": "00:00", "end": "01:30", "description": "x"},
            {"start": 10, "end": 20.5},
        ]
    }
    result = _coerce_scene_times(data)
    assert result["scenes"][0]["start"] == 0.0
    assert result["scenes"][0]["end"] == 90.0
    assert result["scenes"][1]["start"] == 10.0
    assert result["scenes"][1]["end"] == 20.5


def test_schema_for_gemini_strips_additional_properties() -> None:
    schema = _schema_for_gemini(EditingBlueprint)
    assert "additionalProperties" not in str(schema)
    assert schema["title"] == "EditingBlueprint"


def _segment(
    text: str, start: float, end: float, words: list[tuple[str, float, float]]
) -> TranscriptSegment:
    return TranscriptSegment(
        text=text,
        start=start,
        end=end,
        words=[Word(text=t, start=s, end=e) for t, s, e in words],
    )


def test_merge_chunk_transcripts_offsets_and_drops_overlap() -> None:
    # Chunk 0 covers [0,45); chunk 1 covers [42,87) (step = 42). Words in the
    # first 3s of chunk 1 re-transcribe chunk 0's tail and must be dropped.
    chunk0 = Transcript(
        language="en",
        segments=[
            _segment(
                "hello world",
                0.0,
                1.0,
                [("hello", 0.0, 0.5), ("world", 0.5, 1.0)],
            ),
            _segment(
                "tail",
                43.5,
                44.0,
                [("tail", 43.5, 44.0)],
            ),
        ],
    )
    chunk1 = Transcript(
        language="en",
        segments=[
            # overlap head (0-3s local = 42-45s global) re-transcribes "tail"
            _segment(
                "tail",
                0.5,
                1.0,
                [("tail", 0.5, 1.0)],
            ),
            _segment(
                "next part",
                4.0,
                5.0,
                [("next", 4.0, 4.5), ("part", 4.5, 5.0)],
            ),
        ],
    )

    merged = _merge_chunk_transcripts(
        [chunk0, chunk1], chunk_seconds=45.0, overlap_seconds=3.0
    )

    texts = [w.text for seg in merged.segments for w in seg.words]
    assert texts == ["hello", "world", "tail", "next", "part"]
    # chunk 1's kept words are offset by 42s; the overlap head is gone.
    next_word = next(w for seg in merged.segments for w in seg.words if w.text == "next")
    assert next_word.start == 46.0
    assert next_word.end == 46.5
    assert merged.language == "en"


def test_merge_chunk_transcripts_three_chunks_continuous() -> None:
    chunks = []
    for i in range(3):
        local_start = 4.0
        chunks.append(
            Transcript(
                language="en",
                segments=[
                    _segment(
                        f"words{i}",
                        local_start,
                        local_start + 2.0,
                        [(f"w{i}a", local_start, local_start + 1.0)],
                    )
                ],
            )
        )
    merged = _merge_chunk_transcripts(
        chunks, chunk_seconds=45.0, overlap_seconds=3.0
    )
    starts = [w.start for seg in merged.segments for w in seg.words]
    assert starts == [4.0, 46.0, 88.0]


def test_merge_chunk_transcripts_empty() -> None:
    merged = _merge_chunk_transcripts([], chunk_seconds=45.0, overlap_seconds=3.0)
    assert merged.language == "en"
    assert merged.segments == []


def test_merge_caps_stretched_word_ends() -> None:
    # Gemini stretched the final word's end across a silent tail (40s).
    chunk = Transcript(
        language="en",
        segments=[
            _segment(
                "short stretched",
                0.0,
                42.0,
                [("short", 0.0, 0.3), ("stretched", 0.3, 42.0)],
            )
        ],
    )
    merged = _merge_chunk_transcripts(
        [chunk], chunk_seconds=45.0, overlap_seconds=3.0
    )
    stretched = next(
        w for seg in merged.segments for w in seg.words if w.text == "stretched"
    )
    assert stretched.end == pytest.approx(4.3, abs=0.001)  # 0.3 start + 4s cap
    short = next(w for seg in merged.segments for w in seg.words if w.text == "short")
    assert short.end == 0.3  # normal words untouched


def test_merge_chunk_transcripts_preserves_speaker_and_text() -> None:
    chunk0 = Transcript(
        language="en",
        segments=[
            TranscriptSegment(
                text="first",
                start=0.0,
                end=1.0,
                speaker="A",
                words=[Word(text="first", start=0.0, end=1.0)],
            )
        ],
    )
    merged = _merge_chunk_transcripts(
        [chunk0], chunk_seconds=45.0, overlap_seconds=3.0
    )
    assert merged.segments[0].speaker == "A"
    assert merged.segments[0].text == "first"


def _words_transcript(*words: tuple[str, float, float], language: str = "en") -> Transcript:
    return Transcript(
        language=language,
        segments=[
            TranscriptSegment(
                text=" ".join(w[0] for w in words),
                start=words[0][1],
                end=words[-1][2],
                words=[Word(text=t, start=s, end=e) for t, s, e in words],
            )
        ],
    )


def test_transcript_gaps_detects_silent_stretches() -> None:
    transcript = _words_transcript(
        ("one", 0.0, 0.5),
        ("two", 0.5, 1.0),
        ("three", 12.0, 12.5),
    )
    assert _transcript_gaps(transcript, threshold=8.0) == [(1.0, 12.0)]
    assert _transcript_gaps(transcript, threshold=20.0) == []


def test_transcript_gaps_no_words() -> None:
    assert _transcript_gaps(Transcript(language="en", segments=[]), threshold=8.0) == []


def test_clamp_transcript_drops_words_past_duration() -> None:
    transcript = _words_transcript(
        ("before", 0.0, 0.5),
        ("inside", 250.0, 256.5),
        ("hallucinated", 300.0, 344.5),
    )
    clamped = _clamp_transcript_to_duration(transcript, duration=256.0)
    texts = [w.text for seg in clamped.segments for w in seg.words]
    assert texts == ["before", "inside"]
    # Words that end past the duration get their end clipped to the video end.
    inside = next(w for seg in clamped.segments for w in seg.words if w.text == "inside")
    assert inside.end == 256.0


def test_clamp_transcript_invalid_duration_is_noop() -> None:
    transcript = _words_transcript(("x", 0.0, 0.5))
    assert _clamp_transcript_to_duration(transcript, duration=0.0) is transcript


def test_splice_fill_replaces_gap_words() -> None:
    transcript = _words_transcript(
        ("before", 0.0, 0.5),
        ("after", 100.0, 100.5),
    )
    fill = _words_transcript(
        ("missed", 30.0, 30.4),
        ("words", 30.4, 30.8),
    )
    repaired = _splice_fill_into_transcript(
        transcript, fill, gap_start=0.5, gap_end=100.0
    )
    texts = [w.text for seg in repaired.segments for w in seg.words]
    assert texts == ["before", "missed", "words", "after"]


def test_splice_fill_drops_straddling_old_words() -> None:
    # A word that starts inside the gap margin is replaced by the fill.
    transcript = _words_transcript(
        ("before", 0.0, 0.5),
        ("straddle", 99.0, 99.5),
        ("after", 100.0, 100.5),
    )
    fill = _words_transcript(("filler", 50.0, 50.4))
    repaired = _splice_fill_into_transcript(
        transcript, fill, gap_start=0.5, gap_end=100.0
    )
    texts = [w.text for seg in repaired.segments for w in seg.words]
    assert "straddle" not in texts
    assert texts == ["before", "filler", "after"]
