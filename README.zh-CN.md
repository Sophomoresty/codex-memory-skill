[English](README.md)

<p align="center">
  <img src="docs/images/logo.png" alt="Codex Memory Skill" width="180" />
</p>

<h1 align="center">Codex Memory Skill</h1>

<p align="center">本地优先的编码 Agent 记忆工作流与命令行工具.</p>

<p align="center">
  <img src="docs/images/social-card.png" alt="Codex Memory Skill social card" width="720" />
</p>

## 项目定位

Codex Memory Skill 是一个本地 CLI (`codex-memo`) 和可复用 skill bundle (`skills/project-memory-loop/`), 为编码 Agent 提供结构化, 可路由, 可验证的项目记忆.

它的核心目标: 当新的 Agent 线程接手一个仓库时, 不应该从零开始. 项目知识 -- runbook, 决策, 故障模式, 已验证流程 -- 应该可索引, 可路由, 可回归验证, 而不是消失在聊天历史中.

**给谁用:** 使用编码 Agent (Codex, Claude Code 等) 的开发者, 希望项目记忆跨线程, 跨会话, 跨项目存活.

## 项目简介

### 解决什么问题

- Agent 线程之间没有可复用的项目知识
- 记忆散落在聊天历史中, 无法检索
- 缺少结构化的项目决策和流程记录
- 没有可回归验证的记忆质量保障

### 核心功能

| 功能 | 命令 |
|---|---|
| 仓库概览与入口 | `codex-memo ov` |
| 任务路由 (命中最匹配的 runbook 或记忆) | `codex-memo r --task "..."` |
| 本地能力检索 (skill, script, runbook, insight) | `codex-memo q --task "..."` |
| 新建记忆笔记 | `codex-memo n --type runbook --slug ... --title ...` |
| 资产索引构建 | `codex-memo a` |
| 工作检查点读写 | `codex-memo k --task "..."` |
| 长期提升 (从检查点提取可复用知识) | `codex-memo lp --task "..."` |
| L4 会话归档与回放 | `codex-memo l4 --closeout` / `codex-memo l4 --query "..."` |
| 记忆体检 | `codex-memo c` |
| 全量治理维护 | `codex-memo m` |
| 语义缓存构建 (可选) | `codex-memo sx` |
| 环境诊断 | `codex-memo d` |

### 核心对象与关系

| 对象 | 角色 |
|---|---|
| 记忆笔记 (Memory note) | 带 frontmatter 的 Markdown 文件, 是项目知识的基本单元. 类型包括: runbook, decision, pattern, postmortem, context. |
| Runbook | 可重复执行的流程笔记, 是 Agent 路由的首要命中目标. |
| Skill bundle | `skills/project-memory-loop/`, 一套可移植的脚本, 规则和工作流, 定义完整的记忆生命周期. |
| 资产索引 (Asset index) | JSON 文件 (`.codex/cache/asset-index.json`), 列出仓库中的 skill, script, 可执行文件, 会话和 insight 指针. |
| 检查点 (Checkpoint) | 单任务的工作记忆: 关键事实, 不变量, 已验证步骤, 检索轨迹. 持久化到 SQLite 存储 `.codex/cache/memory-state.db`. |
| 提升 (Promotion) | 从检查点提取的长期知识条目, 经验证后成为正式记忆笔记. |
| L4 归档 (L4 archive) | 已归档的会话文件, 支持按查询回放. 存放在 `.codex/archived_sessions/`. |

所有核心操作 (路由, 能力检索, 资产索引, 体检, 检查点, 提升, 归档) 均在本地运行, 不依赖外部 API.

## 快速开始

```bash
git clone <repo-url> codex-memory-skill
cd codex-memory-skill
chmod +x bin/codex-memo
./bin/codex-memo --help
```

为目标项目注入记忆层:

```bash
cd /path/to/your-project
/path/to/codex-memory-skill/bin/codex-memo b
```

这会在目标仓库创建 `.codex/memory/` 目录, 包含 runbook, decision, pattern, postmortem 子目录, 以及一篇内置的治理 runbook.

## 常用命令

```bash
# 获取当前仓库的概览与入口
codex-memo ov

# 按任务描述路由, 命中最匹配的 runbook 或记忆笔记
codex-memo r --task "restore previous chat history"

# 检索本地能力 (skill, script, runbook, insight)
codex-memo q --task "working checkpoint"

# 构建资产索引
codex-memo a

# 新建记忆笔记
codex-memo n --type runbook --slug my-runbook --title "My Runbook"

# 记录工作检查点状态
codex-memo k --task "restore previous chat history"

# 从检查点创建长期提升
codex-memo lp --task "restore previous chat history" --title "Thread Recovery" --summary "..." --doc-type runbook

# 归档或回放 L4 会话
codex-memo l4 --closeout
codex-memo l4 --query "thread recovery"

# 运行全量治理维护循环
codex-memo m

# 执行记忆体检
codex-memo c

# 构建语义检索缓存 (可选)
codex-memo sx

# 诊断环境配置
codex-memo d
```

## 差异点

| 其他方案的常见做法 | Codex Memory Skill 的做法 |
|---|---|
| 记忆存为聊天历史或隐式上下文 | 记忆存为带类型化 frontmatter 的结构化 Markdown 笔记 |
| 单纯依赖向量相似度 | 词汇路由 + IDF 加权, 可选语义重排, 以及执行门控 |
| 依赖托管 API 或云服务 | 所有核心操作本地运行, 无外部依赖 |
| 没有内置验证 | 附带冒烟测试和基准测试套件, 有基线数据 |
| 记忆不可见 | 记忆是普通文件, 可读, 可编辑, 可版本管理, 可删除 |
| 没有生命周期治理 | 内置体检检查, 过期检测, canonical 去重, decision 退役审查 |

如果你需要以下能力, 这套更合适:

- 记忆跨线程存活, 而不是随会话消失.
- 路由和检索完全在本地运行, 不依赖托管 API.
- 结构化笔记, 可读, 可编辑, 可版本管理 -- 不是黑盒向量存储.
- 内置治理: 体检检查, canonical 去重, 过期检测, decision 退役审查.

常见替代方案对比:

| 方案类型 | 局限 | 本项目的做法 |
|---|---|---|
| 聊天历史式记忆 | 线程结束即丢失; 不可查询, 不可复用 | 带类型化 frontmatter 的结构化 Markdown 笔记, 可索引, 可路由 |
| 纯向量召回式记忆 | 依赖嵌入模型; 排序不透明; 没有执行门控 | 词汇路由 + IDF 加权, 可选语义重排, 以及执行门控 |
| 托管 memory API / SaaS | 依赖网络; 数据离开本机; 供应商锁定 | 所有核心操作本地运行, 无外部依赖 |
| 零散 Markdown 笔记但没有治理链路 | 逐渐漂移, 重复, 过期, 无法确认哪篇可信 | 体检检查, canonical 去重, 过期检测, decision 退役审查, 冒烟测试 |

关键特性:

- **本地优先**: 路由和能力检索完全在本地完成.
- **Skill-native**: 记忆生命周期定义在可移植的 skill bundle 中, 不硬编码在 CLI 里.
- **可测试**: 3 个冒烟测试, 一套基准测试, 路由基线 (130/130 成功, top-1 100%, p50 445 ms).

## 验证结果

冒烟测试 (在当前仓库运行):

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

结果: **3/3 通过**.

原系统本地基线:

| 项目 | 结果 |
|---|---|
| 路由 | 130/130 成功, top-1 100%, p50 445 ms |
| 能力检索 | 64/64 成功, p50 139 ms |

基准回放:

```bash
python3 scripts/memory_benchmark.py --repo-root . --cases examples/benchmark-cases.json
```

## 仓库结构

```text
bin/
  codex-memo                 CLI 入口

scripts/
  codex_memo.py              CLI 分发与路由逻辑
  memory_tool.py             核心记忆操作
  build_asset_index.py       资产索引构建
  memory_benchmark.py        基准测试运行器
  lib/                       共享内部模块 (query_intel, semantic_index, ...)

skills/
  project-memory-loop/       可复用 skill bundle
    scripts/                 核心运行脚本镜像
    workflows/               生命周期工作流
    rules/                   边界规则
    references/              文档模板

examples/
  benchmark-cases.json       基准测试用例

tests/
  test_smoke.py              冒烟测试
```

`skills/project-memory-loop/scripts/` 有意保留了核心运行脚本的镜像. 修改内部逻辑时需要同步 root scripts 和 skill bundle 内的 scripts.

## 可选依赖

如需更强的模糊匹配能力:

```bash
pip install numpy sentence-transformers
```

然后构建语义缓存:

```bash
codex-memo sx
```

这是可选增强. 核心路由和能力检索不依赖这些包.

## 边界说明

Codex Memory Skill 是:

- 一个本地 CLI, 用于项目记忆的路由, 索引和治理
- 一个可移植的 skill bundle, 覆盖完整的记忆生命周期
- 一个可测试的工作流, 附带冒烟测试和基准测试

它不是:

- 托管记忆平台或 SaaS 服务
- 多租户系统
- 通用向量数据库
- 项目正式文档的替代品

运行要求: Python >= 3.11. 核心操作无强制外部依赖.
