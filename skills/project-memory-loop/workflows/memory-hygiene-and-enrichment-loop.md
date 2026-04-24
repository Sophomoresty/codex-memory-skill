# Memory Hygiene And Enrichment Loop

1. 默认先运行:
   - `codex-memo m`
   - 把返回的 `governance_summary` 视为本轮治理起点
2. 再扫描当前资产分布:
   - `session_assets`
   - `runbooks`
   - `patterns`
   - `decisions`
   - `skills`
3. 优先清 session:
   - 对每个 session 只判定一次:
     - `promote`
     - `archive`
     - `delete`
   - 已提炼为 canonical memory 的 session 不重复保留
4. 再按问题族扫描重复 memory:
   - 同根因
   - 同流程
   - 同边界
5. 对每组重复 memory 只做一个动作:
   - `merge-into-canonical-memory`
   - `thin-entry-only`
   - `promote-into-existing-skill`
6. 对 canonical memory 补齐检索面:
   - `aliases`
   - `keywords`
   - `triggers`
   - 必要的 `when_to_read`
7. aliases 默认至少覆盖:
   - 中英文同义词
   - 常见缩写
   - 常见错拼
   - 旧命名
8. keywords 默认至少覆盖:
   - 症状词
   - 工具名
   - 文件名
   - 关键命令
9. 若一个问题族已经有既有 skill 可承接:
   - 不新建 skill
   - 改为 canonical memory + thin entry + 既有 skill
10. 完成治理后必须确认:
   - `codex-memo m` 已通过
   - `hygiene.issue_count = 0`
11. 若本轮形成新问题族或新 route 入口:
   - 追加 coverage 或 adoption evidence
12. 向用户汇报时只说明:
   - 清掉了哪些噪声
   - 哪些 memory 被收敛
   - 哪些 aliases / keywords 被补齐
   - 是否通过 hygiene
