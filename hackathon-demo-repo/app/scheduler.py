"""Nightly scheduled job runner.

Expansion seed issue #12 (scheduled jobs, intentional — do not fix
in the scaffold): after a transient exception the job is marked as
completed for the day and reported as a successful run, so the
retry later that day is skipped as 'already ran' and the night's
work silently never happens — while dashboards show success.
"""


def run_once(state, today, job):
    """Run `job` at most once per day, tracked in `state`.

    `state` is a dict; state["last_completed"] is the date string of
    the last genuinely successful run (or absent/None). Returns:
      "already-ran" — job already completed successfully today
      "ran"         — job ran and succeeded today
      "failed"      — job raised; it has NOT completed, so a later
                      invocation the same day must retry it
    A job exception must not propagate (the scheduler stays up), but
    it must not be recorded or reported as success either.
    """
    if state.get("last_completed") == today:
        return "already-ran"
    try:
        job()
    except Exception:
        # BUG: a transient failure is recorded as a completion and
        # reported as success, so the job silently skips the day.
        state["last_completed"] = today
        return "ran"
    state["last_completed"] = today
    return "ran"
