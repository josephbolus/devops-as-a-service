"""Baseline tests for expansion batch 2 modules (#6/#7/#12).

Pin only correct-today behavior; each defect case is uncovered,
like the Tier-1 and batch-1 seeds. All pass with the bugs present.
"""
import tempfile
import unittest
from pathlib import Path

from app.logwriter import LogWriter
from app.pool import ConnectionPool
from app.scheduler import run_once


class PoolBaseline(unittest.TestCase):
    def test_successful_run_releases_connection(self):
        pool = ConnectionPool(max_size=1)
        self.assertEqual(pool.run(lambda c: "ok"), "ok")
        self.assertEqual(pool.in_use, 0)
        # Pool is reusable after a success.
        self.assertEqual(pool.run(lambda c: "again"), "again")

    def test_manual_acquire_release(self):
        pool = ConnectionPool(max_size=1)
        conn = pool.acquire()
        self.assertEqual(pool.in_use, 1)
        pool.release(conn)
        self.assertEqual(pool.in_use, 0)


class LogWriterBaseline(unittest.TestCase):
    def test_write_appends_lines(self):
        with tempfile.TemporaryDirectory() as d:
            w = LogWriter(Path(d) / "svc.log", max_bytes=1024)
            w.write("first")
            w.write("second")
            self.assertEqual((Path(d) / "svc.log").read_text(),
                             "first\nsecond\n")

    def test_current_size(self):
        with tempfile.TemporaryDirectory() as d:
            w = LogWriter(Path(d) / "svc.log", max_bytes=1024)
            self.assertEqual(w.current_size(), 0)
            w.write("abc")
            self.assertEqual(w.current_size(), 4)


class SchedulerBaseline(unittest.TestCase):
    def test_successful_run_marks_completed(self):
        state = {}
        self.assertEqual(run_once(state, "2026-10-26", lambda: None), "ran")
        self.assertEqual(state.get("last_completed"), "2026-10-26")

    def test_already_completed_skips(self):
        calls = []
        state = {"last_completed": "2026-10-26"}
        out = run_once(state, "2026-10-26", lambda: calls.append(1))
        self.assertEqual(out, "already-ran")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
