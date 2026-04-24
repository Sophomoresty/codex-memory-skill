# Core Boundaries

- `.codex/memory/` 是唯一 canonical 的长期项目记忆存储.
- 快路径是默认执行路径; 治理, adoption, coverage, verifier, promotion 都是按需流程.
- `~/.codex/memory/` 是个人全局 memory overlay, 用于跨项目 consult, 不是项目 canonical memory.
- task-state 应放在 `.codex/tasks/<task-id>/`, 不得写进 memory notes.
- runtime checkpoint 应放在 `.codex/tasks/` 侧的 non-canonical store, 不得写进 memory notes.
- verifier sidecar 应放在 `.codex/tasks/<task-id>/verify/`, 不得写进 memory notes.
- verifier sidecar 只允许保存 `verify_context.json` 与 `review.md` 这类 task-scoped review artifact.
- `ov` 与 `r` 是 runtime 入口; `registry.md` 与 `index.md` 默认只用于治理场景.
- 若存在 `.codex/evolution/` sidecar, 它只记录运行时经验, 不能直接写入 `.codex/memory/`.
- procedural memory candidate 应放在 `.codex/evolution/` sidecar, 不得直接视为 canonical memory.
- retrieval learning 应放在 `.codex/evolution/` sidecar, 只允许影响 route 打分, 不得直接改写 canonical memory note.
- 长期写回默认走 `codex-memo f`.
- `codex-memo v` 只读写 task-scoped verifier sidecar, 不得直接声称任务通过.
- 若存在本地 capability discovery, 它只是辅助上下文, 不能替代 memory routing.
- runtime 默认先读项目 memory, 再读 home memory overlay; 冲突时以项目命中优先.
- 是否存在跨项目可复用知识, 由 agent 在收尾时判断; 不要求用户预先全量标记.
- `f` 默认只写项目 memory, 不隐式写入 home memory.
