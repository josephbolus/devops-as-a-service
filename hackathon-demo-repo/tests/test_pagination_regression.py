from app.pagination import paginate


def test_paginate_full_last_page_returns_page_size_items():
    result = paginate(list(range(20)), 2, 10)
    assert result == list(range(10, 20))
    assert len(result) == 10
