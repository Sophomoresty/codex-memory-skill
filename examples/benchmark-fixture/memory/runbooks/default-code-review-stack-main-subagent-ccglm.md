---
doc_id: runbook-default-code-review-stack-main-subagent-ccglm
doc_type: runbook
title: Default code review stack with main thread, subagent, and ccglm
status: active
scope: repo
tags: [code-review, review, subagent, ccglm]
triggers:
  - 进行 code review
  - 双审当前实现
keywords:
  - final code review
  - code review
  - subagent review
  - main thread review
aliases:
  - default code review stack
  - main subagent review
  - 双审当前实现
canonical: true
related: []
supersedes: []
last_verified: 2026-04-24
confidence: high
update_policy: merge
when_to_read:
  - before running final code review with main thread, subagent, or ccglm
---

# Default code review stack with main thread, subagent, and ccglm

## Trigger

- Use this note when the task asks for the default implementation review stack.
- Use this note when independent review is required before claiming implementation quality.

## Preconditions

- Identify the implementation scope and the files changed by the current task.
- Verify whether the user requested ccglm, subagent review, or main-thread-only review.

## Steps

1. Review correctness, regressions, repository hygiene, tests, and documentation claims.
2. Run the relevant local test suite before making any completion claim.
3. Treat reviewer output as evidence to verify, not as a replacement for local checks.

## Verification

- The final review lists concrete findings or states no blocker after fresh verification.
- The reported status includes the command outputs that prove the reviewed state.
