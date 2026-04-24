---
name: project-memory-loop
owner: sophomores
description: Use when non-trivial project work must read project memory before execution and may need stable write-back after. 当非琐碎项目任务必须先读项目记忆, 且收尾时可能需要稳定写回时使用.
---

# Project Memory Loop

## Overview

- 这个 skill 用于长生命周期仓库, 让稳定记忆在执行前生效, 在收尾时做可信写回.
- `.codex/memory/` 是 canonical memory, 不是 task-state 存储层.
- runtime 默认先 consult 项目 memory, 再 consult `~/.codex/memory/` 作为个人全局 overlay.
- memory 可以充当 skill 的轻入口:
  - canonical memory 保存长期知识与 route 词.
  - thin entry memory 把高频旧入口导回既有 skill.
- 默认先收敛到已有 skill, 不为单一 runbook 新建 skill.
- 默认走快路径; 治理, promotion, hygiene, verifier 等流程按需触发.

## Always Read

1. `rules/core-boundaries.md`
2. `workflows/runtime-protocol.md`

## Common Tasks

- 为仓库补齐 `.codex` 项目层 -> 按 `workflows/runtime-protocol.md#bootstrap-when-missing`
- 在记忆治理仓库中启动非琐碎任务 -> 按 `workflows/runtime-protocol.md#start-of-non-trivial-work`
- 收尾并判断是否写回长期 memory -> 按 `workflows/closeout-protocol.md`
- 做周期性治理或 promotion 判断 -> 读 `workflows/memory-hygiene-and-enrichment-loop.md` 或 `workflows/memory-skill-promotion-loop.md`
- 更新 handbook 或面向人的仓库文档 -> 读 `references/handbook-update-rules.md` 和 `references/handbook-style.md`
- Other / unlisted task -> 先完成 `Always Read`, 只有需要治理细节时再读 `references/memory-governance.md`

## Known Gotchas

- 默认启动只要求 `ov -> 读 context.md / must_read -> 执行`; `r` 只在需要命中既有 runbook 或 asset 时再运行.
- 先读 `registry.md` 或 `index.md` 会削弱 runtime 路由质量 -> 见 `references/known-gotchas.md#route-skipping`
- task-state 不属于 `.codex/memory/` -> 见 `references/known-gotchas.md#task-state-pollution`
- evolution sidecar 不能绕过 canonical memory flush -> 见 `references/known-gotchas.md#sidecar-boundary-drift`
- home memory 是 runtime overlay, 不是项目 memory 的默认写回目标 -> 见 `rules/core-boundaries.md`

## References

### Core

- `rules/core-boundaries.md`
- `workflows/runtime-protocol.md`
- `workflows/closeout-protocol.md`

### On-demand

- `references/known-gotchas.md`
- `references/memory-governance.md`
- `references/gpt54-agent-loop.md`
- `references/handbook-update-rules.md`
- `references/handbook-style.md`
- `workflows/memory-hygiene-and-enrichment-loop.md`
- `workflows/memory-skill-promotion-loop.md`
- `references/项目说明书模板.md`
- `references/项目说明书.reference模板.md`
- `scripts/codex_memo.py`
- `scripts/bootstrap_project_codex.py`
- `scripts/memory_tool.py`
- `scripts/build_asset_index.py`
