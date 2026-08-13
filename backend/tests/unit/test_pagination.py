

from clipforge.common.pagination import PageRequest, PageResult


def test_page_request_defaults() -> None:
    p = PageRequest()
    assert p.limit == 20
    assert p.offset == 0


def test_page_request_custom() -> None:
    p = PageRequest(limit=10, offset=20)
    assert p.limit == 10
    assert p.offset == 20


def test_page_result_has_more() -> None:
    result = PageResult(
        items=["a", "b", "c"],
        total=5,
        limit=3,
        offset=0,
    )
    assert result.has_more is True


def test_page_result_no_more() -> None:
    result = PageResult(
        items=["a", "b", "c"],
        total=3,
        limit=10,
        offset=0,
    )
    assert result.has_more is False


def test_page_result_empty() -> None:
    result = PageResult(items=[], total=0, limit=10, offset=0)
    assert result.has_more is False
    assert len(result.items) == 0
