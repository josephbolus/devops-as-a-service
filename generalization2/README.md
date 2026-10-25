# textkit — second generalization target codebase

A small, self-contained Python package (stdlib only) vendored into
this repo on Oct 25, 2026 **solely** as a THIRD codebase the DevOps as
a Service pipeline has never seen (after the seeded demo repo and
`generalization/`'s ledgerlite): a different package name (`textkit`,
not `app` or `ledgerlite`), a different domain (text normalization,
tokens, slugs, and reading statistics — not pagination/HTTP/CLI or
ledger cent amounts), and a different module layout.

## The pre-existing bug

`textkit/tokens.py` — `first_words()` slices `words[: n + 1]` instead
of `words[:n]`, returning one word more than requested and
contradicting its own docstring. Repro:

```bash
python3 -c "from textkit.tokens import first_words; print(repr(first_words('alpha beta gamma delta', 2)))"
# prints 'alpha beta gamma' — expected 'alpha beta'
```

The baseline suite does not cover the exact-count case (only the
over-length and zero cases), so it passes with the bug present:

```bash
python3 -m unittest discover -s tests -q   # 10 tests, all passing
```

## The issue

`issue.json` in this directory is the real issue the pipeline was run
against (title: "Fix first_words returning one word too many"). The
measured live run and its outcome are recorded in
`../eval-scorecard/GENERALIZATION2.md` and
`../eval-scorecard/generalization2-runs.json`.

This directory is the pristine pre-run state: the pipeline ran
against a fresh copy of it, never against this directory in place,
and it was not tuned after the run — whatever the run did is the
recorded result.
