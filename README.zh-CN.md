[English](README.md)

<p align="center">
  <img src="docs/images/logo.png" alt="Codex Memory Skill" width="180" />
</p>

<h1 align="center">Codex Memory Skill</h1>

<p align="center">
  本地优先, skill-native, 可测试的记忆工作流.
</p>

<p align="center">
  <img src="docs/images/social-card.png" alt="Codex Memory Skill social card" width="720" />
</p>

## 它是什么

Codex Memory Skill 把项目记忆做成一套可执行的本地工作流: 记忆不是聊天残留, 而是可索引, 可路由, 可验证, 可压测的结构化资产.

它由一个本地 CLI 和一个可复用 skill bundle 组成, 重点解决:

- 任务来了先命中哪个 skill / runbook
- 项目里有哪些本地能力可以复用
- 如何为新项目快速 bootstrap 一层 `.codex/memory/`
- 如何做 benchmark, hygiene, checkpoint, promotion, L4 archive

核心 route 和 capability search 默认都在本地完成, 不依赖 hosted API.

## 核心能力

- **本地路由**: `codex-memo r --task "..."`
- **本地能力检索**: `codex-memo q --task "..."`
- **项目记忆 bootstrap**: `codex-memo b`
- **资产索引构建**: `codex-memo a`
- **记忆体检 / hygiene**: `codex-memo c`
- **benchmark 回放**: `python3 scripts/memory_benchmark.py --repo-root . --cases examples/benchmark-cases.json`
- **可选语义增强**: `numpy` + `sentence-transformers`
- **可测试**: 仓库内置 smoke tests

## 仓库结构

```text
bin/
  codex-memo                 # CLI 入口

scripts/
  codex_memo.py              # CLI 分发
  memory_tool.py             # 核心记忆操作
  build_asset_index.py       # 资产索引构建
  memory_benchmark.py        # Benchmark 运行器
  lib/                       # 共享内部模块

skills/
  project-memory-loop/       # 可复用 skill bundle

examples/
  benchmark-cases.json       # Benchmark 用例

tests/
  test_smoke.py              # 冒烟测试
```

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

## 常用命令

```bash
# 按任务描述做本地路由
codex-memo r --task "restore previous chat history"

# 检索本地 capability
codex-memo q --task "working checkpoint"

# 构建资产索引
codex-memo a

# 执行 hygiene 检查
codex-memo c

# 跑 benchmark
python3 scripts/memory_benchmark.py --repo-root . --cases examples/benchmark-cases.json
```

## 验证

打包后仓库的 smoke tests:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

当前结果:

- **3 / 3 smoke tests passed**

原系统的本地压测基线:

| 项目 | 结果 |
|---|---|
| Route | 130 / 130 success, top-1 100%, p50 445 ms |
| Capability search | 64 / 64 success, p50 139 ms |

## 可选语义增强

如需更强的模糊匹配:

```bash
pip install numpy sentence-transformers
```

这是可选增强, 不安装也不影响核心工作流.

## 适用边界

Codex Memory Skill 最强的定位是:

- 本地执行
- 文件透明
- 可回归验证
- skill-native 集成

它不是 hosted memory platform, 不是多租户 SaaS, 也不是通用向量数据库.

## Roadmap

- 更清晰的安装路径
- 更多公开示例
- 更完整的 benchmark case coverage
- 更便携的 skill bundle 打包方式
