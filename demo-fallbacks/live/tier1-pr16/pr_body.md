## paginate() returns 9 items instead of 10 on full pages.

Closes: Fix off-by-one in pagination helper

### Plan
- Reproduce bug with paginate(list(range(20)), 2, 10) confirming 9 vs 10 items
- Inspect app/pagination.py slice/end-index logic for off-by-one on full pages
- Fix slicing to return full page_size items
- Add regression test asserting full-page returns 10 items
- Run regression and existing baseline tests

### Files changed
- app/pagination.py
- tests/test_pagination_regression.py

### Tests
All tests pass (6 → 8 discovered).

### Reviewer
approve: Checked off-by-one fix in paginate: start:end-1 to start:end; verified new regression tests cover full first and second pages returning 10 items; diff limited to planned scope with no unrelated changes; tests 6->8 pass.

