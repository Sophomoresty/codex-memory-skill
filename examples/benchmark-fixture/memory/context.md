---
doc_id: context-benchmark-fixture
doc_type: context
title: Benchmark Fixture Context
status: active
scope: repo
repo_type: benchmark-fixture
project_summary: Bundled benchmark fixture for codex-memory-skill route replay.
tags: [benchmark, fixture]
entrypoints:
  - runbooks/codex-app-update-thread-and-config-recovery.md
  - runbooks/ccglm-long-task-review-loop.md
common_tasks:
  - replay benchmark cases
must_read:
  - runbooks/codex-app-update-thread-and-config-recovery.md
  - runbooks/memory-hygiene-scan-cleanup-and-enrichment.md
keywords:
  - benchmark
  - fixture
canonical: true
related: []
supersedes: []
last_verified: 2026-04-24
confidence: high
update_policy: merge
when_to_read:
  - before replaying the bundled benchmark
---

# Benchmark Fixture Context

Use this bundled memory set to replay the published benchmark cases in a clean repo checkout.
