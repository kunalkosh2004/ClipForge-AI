import pytest

from clipforge.videos.infrastructure.youtube import (
    extract_youtube_id,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s",
        "http://m.youtube.com/watch?v=dQw4w9WgXcQ",
    ],
)
def test_extract_youtube_id_valid(url: str) -> None:
    assert extract_youtube_id(url) == "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://vimeo.com/12345",
        "https://youtube.com/watch",
        "https://youtube.com/watch?v=too-short",
        "not a url",
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "ftp://youtube.com/watch?v=dQw4w9WgXcQ",
    ],
)
def test_extract_youtube_id_invalid(url: str) -> None:
    assert extract_youtube_id(url) is None


def test_extract_youtube_id_whitespace() -> None:
    assert extract_youtube_id("  https://youtu.be/dQw4w9WgXcQ  ") == "dQw4w9WgXcQ"


def test_downloader_picks_largest_video(tmp_path) -> None:
    (tmp_path / "video.mp4").write_bytes(b"a" * 100)
    (tmp_path / "video.webm").write_bytes(b"b" * 200)
    (tmp_path / "notes.txt").write_text("ignored")
    from clipforge.videos.infrastructure.youtube import _find_largest_video

    result = _find_largest_video(tmp_path)
    assert result is not None
    assert result.suffix == ".webm"
