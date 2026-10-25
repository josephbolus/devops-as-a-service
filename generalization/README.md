# ledgerlite — generalization target codebase

A small, self-contained Python package (stdlib only) vendored into this
repo on Oct 25, 2026 **solely** as a second codebase the DevOps as a
Service pipeline has never seen: a different package name (`ledgerlite`,
not the demo repo's `app`), a different domain (ledger cent amounts,
not pagination / HTTP / CLI reports), and a different module layout.

## The pre-existing bug

`ledgerlite/stats.py` — `median_cents()` returns `ordered[mid]` for an
even count instead of averaging the two middle values, contradicting
its own docstring. Repro:

```bash
python3 -c "from ledgerlite.stats import median_cents; print(median_cents([100, 200, 300, 400]))"
# prints 300 — expected 250
```

The baseline suite does not cover the even-count case, so it passes
with the bug present:

```bash
python3 -m unittest discover -s tests -q   # 9 tests, all passing
```

## The issue

`issue.json` in this directory is the real issue the pipeline was run
against (title: "Fix median_cents for even-length amount lists"). The
measured live run and its outcome are recorded in
`../eval-scorecard/GENERALIZATION.md` and
`../eval-scorecard/generalization-runs.json`.

This directory is the pristine pre-run state: the pipeline ran against
a fresh copy of it, never against this directory in place, and it was
not tuned after the run — whatever the run did is the recorded result.
