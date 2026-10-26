"""Pipeline: issue in -> triage -> planner -> coder -> tests -> reviewer -> PR body out.

The pipeline itself stops at a written PR body (pr_body.md) plus the list
of changed files, so the whole loop is testable offline with no GitHub
side effects. run_pr.py wraps it with the real branch/commit/PR steps.
The agents receive real context: the planner sees the repo file tree,
the coder sees the current contents of the planned files (its edits
must quote them verbatim), and the reviewer sees the actual diff.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from . import approval
from . import cost as cost_mod
from . import guardrail
from . import prompts
from .llm import MockClient, resolve_model


class Escalation(RuntimeError):
    def __init__(self, reason, cost=None):
        super().__init__(reason)
        self.reason = reason
        # Cost summary of the calls made before escalating — for the
        # guardrail path this is always the zero summary (the guardrail
        # runs before any model call, by design).
        self.cost = cost


def _model_for(client, system):
    """Model that will serve this call, walking wrapper clients.

    MockClient (and subclasses / wrappers around it) report "mock";
    a client exposing .model/.role_models resolves per-role exactly
    like the llm layer does; anything else is recorded as "unknown"
    (priced at the default model's rates by daas.cost, and visible
    as unknown in the record rather than dressed up as a real model).
    """
    obj = client
    while obj is not None:
        if isinstance(obj, MockClient):
            return "mock"
        model = getattr(obj, "model", None)
        if model:
            return resolve_model(system, model,
                                 getattr(obj, "role_models", None) or {})
        obj = getattr(obj, "inner", None)
    return "unknown"


def _call(client, system, user, calls_log):
    """One model call, with its per-role cost record appended.

    Token usage is not exposed by the connector path (see daas/cost.py),
    so the record is a character-count estimate unless the client ever
    surfaces real usage — purely observational, like on_event.
    """
    response = client.complete_json(system, user)
    calls_log.append(cost_mod.record_call(
        cost_mod.role_from_system(system), _model_for(client, system),
        system, user, response))
    return response


def _repo_tree(repo: Path):
    """Repo-relative file paths, skipping noise — the planner's map."""
    skip = {".git", "__pycache__", ".pytest_cache"}
    out = []
    for p in sorted(repo.rglob("*")):
        if p.is_file() and not any(part in skip for part in p.parts):
            out.append(str(p.relative_to(repo)))
    return out


def _file_contents(repo: Path, files):
    """Current contents of the planned files that already exist."""
    out = {}
    for name in files:
        path = repo / name
        if path.is_file():
            out[name] = path.read_text()
    return out


def _diff(repo: Path, changed):
    """Unified diff of the changed files when the repo is under git.

    `git diff` never shows untracked files, and the coder's regression
    test is usually a brand-new file — synthesize a new-file block for
    those so the reviewer can actually verify the coverage.
    """
    proc = subprocess.run(["git", "-C", str(repo), "diff", "--", *changed],
                          capture_output=True, text=True, cwd=str(repo))
    out = proc.stdout if proc.returncode == 0 else ""
    listed = subprocess.run(["git", "-C", str(repo), "ls-files", "--", *changed],
                            capture_output=True, text=True, cwd=str(repo))
    tracked = set(listed.stdout.split()) if listed.returncode == 0 else set()
    for name in changed:
        path = repo / name
        if name not in tracked and path.is_file():
            body = "".join(f"+{line}\n" for line in path.read_text().splitlines())
            out += f"\n--- new file: {name} ---\n{body}"
    return out


def _apply_edits(repo: Path, edits):
    changed = []
    for edit in edits:
        path = repo / edit["file"]
        if edit["old"] is None:  # create new file
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(edit["new"])
        else:
            text = path.read_text()
            if edit["old"] not in text:
                raise RuntimeError(f"Coder edit does not apply cleanly to {edit['file']}")
            path.write_text(text.replace(edit["old"], edit["new"], 1))
        changed.append(edit["file"])
    return changed


def _run_tests(repo: Path):
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
        cwd=repo, capture_output=True, text=True)
    log = (proc.stdout + proc.stderr).strip()
    m = re.search(r"Ran (\d+) test", log)
    return proc.returncode == 0, log, int(m.group(1)) if m else 0


def _is_test_file(name):
    return "/test" in name or name.startswith("test")


def _purge_pycache(repo: Path):
    for cache in sorted(repo.rglob("__pycache__"), reverse=True):
        if ".git" not in cache.parts:
            import shutil
            shutil.rmtree(cache, ignore_errors=True)


def _snapshot(repo: Path, files):
    out = {}
    for name in files:
        if name in out:
            continue
        path = repo / name
        out[name] = path.read_text() if path.is_file() else None
    return out


def _restore(repo: Path, snapshot):
    for name, text in snapshot.items():
        path = repo / name
        if text is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    _purge_pycache(repo)


def regression_gate(repo, baseline, after, changed):
    """Deterministic regression verification (maximizer iteration 26).

    Added after iterations 24-25 measured that a FALSE bug report was
    stopped only by the reviewer on two codebases: the coder's new
    tests asserted behaviour the baseline already had, so they passed
    on the unfixed code too. A regression test that passes on the
    baseline proves nothing about the claimed bug. This gate restores
    the changed PRODUCTION files to their baseline contents (test
    files stay as the coder left them), re-runs the suite, and
    restores the fix. Applicable only when both production and test
    files changed; the run may pass only if the suite FAILS on the
    baseline. Purely deterministic — no model call is involved.
    """
    test_files = sorted({f for f in changed if _is_test_file(f)})
    prod_files = sorted({f for f in changed if not _is_test_file(f)})
    if not test_files or not prod_files:
        return {"applicable": False, "passed": True,
                "tests_ok_on_baseline": None, "tests_on_baseline": None,
                "reason": "no production+test change pair to verify"}
    prod_baseline = {f: baseline.get(f) for f in prod_files}
    prod_after = {f: after.get(f) for f in prod_files}
    try:
        _restore(repo, prod_baseline)
        ok, _log, count = _run_tests(repo)
    finally:
        _restore(repo, prod_after)
    return {"applicable": True, "passed": not ok,
            "tests_ok_on_baseline": ok, "tests_on_baseline": count,
            "reason": ("suite fails on baseline production code, so the "
                       "new tests demonstrate the claimed change"
                       if not ok else
                       "suite passes on baseline production code, so the "
                       "new tests do not demonstrate any change — the "
                       "claimed bug is not reproduced by them")}


def _function_segments(text):
    """{function_name: source segment} for a Python source text."""
    import ast
    try:
        tree = ast.parse(text or "")
    except SyntaxError:
        return {}
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seg = ast.get_source_segment(text or "", node)
            if seg is not None:
                out[node.name] = seg
    return out


def issue_target_gate(issue, repo_functions, baseline, after, changed):
    """Deterministic issue-target verification (maximizer iteration 27).

    Added after the regression-gate-2 eval measured a new false-pass
    shape on gradebook: the issue falsely claimed simple_mean was
    broken, the coder instead fixed weighted_mean — a genuine bug in
    the same file — and its new tests failed on the baseline, so the
    regression gate verified a real change and the run passed without
    ever touching the function the issue was about. A pass must
    address the issue's named target, not just any real bug nearby.

    `repo_functions` is the set of function names defined in the
    repo's non-test Python files BEFORE the run. Targets = the subset
    named (as whole words) in the issue title/body. Changed functions
    = functions in changed production files whose source segment
    differs between the baseline and after snapshots (a brand-new
    production file counts all its functions as changed). Applicable
    only when the issue names at least one existing function and a
    production file changed; a run may pass only if at least one
    named target was actually changed. Purely deterministic.
    """
    prod_changed = sorted({f for f in changed
                           if not _is_test_file(f) and f.endswith(".py")})
    text = ((issue.get("title") or "") + "\n" + (issue.get("body") or ""))
    mentioned = sorted({name for name in repo_functions
                        if re.search(r"\b" + re.escape(name) + r"\b", text)})
    if not prod_changed or not mentioned:
        return {"applicable": False, "passed": True,
                "mentioned_targets": mentioned, "changed_functions": [],
                "reason": ("issue names no existing function, or no "
                           "production code changed — nothing to verify "
                           "the target against")}
    changed_functions = set()
    for name in prod_changed:
        before = _function_segments(baseline.get(name) or "")
        after_segs = _function_segments(after.get(name) or "")
        for fn, seg in after_segs.items():
            if before.get(fn) != seg:
                changed_functions.add(fn)
        for fn in before:
            if fn not in after_segs:
                changed_functions.add(fn)
    hit = sorted(set(mentioned) & changed_functions)
    return {"applicable": True, "passed": bool(hit),
            "mentioned_targets": mentioned,
            "changed_functions": sorted(changed_functions),
            "reason": (f"the fix changes the issue's named target(s): "
                       f"{', '.join(hit)}" if hit else
                       f"the issue names {', '.join(mentioned)} but the "
                       f"production change touches only "
                       f"{', '.join(sorted(changed_functions)) or 'no function'} "
                       f"— an off-target fix, however real, does not "
                       f"answer this issue")}


def _repo_function_names(repo, repo_tree):
    names = set()
    for name in repo_tree:
        if name.endswith(".py") and not _is_test_file(name):
            path = repo / name
            if path.is_file():
                names.update(_function_segments(path.read_text()))
    return names


def invented_production_files(plan, repo_tree, triage):
    """Planned non-test files that do not exist in the repo.

    Added Oct 25 (maximizer iteration 24) after the negative-controls
    eval measured a false pass: for an issue reporting a bug in a
    non-existent gradebook/statistics.py, the planner named that file,
    the coder created it, and the reviewer approved — the pipeline
    "fixed" a target it had invented. A bug report is about existing
    behavior, so for kind == "bug" a planned production file that is
    not in the tree is not a fix plan; it is a hallucinated target.
    Feature requests are exempt (creating a module can be the work),
    and new test files are always exempt (regression tests are new).
    """
    if (triage or {}).get("kind") != "bug":
        return []
    tree = set(repo_tree)
    return [f for f in plan.get("expected_files", [])
            if f not in tree and not _is_test_file(f)]


def _emit(on_event, stage, data):
    if on_event is not None:
        on_event({"stage": stage, "data": data})


def run(repo, issue, client, out_dir, on_event=None):
    """issue: dict with title/body. Returns result dict; raises Escalation.

    on_event, when given, is called with {"stage": ..., "data": {...}}
    dicts as the run progresses (guardrail/triage/plan/code/tests/
    review/done) — the demo console renders these live. Purely
    observational: it never changes the run's behavior.
    """
    repo = Path(repo)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    blocked, reason = guardrail.check(issue["title"], issue.get("body", ""))
    if blocked:
        request = approval.build_request(issue, reason)
        (out_dir / "escalation.md").write_text(approval.render_markdown(request))
        (out_dir / "approval_request.json").write_text(approval.to_json(request))
        _emit(on_event, "guardrail", {"blocked": True, "reason": reason,
                                      "request": request})
        raise Escalation(reason, cost=cost_mod.summarize([]))
    _emit(on_event, "guardrail", {"blocked": False})

    calls_log = []
    triage = _call(client, prompts.TRIAGE, json.dumps(issue), calls_log)
    _emit(on_event, "triage", triage)
    repo_tree = _repo_tree(repo)
    repo_functions = _repo_function_names(repo, repo_tree)
    plan = _call(client, prompts.PLANNER,
                 json.dumps({"issue": issue, "triage": triage,
                             "repo_tree": repo_tree}), calls_log)
    _emit(on_event, "plan", plan)
    invented = invented_production_files(plan, repo_tree, triage)
    if invented:
        # Deterministic plan gate (iteration 24): escalate BEFORE the
        # coder runs — the pipeline must not create the very target a
        # bug report claims is broken. Triage/planner calls already
        # made are costed on the Escalation, unlike the guardrail path
        # (which by design has made zero calls at this point).
        reason = ("plan targets non-existent production file(s) for a "
                  "bug report: " + ", ".join(sorted(invented)) +
                  " — a bug fix must change existing code; escalating "
                  "for human review instead of inventing the target")
        (out_dir / "escalation.md").write_text(
            "# Escalated by the plan gate\n\n" + reason + "\n")
        _emit(on_event, "plan_gate", {"blocked": True, "reason": reason,
                                      "invented_files": sorted(invented)})
        raise Escalation(reason, cost=cost_mod.summarize(calls_log))
    _, _, tests_before = _run_tests(repo)
    coder = _call(client, prompts.CODER,
                  json.dumps({"issue": issue, "plan": plan,
                              "files": _file_contents(
                                  repo, plan.get("expected_files", []))}), calls_log)
    baseline_snapshot = _snapshot(repo, [e["file"] for e in coder["edits"]])
    changed = _apply_edits(repo, coder["edits"])
    after_snapshot = _snapshot(repo, changed)
    diff = _diff(repo, changed)
    _emit(on_event, "code", {"changed": changed, "diff": diff})

    tests_ok, test_log, tests_after = _run_tests(repo)
    _emit(on_event, "tests", {"tests_ok": tests_ok, "tests_before": tests_before,
                              "tests_after": tests_after,
                              "test_log_tail": test_log[-400:]})
    gate = regression_gate(repo, baseline_snapshot, after_snapshot, changed)
    _emit(on_event, "regression_gate", gate)
    target_gate = issue_target_gate(issue, repo_functions,
                                    baseline_snapshot, after_snapshot, changed)
    _emit(on_event, "target_gate", target_gate)
    review = _call(client, prompts.REVIEWER,
                   json.dumps({"changed": changed, "tests_ok": tests_ok,
                               "tests_before": tests_before,
                               "tests_after": tests_after,
                               "regression_gate": gate,
                               "target_gate": target_gate,
                               "diff": diff}), calls_log)
    _emit(on_event, "review", review)

    unexpected = sorted(set(changed) - set(plan.get("expected_files", changed)))
    test_files_changed = [f for f in changed if "/test" in f or f.startswith("test")]
    # A changed test file only counts as coverage if tests actually ran:
    # the discovered-test count must grow past the pre-fix baseline.
    coverage_live = not test_files_changed or tests_after > tests_before
    passed = (tests_ok and coverage_live and gate["passed"]
              and target_gate["passed"]
              and review.get("verdict") == "approve" and not unexpected)
    pr_body = (
        f"## {triage['summary']}\n\n"
        f"Closes: {issue['title']}\n\n"
        f"### Plan\n" + "\n".join(f"- {s}" for s in plan["steps"]) + "\n\n"
        f"### Files changed\n" + "\n".join(f"- {f}" for f in changed) + "\n\n"
        f"### Tests\n{'All tests pass' if tests_ok else 'TESTS FAILING — see log'} "
        f"({tests_before} → {tests_after} discovered).\n\n"
        f"### Regression gate\n"
        f"{'Verified: ' if gate['applicable'] else 'Not applicable: '}"
        f"{gate['reason']}.\n\n"
        f"### Issue-target gate\n"
        f"{'Verified: ' if target_gate['applicable'] else 'Not applicable: '}"
        f"{target_gate['reason']}.\n\n"
        f"### Reviewer\n{review.get('verdict')}: {review.get('notes', '')}\n")
    (out_dir / "pr_body.md").write_text(pr_body)
    run_cost = cost_mod.summarize(calls_log)
    (out_dir / "cost.json").write_text(json.dumps(
        {"summary": run_cost, "calls": calls_log}, indent=2) + "\n")
    result = {"passed": passed, "changed": changed, "tests_ok": tests_ok,
              "tests_before": tests_before, "tests_after": tests_after,
              "unexpected_files": unexpected, "test_log_tail": test_log[-400:],
              "regression_gate": gate,
              "target_gate": target_gate,
              "cost": run_cost}
    _emit(on_event, "done", {"result": result, "pr_body": pr_body})
    return result


def resume(repo, request, client, out_dir, on_event=None):
    """Resume an escalated issue from its recorded human decision.

    - No decision recorded: ValueError (nothing runs).
    - reject / handle_manually: closes the request, writes
      resume_result.json, returns a closed result; no model call is
      made and no file is touched (client is never invoked).
    - rescope: re-enters run() with the attached rescoped_issue, so
      the deterministic guardrail re-checks the new issue before any
      model call; a still-destructive rescope escalates again
      (Escalation propagates, with a fresh approval request written).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not isinstance(request, dict) or request.get("type") != "human_approval_request":
        raise ValueError("resume requires a human_approval_request")
    record = request.get("decision_record") or {}
    decision = record.get("decision")
    if not decision:
        raise ValueError("no human decision recorded on this approval request")
    _emit(on_event, "resume", {"decision": decision,
                               "decided_by": record.get("decided_by")})
    if decision in ("reject", "handle_manually"):
        result = {"status": "closed_manual" if decision == "handle_manually" else "closed_rejected",
                  "decision": decision, "resumed": False, "passed": False,
                  "model_calls_made": 0, "cost": cost_mod.summarize([])}
        (out_dir / "resume_result.json").write_text(json.dumps(result, indent=2) + "\n")
        _emit(on_event, "done", {"result": result})
        return result
    if decision != "rescope":
        raise ValueError(f"unknown decision {decision!r}")
    rescoped = request.get("rescoped_issue")
    if not isinstance(rescoped, dict) or not rescoped.get("title"):
        raise ValueError("rescope decision has no rescoped_issue attached")
    result = run(repo, rescoped, client, out_dir, on_event=on_event)
    wrapped = {"status": "resumed", "decision": "rescope", "resumed": True,
               "passed": bool(result.get("passed")), "issue": rescoped,
               "result": result, "cost": result.get("cost")}
    (out_dir / "resume_result.json").write_text(json.dumps(wrapped, indent=2) + "\n")
    return wrapped
