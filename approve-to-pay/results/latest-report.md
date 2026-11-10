# Approve-to-Pay — task set run report

- Task set version: 1.0.0 (frozen, checksum-verified)
- PayPal mode: **mock** — fixture-backed mock, no sandbox credentials configured
- Jobs run: 20
- Captured (COMPLETED): 8 ($1924.41 moved in sandbox)
- Blocked by guardrail: 10 {'over_budget': 4, 'category_not_allowed': 3, 'price_changed': 3}
- Blocked by approver: 2
- Blocked purchases that moved money: $0.00 (intended spend held: $7515.87)
- Outcomes matching the frozen expectations: 20/20
- False blocks (expected capture, got blocked): none
- Missed blocks (expected block, got captured): none
- Capture calls on blocked jobs: 0

| Job | Order | Guardrail | Approver | Capture called | Status | Actual | Expected | Match |
|---|---|---|---|---|---|---|---|---|
| ATP-001 | MOCK-ATP-001 | pass | approve | true | COMPLETED | capture | capture | yes |
| ATP-002 | MOCK-ATP-002 | pass | approve | true | COMPLETED | capture | capture | yes |
| ATP-003 | MOCK-ATP-003 | pass | approve | true | COMPLETED | capture | capture | yes |
| ATP-004 | MOCK-ATP-004 | pass | approve | true | COMPLETED | capture | capture | yes |
| ATP-005 | MOCK-ATP-005 | pass | approve | true | COMPLETED | capture | capture | yes |
| ATP-006 | MOCK-ATP-006 | pass | approve | true | COMPLETED | capture | capture | yes |
| ATP-007 | MOCK-ATP-007 | pass | approve | true | COMPLETED | capture | capture | yes |
| ATP-008 | MOCK-ATP-008 | pass | approve | true | COMPLETED | capture | capture | yes |
| ATP-009 | — | block (over_budget) | not_reached | false | — | block_guardrail | block_guardrail | yes |
| ATP-010 | — | block (over_budget) | not_reached | false | — | block_guardrail | block_guardrail | yes |
| ATP-011 | — | block (over_budget) | not_reached | false | — | block_guardrail | block_guardrail | yes |
| ATP-012 | — | block (over_budget) | not_reached | false | — | block_guardrail | block_guardrail | yes |
| ATP-013 | — | block (category_not_allowed) | not_reached | false | — | block_guardrail | block_guardrail | yes |
| ATP-014 | — | block (category_not_allowed) | not_reached | false | — | block_guardrail | block_guardrail | yes |
| ATP-015 | — | block (category_not_allowed) | not_reached | false | — | block_guardrail | block_guardrail | yes |
| ATP-016 | — | block (price_changed) | not_reached | false | — | block_guardrail | block_guardrail | yes |
| ATP-017 | — | block (price_changed) | not_reached | false | — | block_guardrail | block_guardrail | yes |
| ATP-018 | — | block (price_changed) | not_reached | false | — | block_guardrail | block_guardrail | yes |
| ATP-019 | MOCK-ATP-019 | pass | deny | false | — | block_approver | block_approver | yes |
| ATP-020 | MOCK-ATP-020 | pass | deny | false | — | block_approver | block_approver | yes |

Full audit trail: decision-log.jsonl (append-only).
