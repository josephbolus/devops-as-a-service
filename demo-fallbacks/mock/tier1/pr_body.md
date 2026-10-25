## paginate() drops the last item of every full page

Closes: Fix off-by-one in pagination helper

### Plan
- Reproduce with 20 items, page 2, page size 10
- Fix the slice end in app/pagination.py
- Add a regression test for a full last page

### Files changed
- app/pagination.py
- tests/test_pagination_regression.py

### Tests
All tests pass (6 → 7 discovered).

### Reviewer
approve: Diff limited to expected files; regression test added.
