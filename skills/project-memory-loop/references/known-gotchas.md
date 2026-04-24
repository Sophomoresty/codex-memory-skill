# Known Gotchas

## Route skipping

- 上来先读 `registry.md` 或 `index.md` 会浪费上下文, 也会削弱路由质量.
- runtime 应先走 `codex-memo ov` 与 `codex-memo r`; 只有治理场景才读 `registry.md` 或 `index.md`.
- `codex-memo` 默认只走 CLI 入口:
  - 用 `codex-memo ...`
  - 不把 `/home/sophomores/.local/bin/codex-memo ...` 当作普通使用写法; 绝对路径只用于 PATH/安装排障
  - 不在普通执行场景直接跑 `python3 /home/sophomores/.codex/scripts/codex_memo.py ...`

## Task-state pollution

- 不要把执行状态写进 `.codex/memory/`.
- 活动 task-state 固定放在 `.codex/tasks/<task-id>/`.

## Sidecar boundary drift

- `.codex/evolution/` 可以记录运行时经验, 但不能替代 canonical memory.
- sidecar 资产绝不能绕过 `codex-memo f`.

## Home overlay confusion

- `~/.codex/memory/` 参与 runtime consult, 但不改变项目 canonical memory 的归属.
- 只有在 agent 明确判断为跨项目可复用知识时, 才考虑从项目结论 promote 到 home memory.
