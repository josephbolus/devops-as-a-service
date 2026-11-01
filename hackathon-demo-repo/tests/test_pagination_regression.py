"""Regression test for pagination off-by-one."""
import unittest

from app.pagination import paginate


class TestPaginationRegression(unittest.TestCase):
    def test_full_second_page_returns_ten_items(self):
        result = paginate(list(range(20)), 2, 10)
        self.assertEqual(result, list(range(10, 20)))
        self.assertEqual(len(result), 10)

    def test_full_first_page_returns_ten_items(self):
        result = paginate(list(range(20)), 1, 10)
        self.assertEqual(result, list(range(10)))
        self.assertEqual(len(result), 10)


if __name__ == "__main__":
    unittest.main()
