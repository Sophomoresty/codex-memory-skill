# Runtime Protocol

## Bootstrap when missing

1. 如果仓库缺少 `.codex` 项目层或必需脚本, 运行 `codex-memo b`.
2. `boot` 负责补齐 `.codex/memory/`, `.codex/AGENTS.md`, root `AGENTS.md`, 以及本地辅助脚本.
3. `boot` 以本 skill 的 `scripts/` 目录为托管源同步辅助脚本.

## Start of non-trivial work

1. 每个新线程先运行一次 `codex-memo ov`.
2. 读取 project overview 返回的 `context.md` 与 `must_read`.
3. 默认到此直接开始执行.
4. `codex-memo` 一律优先走 CLI 入口:
   - 若 PATH 已正确注入, 直接执行最短命令 `codex-memo ...`
   - 不要在普通执行场景优先写 `/home/sophomores/.local/bin/codex-memo ...`
   - 只有命令缺失或定位 PATH 问题时, 才用 `command -v codex-memo` 或 `/home/sophomores/.local/bin/codex-memo ...` 做调试
   - 非脚本开发或测试场景, 不直接调用 `python3 /home/sophomores/.codex/scripts/codex_memo.py ...`
   - 不假设源脚本支持与 CLI 完全相同的参数面
5. 若当前运行环境是 GPT-5.4 agent loop, 读 `references/gpt54-agent-loop.md`.
6. 只有在以下情况才运行 `codex-memo r --task "<summary>"`:
   - 当前任务明显依赖既有 runbook.
   - 需要查 project asset, task-doc, session recall, 或本地 capability 线索.
   - 要做 memory write-back, adoption, coverage, 或 verifier 相关治理.
7. `codex-memo r` 默认只使用本地 semantic rerank:
   - 不提供在线 AI rerank 命令面.
   - route 质量校准改为主线程低频抽检评分, 不走 rerank API.
8. `codex-memo r` 默认只读缓存:
   - 读取现有 `.codex/cache/asset-index.json`.
   - 读取现有 semantic index.
   - 普通 route 不现场 rebuild asset index 或 semantic index.
9. 优先只读取高置信命中项, 顺序为 project memory hits -> project asset hits -> home memory hits -> merged hits.
10. project asset hits 允许包含 script, skill, task-doc, session.
11. 若 route 命中 session asset, 只把相关片段当作 runtime recall 线索, 不把 session 直接当 canonical memory.
12. 每次 `codex-memo r` 后, 查看返回的 `execution_gate`:
   - `state = hit` 时, 按 `selected_ref / selected_path` 对应的 project runbook 执行.
   - `state = reference_only` 时, 命中项只可作为参考线索, 不计作可执行记忆.
   - `state = miss` 时, 本次按新问题族处理.
13. `route_event_id` 与 `surfaced_hits_hash` 是 route evidence 的绑定键; 后续写 checkpoint / adoption / coverage 时必须带上.
14. 若 route 返回低置信度或无命中, 再补读项目 `context.md`, 不先读 `registry.md` 或 `index.md`.
15. 默认不要求 `codex-memo a`; 只有需要辅助上下文或本轮改动了本地 skill / script / pattern 时再运行.

## Default execution path

- 在新增资产前, 先复用现有 memory 与本地 capability.
- 默认不要求 checkpoint, adoption trace, coverage, verifier.
- 收尾时只判断两件事:
  - 是否形成了稳定项目知识.
  - 是否修改了本地 skill, script, runbook, 或 pattern.

## On-demand extensions

- 若任务持续超过一个明确实现阶段, 再用 `codex-memo k --task "<summary>" ...` 记录 key facts, task assets, current invariant, verified steps.
- 若本轮 route 的 top hit 或 selected hit 被实际采用, 且需要沉淀 retrieval learning, 再记录 adoption evidence:
  - `codex-memo k --task "<summary>" --route-query "<query>" --route-event-id "<event-id>" --surfaced-hits-hash "<hits-hash>" --selected-hit "<repo-path>" --adopted-hit "<repo-path>" --observed-actions "<action1,action2>" --evidence-paths "<path1,path2>"`
- 若本轮 `execution_gate.state != hit`, 且收尾要把问题沉淀为新问题族, 再记录 coverage:
  - `codex-memo k --task "<summary>" --route-query "<query>" --route-event-id "<event-id>" --surfaced-hits-hash "<hits-hash>" --coverage-mode new_family --runbook-paths "<runbook>" --benchmark-queries "<query1,query2>" --coverage-evidence "<path1,path2>" --evidence-paths "<path1,path2>"`
- 若任务已有 `.codex/tasks/<task-id>/`, 且需要独立 review / verify 闭环, 再初始化 verifier sidecar:
  - `codex-memo v --task-id "<task-id>" --task-summary "<summary>" --deliverables "<path1,path2>" --required-checks "<check1,check2>" --evidence-paths "<path1,path2>"`
- verifier sidecar 只用于 task-scoped review artifact, 不进入 `.codex/memory/`.
- route 返回的 `adoption_hint` 或 `coverage_hint` 字段包含对应命令模板.
- route 返回的 `execution_gate.prompt` 是强制提示文案, 不允许静默跳过.
- `--surfaced-hits` 只用于显式回放已知 route event; 默认由 `route_event_id` 自动回填并校验.
- adoption 记录会通过 `learning_boost` 提升未来 route 精确率.
- `session`, `skill`, 普通 `task-doc`, 普通 `script` 默认只算 reference hit; 若要形成稳定复用, 必须再沉淀成 runbook 或 executable asset.
- 如果 route 没有命中有用结果, 而你通过其他方式解决了问题, 考虑用 `codex-memo p` 创建新的记忆资产.
