# Project Memory Governance

只在需要治理判断时再读这个文件.
治理流程按需触发, 不作为每次任务的默认动作.

## 主原则

- 新建前先问: 能不能 update? 能不能 merge?
- 同根因, 同流程, 同边界, 默认不新建
- memory 只存未来线程可复用的信息

## memory 与 skill 分层

- 先问: 这是长期知识, 还是高频执行协议.
- 长期知识留在 canonical memory.
- 高频执行协议优先并入已有 skill.
- 旧入口, 旧叫法, 旧检索词保留在 thin entry memory.
- 不为单一 runbook 新建 skill.
- skill 负责改变执行行为.
- memory 负责检索, 路由, 边界, 稳定结论.

## promotion 规则

- 满足以下条件, 才考虑 promote 到 skill:
  - 同一 procedural path 高频重复出现
  - 每次都需要改变 agent 执行顺序或读取顺序
  - 现有 skill 无法自然吸收
- 若现有 skill 可以吸收:
  - 更新 skill
  - 原 runbook 降为 thin entry
- 若只是 broad routing:
  - 建总入口 runbook
  - 不新建 skill
- 若 skill 数量增长只会增加上下文开销:
  - 保持 canonical memory + thin entry
  - 不 promote

## 周期性治理规则

- 周期性治理默认包含 4 件事:
  - 扫 session
  - 收敛重复 memory
  - 补 aliases / keywords
  - 重建索引并做 hygiene
- 周期性治理默认入口固定为:
  - `codex-memo m`
- 这 4 件事属于 `project-memory-loop`, 不是额外临时动作.
- 周期性治理不要求每次都新建文档.
- 默认目标是:
  - 减少 route 噪声
  - 保持 canonical 命中稳定
  - 防止 skill 膨胀

## session 清理规则

- `session` 和 `archived_session` 默认不保留为长期资产.
- 对每个活跃 session 只做一个判定:
  - promote 为 runbook / decision / pattern
  - 归档
  - 删除
- 若 session 只有一次性上下文, 直接删除或归档.
- 若 session 已被提炼进 canonical memory, 不重复保留 session.

## aliases / keywords 补齐规则

- canonical runbook 默认补齐:
  - 至少 3 个 aliases
  - 中英混合 keywords
  - 症状词
  - 工具名
  - 文件名或命令名
- thin entry 默认补齐:
  - 旧叫法
  - 旧入口
  - broad routing 词
- 若 route 命中不稳定, 先补 aliases / keywords, 不先新建文档.

## 写入优先级

- 新故障模式 -> `postmortems/`
- 重复稳定流程 -> `runbooks/`
- 未来线程必须知道的硬约束 -> `decisions/`
- 稳定复用方法 -> `patterns/`

## 轻治理规则

### decision
- active canonical `decision` 默认不超过 6 篇
- 阶段现象, 临时 warning, 过渡状态默认不进 decision
- 新增 decision 前先问: 新主题, 还是旧主题补充?

### context
`context.md` 只保留 4 类内容:
- 仓库身份
- 唯一设计基线来源
- 关键目录
- 稳定流程边界

### retirement review
每周或每阶段收口时检查:
- 哪篇 decision 已被覆盖
- 哪篇 decision 只是阶段现象
- 哪篇 decision 应降级为 docs

## no-op 何时允许

- 本轮只是执行已有 canonical 流程
- 本轮只是一次性微调
- 本轮结论与现有主文档完全一致

## 文档生成规范

### 类型比例目标
- runbook: ~40%（操作指南）
- decision: ~20%（架构决策）— 当前严重不足，优先补齐
- pattern: ~15%（稳定复用方法）
- postmortem: ~10%（事故复盘）
- context/executable: ~15%
- 新建文档前先检查当前比例，向不足的类型倾斜

### aliases 必填
- 每个新文档的 frontmatter 必须包含 `aliases` 字段，至少 3 个条目
- aliases 内容：中英混合、缩写、常见错拼、同义词
- 示例: `aliases: [cc-switch, codex配置同步, config-sync, jshook开关]`
- 作用：route 检索时 aliases 权重为 1.0（等同于 title），是跨语言匹配的关键

### Session 生命周期
- session 和 archived_session 是临时产物，不参与长期记忆
- 任务结束后，session 中有可复用知识 → 提炼为 runbook/decision/pattern
- 无复用价值的 session → 删除，不保留
- 禁止让 session 长期堆积（当前 80 个 session 占 42% assets，需清理）

### 文档质量 checklist
- title: 简短、描述性强、可被 route 匹配
- triggers: 声明式描述 "什么情况下该想起这篇文档"
- keywords: 包含中英关键词、技术名词、文件名
- aliases: 至少 3 个（缩写/同义词/错拼）
- body: 有 ## 标题结构，操作步骤有 code blocks
