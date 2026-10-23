import unittest
import urllib.error

from app.http_client import HttpError, get
from app.pagination import paginate
from app.report import human_report


class PaginationBaseline(unittest.TestCase):
    def test_partial_last_page(self):
        # 25 items, page size 10 -> page 3 has the final 5.
        self.assertEqual(paginate(list(range(25)), 3, 10), list(range(20, 25)))

    def test_page_past_end_is_empty(self):
        self.assertEqual(paginate(list(range(5)), 4, 10), [])

    def test_page_is_one_indexed(self):
        with self.assertRaises(ValueError):
            paginate([1, 2, 3], 0, 2)


class HttpClientBaseline(unittest.TestCase):
    def test_get_success(self):
        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b"hello"
        self.assertEqual(get("http://x", opener=lambda url: Resp()), "hello")

    def test_4xx_raises_http_error(self):
        def opener(url):
            raise urllib.error.HTTPError(url, 400, "bad request", None, None)
        with self.assertRaises(HttpError) as ctx:
            get("http://x", opener=opener)
        self.assertEqual(ctx.exception.status, 400)


class ReportBaseline(unittest.TestCase):
    def test_human_report_shape(self):
        out = human_report()
        self.assertIn("demo-api", out)
        self.assertIn("database", out)


if __name__ == "__main__":
    unittest.main()
