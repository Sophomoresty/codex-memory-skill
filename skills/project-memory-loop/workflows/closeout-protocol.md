# Closeout Protocol

## Default closeout

1. 先判断本轮是否形成了稳定项目知识:
   - 是 -> 运行 `codex-memo f ...`; 默认只写项目 memory.
   - 否 -> 不做 canonical write-back.
2. 若本轮修改了本地 skill, script, runbook, 或 pattern:
   - 运行 `codex-memo a`
   - 将 `.codex/cache/asset-index.json` 作为更新后的辅助上下文
3. 面向用户的默认收口保持简短:
   - 只说明实际改动, 当前结果, 以及必要的单句验证结论.
   - 不默认输出 `sync-registry`, `hygiene`, `memory: update`, `task-state`, `资产` 这类治理清单.

## On-demand closeout

1. 若存在 `.codex/scripts/evolution_tool.py` 与 `.codex/evolution/`, 且本轮需要 sidecar 治理:
   - `record-event`
   - `review-promotions`
   - 只有在判断 canonical write-back 候选时才运行 `suggest-memory-writeback`
2. 若本轮是周期性治理或保养:
   - 运行 `codex-memo m`
   - 把它当作治理自动化入口:
     - 重建 asset index
     - sync registry
     - hygiene
     - governance summary
3. 若本轮需要做 memory review 与 promotion 决策:
   - `create`
   - `update`
   - `merge`
   - `no-op`
   - `promote-into-existing-skill`
   - `thin-entry-only`
4. 若本轮是高频执行协议, 按 `workflows/memory-skill-promotion-loop.md` 判断:
   - 能否并入已有 skill
   - 是否只需要保留 canonical memory + thin entry
   - 是否真的需要新 skill
5. 若本轮是周期性治理, 或本轮新增了多篇 memory / session / route 词:
   - 先按 `workflows/memory-hygiene-and-enrichment-loop.md` 扫描
   - 再决定哪些内容需要 merge, thin entry, 或 promotion
6. 若决定并入已有 skill:
   - 先更新 skill 的 workflow / references / common tasks
   - 再把旧 runbook 降为 `canonical: false` 的 thin entry
   - thin entry 只保留 route 词, 触发条件, 跳转路径
7. 若本轮形成了可复用 procedural path:
   - 运行 `codex-memo p --task-summary "<summary>" --type <skill|sop|script> --title "<title>" --summary "<summary>"`
   - candidate 默认只进入 evolution sidecar, 不直接写 retrieval learning
8. 如果本轮存在 adoption evidence:
   - 确认 checkpoint 中保留了 `route_event_id`, `surfaced_hits_hash`, `surfaced_hits`, `selected_hit`, `adopted_hit`, `observed_actions`, `evidence_paths`
   - 只有 `adoption_state = adopted` 的 trace 才允许作为 procedural candidate 的晋升证据
   - `evidence_paths` 必须非空且可解析到 repo 内实际文件
9. 如果本轮走的是新问题族 coverage:
   - 确认 checkpoint 中保留了 `closeout_ledger.coverage_mode = new_family`
   - 同时保留 `runbook_paths`, `benchmark_queries`, `coverage_evidence`
10. 如果本轮使用了 verifier sidecar:
   - 保留 `.codex/tasks/<task-id>/verify/verify_context.json`
   - 更新或审阅 `.codex/tasks/<task-id>/verify/review.md`
   - 不把 verifier artifact 直接 flush 到 `.codex/memory/`
11. 如果本轮结论已被证明是跨项目可复用知识, 再单独判断是否 promote 到 home memory; 这一步不是默认动作.
12. 只有当边界, 入口, 或必须让人知道的知识发生变化时, 才更新 human-facing docs.
13. 如果 `.codex/tasks/<task-id>/` 下存在 task-state, 按收尾结论删除或归档.
14. 只有用户明确要求详细收尾, 审计信息, 或交付清单时, 才展开治理字段.
