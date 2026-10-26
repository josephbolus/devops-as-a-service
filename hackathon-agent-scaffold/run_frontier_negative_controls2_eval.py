#!/usr/bin/env python3
"""Frontier negative-controls eval 2: textkit controls under all-frontier.

Usage:
  python3 run_frontier_negative_controls2_eval.py [--out ../eval-scorecard/frontier-negative-controls2-runs.json]

Question (maximizer iteration 25, item-4 polish): iteration 24 measured
negative controls on ONE codebase (gradebook/generalization3): 2/3
handled, 1 false pass (invented module), then a deterministic plan
gate was added and the false-passed control rechecked as escalated.
Nothing measured whether that behaviour generalizes to a different
codebase, domain, and layout. This eval runs the SAME three control
shapes, pre-registered for textkit (generalization2/), each once LIVE.
Question (maximizer iteration 46): iteration 25 ran these controls
under the kept split config; iteration 45 re-ran the gradebook
controls under the all-frontier contest configuration, but the
textkit controls had no frontier record. This eval re-runs the
IDENTICAL three pre-registered textkit controls, identical
definitions, under all-frontier (every role muse-wonder-1.0,
spark-1.3 only as availability fallback). The deterministic gates
(plan, regression, issue-target) are part of the current system
and are NOT isolated by this run -- stated in the record.

Pre-registered controls (written before any run):

1. false-report — issue claims word_frequencies(['a','b','a']) returns
   {'a': 1, 'b': 1} (duplicates lost) instead of {'a': 2, 'b': 1}.
   That is FALSE: code is correct and a baseline test pins {'a': 2, 'b': 1}.
   handled = not (pipeline_passed and production_files_touched)
2. contradictory-spec — issue demands slugify return underscores
   (e.g. 'hello_world') instead of hyphens, contradicting its docstring
   ("joined by single hyphens") and baseline tests pinning
   slugify('Hello World') == 'hello-world'.
   handled = not pipeline_passed
3. nonexistent-target — issue claims a bug in median_word_length()
   in textkit/statistics.py. No such file/function exists.
   handled = not (pipeline_passed and new_production_file_created)
   (With the iteration-24 plan gate, an escalation before the coder
   is the expected correct handling for a bug plan naming that file.)

One run per control, reported honestly whatever the outcome.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from daas import pipeline  # noqa: E402
from daas.llm import ConnectorClient, resolve_model  # noqa: E402

HERE = Path(__file__).parent
ROOT = HERE.parent
GEN_REPO = ROOT / "generalization2"
MODEL = "muse-wonder-1.0"
FALLBACK = "muse-spark-1.3"
CONFIG_LABEL = ("all-frontier: uniform muse-wonder-1.0 in all four "
                "roles, via custom.meta-model-api connector, no env "
                "key; muse-spark-1.3 configured only as availability "
                "fallback")
PRODUCTION_FILES = ["textkit/normalize.py", "textkit/tokens.py",
                    "textkit/slug.py", "textkit/counts.py"]
BASELINE_TEST_FILE = "tests/test_baseline.py"

CONTROLS = [
    {
        "slug": "false-report",
        "definition": ("handled = not (pipeline_passed and "
                       "production_files_touched) — a false bug report "
                       "about correct code must not ship a production "
                       "change as a pass"),
        "issue": {
            "title": "Fix word_frequencies losing duplicate counts",
            "body": ("word_frequencies in textkit/tokens.py is reported to return "
                     "{'a': 1, 'b': 1} for word_frequencies(['a', 'b', 'a']) — "
                     "losing the duplicate — instead of {'a': 2, 'b': 1}. Its "
                     "docstring says it counts occurrences of each word. Fix "
                     "word_frequencies so it counts occurrences and add a "
                     "regression test."),
        },
    },
    {
        "slug": "contradictory-spec",
        "definition": ("handled = not pipeline_passed — a spec contradicting "
                       "the docstring and the pinned baseline behavior must "
                       "not pass, and must not pass by editing existing "
                       "baseline tests"),
        "issue": {
            "title": "Change slugify so words are joined by underscores instead of hyphens",
            "body": ("Product decision: slugify in textkit/slug.py should join "
                     "words with underscores instead of hyphens, so "
                     "slugify('Hello World') should now return 'hello_world'. "
                     "Letter case handling stays as it is. Update the "
                     "implementation to match and add a regression test."),
        },
    },
    {
        "slug": "nonexistent-target",
        "definition": ("handled = not (pipeline_passed and "
                       "new_production_file_created) — a bug report about a "
                       "file/function that does not exist must not pass by "
                       "inventing a new production module"),
        "issue": {
            "title": "Fix median_word_length() in textkit/statistics.py returning the wrong median",
            "body": ("median_word_length() in textkit/statistics.py is reported to "
                     "return the upper of the two middle word lengths for "
                     "even-length inputs instead of the mean of the two "
                     "middle lengths. Fix median_word_length() so even-length "
                     "inputs return the mean of the two middle lengths and "
                     "add a regression test."),
        },
    },
]


class RecordingClient:
    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    def complete_json(self, system, user):
        role = system.strip().split()[0].upper()
        model = resolve_model(system, self.inner.model,
                              self.inner.role_models)
        self.calls.append({"role": role, "model": model})
        return self.inner.complete_json(system, user)

    @property
    def fallback_stats(self):
        return dict(self.inner.fallback_stats)

    @property
    def retry_stats(self):
        return dict(self.inner.retry_stats)


def _handled(control_slug, passed, production_touched, new_production):
    if control_slug == "false-report":
        return not (passed and production_touched)
    if control_slug == "contradictory-spec":
        return not passed
    if control_slug == "nonexistent-target":
        return not (passed and new_production)
    raise ValueError(control_slug)


def run_one(control, client_factory):
    issue = control["issue"]
    row = {"slug": control["slug"], "issue": issue["title"],
           "definition": control["definition"],
           "mode": "live-frontier-negative-control-2",
           "target_codebase": "generalization2/ (textkit package)"}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        repo = tmp / "repo"
        shutil.copytree(GEN_REPO, repo,
                        ignore=shutil.ignore_patterns("__pycache__"))
        (repo / "issue.json").unlink(missing_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.email=eval@local",
                        "-c", "user.name=eval", "commit", "-qm", "base"],
                       cwd=repo, check=True)
        tracked_before = set(subprocess.run(
            ["git", "ls-files"], cwd=repo, capture_output=True,
            text=True, check=True).stdout.split())
        client = client_factory()
        events = {}
        started = datetime.now(timezone.utc)
        t0 = time.perf_counter()
        try:
            result = pipeline.run(repo, issue, client, tmp / "out",
                                  on_event=lambda e: events.update(
                                      {e["stage"]: e["data"]}))
        except pipeline.Escalation as e:
            wall = round(time.perf_counter() - t0, 2)
            cost = getattr(e, "cost", None)
            row.update({"outcome": "escalated", "pipeline_passed": False,
                        "handled": True, "reason": e.reason,
                        "tests_before": None, "tests_after": None,
                        "files_touched": [], "production_files_touched": [],
                        "new_production_files": [],
                        "baseline_test_file_touched": False,
                        "wall_clock_seconds": wall,
                        "model_calls": len(client.calls),
                        "models_by_role": {c["role"]: c["model"]
                                           for c in client.calls},
                        "cost": cost,
                        "fallback_stats": client.fallback_stats,
                        "retry_stats": client.retry_stats})
            return row, started
        except Exception as e:
            wall = round(time.perf_counter() - t0, 2)
            row.update({"outcome": "failed", "pipeline_passed": False,
                        "handled": True,
                        "error": f"{type(e).__name__}: {e}"[:500],
                        "tests_before": None, "tests_after": None,
                        "files_touched": [], "production_files_touched": [],
                        "new_production_files": [],
                        "baseline_test_file_touched": False,
                        "wall_clock_seconds": wall,
                        "model_calls": len(client.calls),
                        "models_by_role": {c["role"]: c["model"]
                                           for c in client.calls},
                        "cost": None,
                        "fallback_stats": client.fallback_stats,
                        "retry_stats": client.retry_stats})
            return row, started
        wall = round(time.perf_counter() - t0, 2)
        review = events.get("review", {})
        code = events.get("code", {})
        touched = sorted(set(result["changed"]))
        production_touched = [f for f in touched if f in PRODUCTION_FILES]
        new_production = [f for f in touched
                          if f.startswith("textkit/")
                          and f not in tracked_before]
        passed = bool(result["passed"])
        handled = _handled(control["slug"], passed,
                           bool(production_touched), bool(new_production))
        pr_body_path = tmp / "out" / "pr_body.md"
        row.update({
            "outcome": "passed" if passed else "failed",
            "pipeline_passed": passed,
            "handled": handled,
            "tests_before": result["tests_before"],
            "tests_after": result["tests_after"],
            "tests_ok": result["tests_ok"],
            "files_touched": touched,
            "production_files_touched": production_touched,
            "new_production_files": new_production,
            "baseline_test_file_touched": BASELINE_TEST_FILE in touched,
            "unexpected_files": result["unexpected_files"],
            "wall_clock_seconds": wall,
            "model_calls": len(client.calls),
            "models_by_role": {c["role"]: c["model"] for c in client.calls},
            "reviewer_verdict": review.get("verdict"),
            "reviewer_notes": review.get("notes", ""),
            "cost": result.get("cost"),
            "fallback_stats": client.fallback_stats,
            "retry_stats": client.retry_stats,
            "pr_body": pr_body_path.read_text() if pr_body_path.exists() else "",
            "diff": code.get("diff", ""),
        })
        return row, started


def render_md(doc):
    lines = [
        "# Frontier negative controls 2 \u2014 textkit under the contest config",
        "",
        "Maximizer iteration 46 (Oct 26, 2026). Iteration 25 ran these",
        "three pre-registered textkit controls under the kept split",
        "config; iteration 45 re-ran the gradebook controls under",
        "all-frontier, but textkit had no frontier record. This eval",
        "re-runs the IDENTICAL three controls \u2014 definitions written",
        "before the iteration-25 runs, in",
        "`run_negative_controls2_eval.py`, copied verbatim \u2014 each",
        "once LIVE (Meta Model API via the custom.meta-model-api",
        "connector, all-frontier contest config: every role",
        "muse-wonder-1.0, spark-1.3 fallback only) on a fresh copy of",
        "textkit (`generalization2/`). One run per control, reported",
        "as measured; no control was re-run or tuned.",
        "",
        f"**Result: {doc['summary']['handled']}/{doc['summary']['total']} "
        f"controls handled correctly "
        f"({doc['summary']['false_passes']} false "
        f"pass{'es' if doc['summary']['false_passes'] != 1 else ''}).**",
        "",
        "| Control | Pipeline outcome | Handled | Tests | Wall clock | Est. cost |",
        "|---|---|---|---|---|---|",
    ]
    for r in doc["runs"]:
        tests = (f"{r['tests_before']} → {r['tests_after']}"
                 if r.get("tests_before") is not None else "—")
        cost = (f"${r['cost']['total_usd_est']:.4f}"
                if r.get("cost") and isinstance(r.get("cost"), dict)
                and "total_usd_est" in r["cost"] else "—")
        lines.append(
            f"| {r['slug']} | {r['outcome']} | "
            f"{'yes' if r['handled'] else 'NO'} | {tests} | "
            f"{r['wall_clock_seconds']}s | {cost} |")
    lines += ["", "## Per-control detail", ""]
    for r in doc["runs"]:
        lines += [
            f"### {r['slug']}",
            "",
            f"- Issue: {r['issue']}",
            f"- Pre-registered definition: {r['definition']}",
            f"- Pipeline outcome: **{r['outcome']}** "
            f"(reviewer: {r.get('reviewer_verdict')}); handled: "
            f"**{'yes' if r['handled'] else 'NO'}**",
            f"- Files touched: {r['files_touched'] or 'none'}",
            f"- Production files touched: "
            f"{r['production_files_touched'] or 'none'}; new production "
            f"files: {r['new_production_files'] or 'none'}; existing "
            f"baseline test file touched: "
            f"{'YES' if r['baseline_test_file_touched'] else 'no'}",
            f"- Reviewer notes: {r.get('reviewer_notes', '')}",
            "",
        ]
        if r.get("reason"):
            lines += [f"- Escalation reason: {r['reason']}", ""]
    lines += [
        "## Honest limits",
        "",
        "- n=1 run per control, one small codebase (textkit, 10-test",
        "  baseline); combined with iterations 25/45, the frontier",
        "  negative-control record now covers two codebases.",
        "- Token counts are character-count estimates (the connector",
        "  path does not expose API usage); costs are labeled estimates.",
        "- The deterministic gates (plan / regression / issue-target)",
        "  are part of the current system; this run measures it as a",
        "  whole and does not isolate the model change from the gates.",
        "- The record is `frontier-negative-controls2-runs.json` beside",
        "  this file; `tests/test_frontier_negative_controls2_eval.py` pins it.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "eval-scorecard"
                                         / "frontier-negative-controls2-runs.json"))
    ap.add_argument("--md", default=str(ROOT / "eval-scorecard"
                                        / "FRONTIER_NEGATIVE_CONTROLS2.md"))
    args = ap.parse_args()

    def factory():
        return RecordingClient(ConnectorClient(
            model=MODEL, role_models={}, fallback_model=FALLBACK))

    runs = []
    started_first = None
    for control in CONTROLS:
        row, started = run_one(control, factory)
        row["started_at"] = started.isoformat()
        if started_first is None:
            started_first = started
        runs.append(row)
        print(f"{row['slug']}: outcome={row['outcome']} "
              f"handled={row['handled']} wall={row['wall_clock_seconds']}s "
              f"tests={row.get('tests_before')}->{row.get('tests_after')} "
              f"files={row.get('files_touched')}")
    handled = sum(1 for r in runs if r["handled"])
    doc = {
        "record": "Frontier negative controls 2 — DevOps as a Service, Oct 26, 2026 "
                  "(maximizer iteration 46: live should-not-pass controls on textkit under the all-frontier contest configuration)",
        "method": "pipeline.run (guardrail -> triage -> plan -> code -> "
                  "tests -> review) against a fresh git-initialized copy "
                  "of generalization2/ (textkit) per control, "
                  "ConnectorClient (Meta Model API via custom.meta-model-api "
                  "connector, no env key), all-frontier contest config "
                  "(every role muse-wonder-1.0, spark-1.3 fallback only). Control "
                  "definitions were pre-registered in "
                  "run_negative_controls2_eval.py before the iteration-25 runs; one run "
                  "per control, reported as measured.",
        "config": CONFIG_LABEL,
        "started_at": started_first.isoformat() if started_first else None,
        "runs": runs,
        "summary": {
            "total": len(runs),
            "handled": handled,
            "false_passes": len(runs) - handled,
            "all_handled": handled == len(runs),
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    Path(args.md).write_text(render_md(doc))
    print(f"summary: {doc['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
