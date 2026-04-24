# Memory Skill Promotion Loop

1. 先按问题族聚合重复 memory:
   - 同根因
   - 同流程
   - 同执行边界
2. 对每组 memory 只做一个目标判定:
   - `merge-into-canonical-memory`
   - `promote-into-existing-skill`
   - `thin-entry-only`
   - `new-skill`
3. 默认优先级固定为:
   - `merge-into-canonical-memory`
   - `promote-into-existing-skill`
   - `thin-entry-only`
   - `new-skill`
4. 命中以下条件时, 保持 memory:
   - 主要价值是 route 词
   - 主要价值是故障树
   - 主要价值是长期边界或知识
5. 命中以下条件时, 并入已有 skill:
   - 这是高频 procedural path
   - 每次都要改变 agent 执行协议
   - 已有 skill 的职责边界能承接
6. 只有同时满足以下条件, 才允许新建 skill:
   - 现有 skill 无法承接
   - 新协议会高频复用
   - 仅靠 canonical memory 无法稳定约束执行
7. 如果并入已有 skill:
   - 更新 skill 的 `Overview`
   - 更新 `Common Tasks`
   - 补 workflow 或 reference
   - 将原 runbook 降为 `canonical: false`
   - thin entry 只保留:
     - 触发条件
     - 前置条件
     - 操作步骤中的跳转路径
     - 验证方法
8. 如果只需要 broad routing:
   - 新建总入口 runbook
   - 只保留症状到专题 runbook / skill 的映射
9. 收尾必须执行:
   - `codex-memo a`
   - route 命中则记录 adoption evidence
   - route 未命中且形成新问题族则记录 coverage
   - `codex-memo s`
   - `codex-memo c`
10. 向用户汇报时只说明:
   - 哪些 memory 被收敛
   - 哪些 skill 被吸收更新
   - 哪些文档降为 thin entry
   - 验证是否通过
