[中文文档](README.zh-CN.md)

<p align="center">
  <img src="docs/images/logo.png" alt="Codex Memory Skill" width="180" />
</p>

<h1 align="center">Codex Memory Skill</h1>

<p align="center">Local-first memory workflow and CLI for coding agents.</p>

<p align="center">
  <img src="docs/images/social-card.png" alt="Codex Memory Skill social card" width="720" />
</p>

## What It Is

Codex Memory Skill is a CLI (`codex-memo`) plus a reusable skill bundle (`skills/project-memory-loop/`) that gives coding agents structured, searchable, testable project memory.

It solves one problem: when a new agent thread starts work on a repo, it should not start from zero. Project knowledge -- runbooks, decisions, failure patterns, proven workflows -- should be indexable, routable, and verifiable, not buried in chat history.

**Who it is for:** developers working with coding agents (Codex, Claude Code, or similar) who want agent memory to survive across threads, sessions, and projects.

**Core objects and their relationships:**

| Object | Role |
|---|---|
| Memory note | A Markdown file with structured frontmatter. The unit of project knowledge. Types: runbook, decision, pattern, postmortem, context. |
| Runbook | A memory note with repeatable steps. The primary executable unit for agent routing. |
| Skill bundle | `skills/project-memory-loop/` -- a portable set of scripts, rules, and workflows that defines the full memory lifecycle. |
| Asset index | A JSON file (`.codex/cache/asset-index.json`) listing skills, scripts, executables, sessions, and insight pointers in the repo. |
| Checkpoint | Working memory for one task: key facts, invariants, verified steps, retrieval traces. Persisted in the SQLite store at `.codex/cache/memory-state.db`. |
| Promotion | A long-term knowledge entry derived from a checkpoint. Becomes a canonical memory note after validation. |
| L4 archive | Archived session files, replayable by query. Stored under `.codex/archived_sessions/`. |

All core operations (route, capability search, asset index, hygiene, checkpoint, promotion, archive) run locally. No hosted API is required.

## Quick Start

```bash
git clone <repo-url> codex-memory-skill
cd codex-memory-skill
chmod +x bin/codex-memo
./bin/codex-memo --help
```

Bootstrap memory into a target project:

```bash
cd /path/to/your-project
/path/to/codex-memory-skill/bin/codex-memo b
```

This creates `.codex/memory/` with runbook, decision, pattern, and postmortem directories, plus a seeded governance runbook.

## Core Commands

```bash
# Get an onboarding bundle for the current repo
codex-memo ov

# Route a task to the best matching runbook or memory note
codex-memo r --task "restore previous chat history"

# Search local capabilities (skills, scripts, runbooks, insights)
codex-memo q --task "working checkpoint"

# Build the asset index
codex-memo a

# Create a new memory note
codex-memo n --type runbook --slug my-runbook --title "My Runbook"

# Record working checkpoint state
codex-memo k --task "restore previous chat history"

# Create a long-term promotion from a checkpoint
codex-memo lp --task "restore previous chat history" --title "Thread Recovery" --summary "..." --doc-type runbook

# Archive or replay L4 sessions
codex-memo l4 --closeout
codex-memo l4 --query "thread recovery"

# Run the full governance maintenance loop
codex-memo m

# Run hygiene checks
codex-memo c

# Build the semantic retrieval cache (optional)
codex-memo sx

# Diagnose setup issues
codex-memo d
```

## Why It Is Different

| What others do | What Codex Memory Skill does |
|---|---|
| Store memory as chat history or implicit context | Store memory as structured Markdown notes with typed frontmatter |
| Rely on vector similarity alone | Use lexical routing with IDF weighting, optional semantic rerank, and execution gates |
| Require a hosted API or cloud service | Run all core operations locally with no external dependencies |
| No built-in validation | Ship smoke tests and a benchmark suite with baseline numbers |
| Memory is opaque | Memory is files you can read, edit, version-control, and delete |
| No lifecycle governance | Include hygiene checks, stale-note detection, canonical dedup, and decision retirement |

Choose Codex Memory Skill if you want:

- Memory that survives across agent threads, not just within one session.
- Route and search that run locally without a hosted API.
- Structured notes you can read, edit, and version-control -- not a black-box vector store.
- Built-in governance: hygiene checks, dedup, stale-note detection, decision retirement.

Common alternatives and how they compare:

| Approach | Limitation | What this project does instead |
|---|---|---|
| Chat history as memory | Lost when the thread ends; not queryable or reusable | Structured Markdown notes with typed frontmatter, indexable and routable |
| Pure vector recall | Requires embedding model; opaque ranking; no execution gates | Lexical routing with IDF weighting, optional semantic rerank, and execution gates |
| Hosted memory API / SaaS | Requires network; data leaves your machine; vendor lock-in | All core operations run locally with no external dependencies |
| Loose Markdown notes, no governance | Drift, duplication, stale content, no way to verify what is current | Hygiene checks, canonical dedup, stale-note detection, decision retirement, smoke tests |

Key properties:

- **Local-first**: route and capability search run entirely on your machine.
- **Skill-native**: the memory lifecycle is defined in a portable skill bundle, not hardcoded in the CLI.
- **Testable**: a public regression suite, a bundled benchmark fixture, and a route baseline from the source system (130/130 success, top-1 100%, p50 445 ms).

## Validation

Public test suite (run in this repo):

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

Result: **7/7 passed**.

Baseline from the source system:

| Operation | Result |
|---|---|
| Route | 130/130 success, top-1 100%, p50 445 ms |
| Capability search | 64/64 success, p50 139 ms |

Benchmark replay:

```bash
python3 scripts/memory_benchmark.py --repo-root . --cases examples/benchmark-cases.json
```

If the current checkout does not already contain `.codex/memory/`, the benchmark runner automatically replays against the bundled fixture under `examples/benchmark-fixture/`.

## Repository Layout

```text
bin/
  codex-memo                 CLI entry point

scripts/
  codex_memo.py              CLI dispatch and route logic
  memory_tool.py             Core memory operations
  build_asset_index.py       Asset index builder
  memory_benchmark.py        Benchmark runner
  lib/                       Shared internals (query_intel, semantic_index, ...)

skills/
  project-memory-loop/       Reusable skill bundle
    scripts/                 Mirrors core runtime scripts
    workflows/               Lifecycle workflows
    rules/                   Boundary rules
    references/              Documentation templates

examples/
  benchmark-cases.json       Benchmark cases
  benchmark-fixture/         Bundled memory fixture for benchmark replay

tests/
  test_smoke.py              Smoke tests
  test_readme_contract.py    README contract checks
  test_regressions.py        Regression coverage for benchmark and rerank API
```

`skills/project-memory-loop/scripts/` intentionally mirrors the root scripts. Keep them in sync when changing internal behavior.

## Optional Semantic Extras

For stronger fuzzy matching:

```bash
pip install numpy sentence-transformers
```

Then build the semantic cache:

```bash
codex-memo sx
```

These dependencies are optional. Route and capability search work without them.

## Scope

Codex Memory Skill is:

- a local CLI for project memory routing, indexing, and governance
- a portable skill bundle for the full memory lifecycle
- a testable workflow with built-in smoke tests and benchmarks

It is not:

- a hosted memory platform or SaaS
- a multi-tenant service
- a general-purpose vector database
- a replacement for your project's own documentation

Requires Python >= 3.11. No required dependencies for core operation.
