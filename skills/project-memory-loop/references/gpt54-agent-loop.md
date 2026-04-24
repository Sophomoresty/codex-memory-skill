# GPT-5.4 Agent Loop Adapter

只在运行环境明确是 GPT-5.4 agent loop 时再读这个文件.

## Start

1. 只有当前 loop 明确需要 route 结果时, 才用 `codex-memo g --task "<summary>"` 替代 `codex-memo r --task "<summary>"`.
2. 读取返回的 `route` 结果与 `working_memory`.
3. 把 `agent_prompt` 作为 loop 的 memory anchor.
4. 默认沿用本地 semantic rerank; route 质量校准改为主线程低频抽检评分, 不走在线 AI rerank.

## During execution

1. 只有实现阶段切换且确实需要重新 route 时, 才重新运行 `codex-memo g --task "<summary>"`.
2. 把 `working_memory.prompt_block` 视为短期状态, 不把它当 canonical memory.
3. 若任务持续超过一个明确实现阶段, 再用 `codex-memo k --task "<summary>" ...` 记录 key facts, task assets, current invariant, verified steps.

## Boundaries

1. `working_memory` 只服务当前 loop, 不等于 canonical memory.
2. `codex-memo g` 不改变 `.codex/memory/` 与 `.codex/tasks/` 的边界.
3. 长期写回仍只通过 `codex-memo f`.
