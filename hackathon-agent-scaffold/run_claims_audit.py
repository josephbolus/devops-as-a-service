#!/usr/bin/env python3
"""Claims audit — submission-facing numbers vs the measured records
(maximizer iteration 51).

Every prior record was pinned when it was written, but the docs a
judge actually reads (SUBMISSION.md, README.md) accumulated layers
across 50 iterations. This runner audits them fresh, deterministically
(no API calls):

  1. Fresh demo baseline: the demo suite really runs 24/24 green.
  2. Full-bench recompute: frontier-full-bench-runs.json's summary
     (12/12 passed, growth, wall clock, cost per passed issue) is
     recomputed from its per-run rows.
  3. Submission tokens: SUBMISSION.md carries the recomputed
     full-bench figures (433.47s, $0.0326, 12/12) and labels the
     split-era $0.0254 cost figure as a split-config measurement.
  4. Contest-config framing: SUBMISSION.md's split paragraph is
     past-tense with the all-frontier supersession stated in the
     same paragraph, and README.md's META_AI_TOOLING row carries
     the supersession too (both presented the split as the current
     decision before this iteration).
  5. README baselines: the run-the-baselines block states the
     current 24-test demo baseline (it still said "6 passing"
     before this iteration — a pre-expansion leftover).

Dated historical records are NOT audited for wording and are never
altered. Outputs (repo-root eval-scorecard/):
  claims-audit.json — the measured record
  CLAIMS_AUDIT.md   — the human-readable record (render_md)
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
OUT_DIR = ROOT / "eval-scorecard"
STALE_README_TOKEN = "6 passing; the Tier-1 bug is not yet covered"


def demo_suite():
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
        cwd=ROOT / "hackathon-demo-repo", capture_output=True, text=True,
        timeout=300)
    out = proc.stderr + proc.stdout
    m = re.search(r"Ran (\d+) tests", out)
    ran = int(m.group(1)) if m else None
    return {"tests": ran, "expected": 24,
            "ok": proc.returncode == 0 and ran == 24 and "\nOK" in out}


def full_bench_recompute():
    rec = json.loads(
        (OUT_DIR / "frontier-full-bench-runs.json").read_text())
    runs = rec["runs"]
    work = [r for r in runs if r["slug"] != "guardrail"]
    passed = sum(1 for r in work if r["outcome"] == "passed")
    growth = sum(r["tests_after"] - r["tests_before"] for r in work)
    wall = round(sum(r["wall_clock_seconds"] for r in runs), 2)
    cost = round(sum(r["cost"]["total_usd_est"] for r in runs), 6)
    s = rec["summary"]
    recomputed = {
        "work_issues_passed": f"{passed}/{len(work)}",
        "guardrail_escalated":
            any(r["slug"] == "guardrail" and r["outcome"] == "escalated"
                for r in runs),
        "test_growth": growth,
        "total_wall_clock_seconds": wall,
        "total_usd_est": cost,
        "cost_per_passed_issue": round(cost / passed, 6) if passed else None,
    }
    matches = (
        recomputed["work_issues_passed"] == s["work_issues_passed"]
        and recomputed["guardrail_escalated"] == s["guardrail_escalated"]
        and recomputed["test_growth"] == s["test_growth"]
        and abs(recomputed["total_wall_clock_seconds"]
                - s["total_wall_clock_seconds"]) < 0.011
        and abs(recomputed["total_usd_est"] - s["total_usd_est"]) < 1e-6
        and abs(recomputed["cost_per_passed_issue"]
                - s["cost_per_passed_issue"]) < 1e-6)
    return {"summary": s, "recomputed": recomputed, "matches": matches}


def doc_checks():
    submission = (ROOT / "SUBMISSION.md").read_text()
    readme = (ROOT / "README.md").read_text()
    split_para = re.search(
        r"A measured per-role split experiment(.{0,600})", submission, re.S)
    split_flat = re.sub(r"\s+", " ", split_para.group(0)) if split_para else ""
    return {
        "submission_carries_full_bench_figures": all(
            t in submission for t in ("433.47s", "$0.0326", "12/12")),
        "submission_labels_split_era_cost":
            "split-config measurement" in submission,
        "submission_split_paragraph_past_tense_superseded": bool(
            "kept the split at the time" in split_flat
            and "all-frontier" in split_flat),
        "readme_tooling_row_names_supersession":
            "superseded for contest runs" in readme,
        "readme_baseline_current":
            "24 passing" in readme and STALE_README_TOKEN not in readme,
    }


def build_record():
    demo = demo_suite()
    bench = full_bench_recompute()
    docs = doc_checks()
    checks = {
        "demo_suite_fresh_24": demo["ok"],
        "full_bench_summary_recomputes": bench["matches"],
        "submission_carries_full_bench_figures":
            docs["submission_carries_full_bench_figures"],
        "submission_labels_split_era_cost":
            docs["submission_labels_split_era_cost"],
        "submission_split_framing_current":
            docs["submission_split_paragraph_past_tense_superseded"],
        "readme_tooling_row_current":
            docs["readme_tooling_row_names_supersession"],
        "readme_baseline_current": docs["readme_baseline_current"],
    }
    return {
        "record": "Claims audit -- submission-facing docs (SUBMISSION.md, "
                  "README.md) checked fresh against the measured records, "
                  "Oct 26, 2026 (maximizer iteration 51)",
        "method": "Deterministic, no API calls: fresh demo-suite run, "
                  "full-bench summary recomputed from its per-run rows, "
                  "and token/framing checks on the two judge-facing docs. "
                  "Dated historical eval records are not audited or altered.",
        "demo_suite": demo,
        "full_bench": bench,
        "docs": docs,
        "checks": checks,
        "all_checks_pass": all(checks.values()),
    }


def render_md(rec):
    b = rec["full_bench"]["recomputed"]
    lines = [
        "# Claims audit -- judge-facing docs vs the measured records "
        "(Oct 26, 2026)",
        "",
        "Maximizer iteration 51. Deterministic audit (no API calls) of",
        "the two documents a judge reads first -- SUBMISSION.md and",
        "README.md -- against the measured records, run fresh at the",
        "current repo state. Three stale current-status framings found",
        "by this audit were fixed in the same iteration (below); dated",
        "historical eval records were left unaltered.",
        "",
        "## Checks (all recomputed fresh)",
        "",
        f"- Demo suite fresh: {rec['demo_suite']['tests']} tests run, "
        f"green: {rec['demo_suite']['ok']}",
        f"- Full-bench summary recomputes from its per-run rows: "
        f"{rec['full_bench']['matches']} -- {b['work_issues_passed']} "
        f"passed, guardrail escalated {b['guardrail_escalated']}, "
        f"growth +{b['test_growth']}, {b['total_wall_clock_seconds']}s, "
        f"est. ${b['total_usd_est']:.4f} total / "
        f"${b['cost_per_passed_issue']:.4f} per passed issue",
    ]
    for name, ok in rec["checks"].items():
        lines.append(f"- {name}: {ok}")
    lines += [
        "",
        "## Stale framings fixed this iteration",
        "",
        "- README.md run-the-baselines block said the demo suite was",
        "  \"6 passing\" -- a pre-expansion leftover; the demo repo has",
        "  been 24 tests since iteration 37. It now states 24 passing",
        "  and that none of the 12 seeded defects is covered by a",
        "  baseline test.",
        "- SUBMISSION.md's Tooling section said a split experiment",
        "  \"keeps the split\" in the present tense; the all-frontier",
        "  supersession appeared paragraphs later. The paragraph now",
        "  reads past tense with the supersession in the same",
        "  paragraph, and README.md's META_AI_TOOLING row names the",
        "  supersession too.",
        "- SUBMISSION.md's Impact section quoted the $0.0254 per-issue",
        "  cost without its configuration; it is now labeled a",
        "  split-config measurement (the contest configuration's",
        "  full-bench figure, $0.0326, is carried in the same draft).",
        "",
        "## Verdict",
        "",
        f"All checks pass: {rec['all_checks_pass']}. The judge-facing",
        "docs now state the current baseline, the current contest",
        "configuration, and configuration-labeled costs wherever the",
        "audited figures appear.",
        "",
        "Honest limits: this audits the figures and framings listed",
        "above, not every number ever written in the repo; dated",
        "historical records keep their then-current wording by",
        "design. Consistency verification, not model performance.",
        "",
    ]
    return "\n".join(lines)


def main():
    rec = build_record()
    (OUT_DIR / "claims-audit.json").write_text(
        json.dumps(rec, indent=1) + "\n")
    (OUT_DIR / "CLAIMS_AUDIT.md").write_text(render_md(rec))
    print(json.dumps(rec, indent=1))
    return 0 if rec["all_checks_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
