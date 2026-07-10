---
description: Closed-loop implementation until acceptance passes (arg1=goal, arg2=ci command)
agent: build
---
Goal: $1
Verification command: $2

1. Implement the next increment toward the goal.
2. Invoke @verifier with goal, diff, and command `$2`.
3. If FAIL: apply ONLY the listed fixes, return to step 2.
4. If PASS: run `$2` once more, summarize, STOP.

HARD STOP after 5 verify cycles. If still FAIL, report blockers and STOP.
