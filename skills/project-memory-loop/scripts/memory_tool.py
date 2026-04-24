#!/usr/bin/env python3
from __future__ import annotations
import math

import argparse
import json
import re
import shutil
import sys
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from textwrap import dedent
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
LIB_DIR = SCRIPT_DIR / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import build_asset_index as bai
import query_intel as qi
import reuse_learning as rl


REQUIRED_FRONTMATTER_FIELDS = [
    "doc_id",
    "doc_type",
    "title",
    "status",
    "scope",
    "tags",
    "triggers",
    "keywords",
    "canonical",
    "related",
    "supersedes",
    "last_verified",
    "confidence",
    "update_policy",
    "when_to_read",
]

FRONTMATTER_ORDER = [
    "doc_id",
    "doc_type",
    "title",
    "repo_type",
    "project_summary",
    "entrypoints",
    "key_dirs",
    "common_tasks",
    "must_read",
    "aliases",
    "status",
    "scope",
    "tags",
    "triggers",
    "keywords",
    "canonical",
    "related",
    "supersedes",
    "last_verified",
    "confidence",
    "update_policy",
    "when_to_read",
]

PLACEHOLDER_SNIPPETS = [
    "YYYY-MM-DD",
    "keyword one",
    "keyword two",
    "error signal one",
    "error signal two",
    "repeated task trigger",
    "repeated failure family",
    "when this implementation shape appears",
    "before changing this convention",
    "before performing this recurring task",
    "before applying this reusable pattern",
    "Short failure title",
    "Verb object procedure",
    "Short architectural or workflow decision",
    "Short reusable pattern title",
    "简短失败标题",
    "动宾流程标题",
    "简短架构或流程决策标题",
    "简短可复用模式标题",
    "关键词一",
    "关键词二",
    "错误信号一",
    "错误信号二",
    "重复任务触发信号",
    "重复故障家族",
    "在这种实现形态出现时",
    "在执行该重复任务前",
    "在修改该约定前",
    "在应用该复用模式前",
    "待补充",
]

MAX_ACTIVE_CANONICAL_DECISIONS = 6

DECISION_PHASE_SNIPPETS = [
    "当前",
    "本阶段",
    "进行中",
    "暂时",
    "临时",
    "过渡",
    "deprecated",
    "warning",
    "待迁移",
    "待完善",
    "另一线程",
]

TEMPLATE_DIRS = {
    "runbook": "runbooks",
    "postmortem": "postmortems",
    "decision": "decisions",
    "pattern": "patterns",
}

ROUTE_EXCLUDED_FILENAMES = {"registry.md", "index.md"}
ROUTE_FALLBACK_ONLY_FILENAMES = {"context.md"}
MIN_SCORE_THRESHOLD = 1.2
MIN_CJK_SCORE_THRESHOLD = 0.18
AMBIGUITY_RATIO = 0.85
CANONICAL_BOOST = 0.05
INSIGHT_POINTER_BOOST = 0.20
BODY_EXCERPT_LIMIT = 800
SESSION_ASSET_TYPES = {"session", "archived_session"}
SESSION_MEMORY_SCORE_MARGIN = 0.01
ROUTE_FIELD_WEIGHTS = {
    "title": 1.0,
    "aliases": 1.0,
    "filename": 0.8,
    "keywords": 0.7,
    "triggers": 0.6,
    "when_to_read": 0.6,
    "tags": 0.5,
    "body": 0.15,
}
ASSET_FIELD_WEIGHTS = {
    "name": 1.0,
    "path": 1.2,
    "description": 0.5,
}
ASSET_EXACT_SYMBOL_BOOST = 1.2
ASSET_TYPE_BOOSTS = {
    "script": 0.15,
    "skill": 0.05,
    "task-doc": 0.08,
    "session": -0.5,
    "archived_session": -0.5,
    "executable": 0.4,
}
DOC_TYPE_BOOSTS = {
    "runbook": -0.1,
    "decision": 0.3,
    "pattern": 0.2,
    "postmortem": 0.2,
}
CONFIDENCE_BOOSTS = {
    "high": 0.0,
    "medium": -0.08,
    "low": -0.15,
}
TASK_DOC_QUERY_TERMS = {"contract", "plan", "issues", "summary", "task", "issue"}
ROUTE_CONTEXT_CACHE_LIMIT = 8
ROUTE_CONTEXT_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()
ROOT_AGENTS_CONTENT = dedent(
    """\
    # Vault 根级 Agent 说明

    ## 入口协议

    - 在这个仓库处理非琐碎任务前, 先读 `./.codex/AGENTS.md`.
    - 新线程首次接手仓库时, 先执行 `codex-memo ov`, 再读 `context.md` 与 `must_read`.
    - 这个仓库的项目记忆统一放在 `./.codex/memory/`.
    - 仓库级多步任务默认使用 `project-memory-loop`, 具体治理规则以该 skill 为准.

    ## 职责分层

    - `./.codex/memory/` 只存项目记忆.
    - `./.codex/tasks/` 只在长任务 workflow 启用时承担规划与执行状态.
    - `docs/` 默认仍是给人看的正式文档, 除非用户明确要求别的用途.
    """
)

CODEX_AGENTS_CONTENT = dedent(
    """\
    # Project Memory Agent Instructions

    ## Project Memory Protocol
    - 项目级记忆统一维护在 `.codex/memory/`.
    - 仓库级多步任务默认使用用户级 skill `project-memory-loop`.
    - 本文件只补充本仓库特有约定, 不重复 skill 中的完整治理协议.
    - 新线程首次接手仓库时, 先执行 `codex-memo ov`, 再读 `context.md` 与 `must_read`.
    - 遇到非琐碎任务时, 默认先执行 `codex-memo ov`, 读取 `context.md` 与 `must_read`, 再直接开始执行.
    - 只有需要命中既有 runbook, project asset, task-doc, 或 session recall 时, 才执行 `codex-memo r --task "<summary>"`.
    - `codex-memo r` 默认只使用本地 semantic rerank; 不提供在线 AI rerank 命令面.
    - `codex-memo r` 默认只读 `.codex/cache/asset-index.json` 与现有 semantic index, 不现场 rebuild.
    - 只读取 route 返回的高置信度记忆正文.
    - 仅当 route 返回低置信度或无命中时, 再补读 `.codex/memory/context.md`.
    - `registry.md` 与 `index.md` 不再作为运行时默认入口, 仅用于 sync-registry, flush, hygiene 与治理.
    - `.codex/memory/` 不承担任务状态跟踪职责.
    - 若启用了长任务 workflow, 执行状态只放在 `.codex/tasks/<task-id>/`.
    - 常规 runtime 与治理入口优先使用 `codex-memo`.
    - `memory_tool.py` 是 `codex-memo` 的后端实现层, 不再作为默认 agent 命令面.
    """
)

INDEX_CONTENT = dedent(
    """\
    ---
    doc_id: context-memory-index
    doc_type: index
    title: 项目记忆索引
    status: active
    scope: repo
    tags: [memory, index, routing]
    triggers:
      - 在读取项目记忆前
      - 在决定打开哪篇记忆文档时
    keywords:
      - memory index
      - canonical notes
      - read order
    canonical: true
    related:
      - context-repository-baseline
      - context-memory-registry
    supersedes: []
    last_verified: {today}
    confidence: high
    update_policy: merge
    when_to_read:
      - 在仓库级非琐碎任务开始时
    ---

    # 项目记忆索引

    ## 作用

    这个目录用于存放可被未来 Codex 线程复用的项目记忆.

    主要用于恢复:
    - 仓库背景与约束
    - 历史故障模式
    - 可重复执行流程
    - 持久化项目决策
    - 可复用实现或提示词模式

    不要用它记录任务状态. 若启用了长任务 workflow, 执行状态应放在 `.codex/tasks/<task-id>/`.

    ## 运行时定位原则

    - 新线程首次接手仓库时, 先执行 `codex-memo ov`, 再读 `context.md` 与 `must_read`.
    - 运行时默认先执行 `codex-memo ov`, 再读 `context.md` 与 `must_read`; 只有需要 route 时才执行 `codex-memo r --task "<summary>"`.
    - 本文件用于治理说明与活跃入口策展, 不再承担运行时默认读序入口.
    - 若 route 返回低置信度或无命中, 再补读 `context.md`.

    ## 目录映射

    - [registry.md](./registry.md): 元信息总表, 用于路由, 去重与生命周期治理.
    - [context.md](./context.md): 仓库背景, 稳定约束, 常用入口与固定约定.
    - [runbooks/](./runbooks/): 未来线程应优先复用的标准流程.
    - [postmortems/](./postmortems/): 故障现象, 触发信号, 根因与已验证修复.
    - [decisions/](./decisions/): 项目级选择及其理由.
    - [patterns/](./patterns/): 可复用代码形态, 提示词形态或操作模式.

    ## 主入口策略

    - `index.md` 应保持短小, 高信号.
    - 这里只列活跃, 高价值, 通常也是 canonical 的文档.
    - 历史文档可以保留在 `registry.md`, 但不必都出现在这里.

    ## 回写规则

    - 新故障模式 -> `postmortems/`
    - 重复出现的流程 -> `runbooks/`
    - 稳定约定或取舍 -> `decisions/`
    - 可复用实现或提示词方法 -> `patterns/`
    - 仓库级背景变化 -> `context.md`

    新建文档前:

    1. 先在 `registry.md` 中检查相同 `doc_type`, `triggers`, `tags` 以及 canonical 主文档.
    2. 若已有活跃 canonical 文档覆盖相同根因或相同流程, 优先更新, 不要重复新建.
    3. 只有当根因或操作边界明显不同, 才值得新建文档.

    若新文档确实提升检索效果, 先更新 `registry.md`, 只有在它值得成为活跃入口时, 才再更新本文件.
    """
)

REGISTRY_CONTENT = dedent(
    """\
    ---
    doc_id: context-memory-registry
    doc_type: registry
    title: 项目记忆总表
    status: active
    scope: repo
    tags: [memory, registry, metadata]
    triggers:
      - 在打开记忆文档前
      - 在新建或合并记忆文档前
    keywords:
      - memory registry
      - metadata catalog
      - deduplication
    canonical: true
    related:
      - context-memory-index
      - context-repository-baseline
    supersedes: []
    last_verified: {today}
    confidence: high
    update_policy: merge
    when_to_read:
      - 在选择记忆文档前
      - 在新建记忆文档前
    ---

    # 项目记忆总表

    ## 作用

    这个文件是项目记忆的元信息总表.

    它主要用于:
    - 在打开正文前, 先依据 frontmatter 做路由
    - 识别已有 canonical 主文档
    - 决定应更新, 合并, 废弃, 还是新建文档

    ## 总表规则

    - 每个活跃记忆文档都应以关键元信息出现在这里.
    - 对同一稳定主题, 尽量只保留一篇 canonical 主文档.
    - 活跃且 canonical 的 decision 默认不超过 6 篇.
    - 文档被合并或废弃后, 条目仍可保留, 但要更新生命周期字段.
    - `index.md` 是精选入口. `registry.md` 是全量元信息目录.

    ## 条目表

    | doc_id | doc_type | path | status | canonical | tags | triggers | last_verified | update_policy | related |
    | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
    | context-repository-baseline | context | `context.md` | active | true | `repo, context` | `在仓库级非琐碎任务前` | {today} | merge | `context-memory-index` |

    ## 合并判断规则

    满足下面条件时, 优先更新已有文档:
    - 根因相同
    - 处理流程实质上相同
    - 适用范围与边界没有变化

    满足下面条件时, 才新建文档:
    - 根因是新的
    - 操作边界变化足够大, 已经需要拆分指导
    - 强行塞进旧文档会让旧文档变得混乱
    """
)

CONTEXT_CONTENT = dedent(
    """\
    ---
    doc_id: context-repository-baseline
    doc_type: context
    title: 仓库基线背景
    repo_type: 待补充
    project_summary: 待补充
    entrypoints: []
    key_dirs: []
    common_tasks: []
    must_read: []
    status: active
    scope: repo
    tags: [repo, context, conventions]
    triggers:
      - 在仓库中开始非琐碎任务前
      - 在确定仓库级约定时
    keywords:
      - repository context
      - conventions
    canonical: true
    related:
      - context-memory-index
      - context-memory-registry
    supersedes: []
    last_verified: {today}
    confidence: high
    update_policy: merge
    when_to_read:
      - 在修改仓库级 workflow, skill 或自动化前
    ---

    # 项目背景

    ## 仓库身份

    - Repository: `{repo_name}`
    - Type: 待补充. 初始化后请在这里写明仓库类型, 关键模块与边界.

    ## 唯一设计基线来源

    - 在这里记录当前唯一可信的设计基线来源, 例如: 某份设计文档, 某个入口 skill, 某条契约说明.

    ## 关键目录

    - 在这里列出真正稳定且高频的关键目录.
    - 不要把阶段性结构调整, 临时目录或一次性实验内容塞进这里.

    ## 稳定流程边界

    - 项目记忆统一放在 `.codex/memory/`.
    - 长任务执行状态应放在 `.codex/tasks/<task-id>/`, 不放在 memory note 中.
    - 新线程在编辑仓库级操作文件前, 应先看 `AGENTS.md` 与 `.codex/AGENTS.md`.
    - 这个文件只保留稳定流程边界, 不记录阶段现象或临时判断.
    """
)

RUNBOOK_TEMPLATE_CONTENT = dedent(
    """\
    ---
    doc_id: runbook-verb-object
    doc_type: runbook
    title: 动宾流程标题
    status: active
    scope: repo
    tags: [workflow, area]
    triggers:
      - 重复任务触发信号
      - 重复故障家族
    keywords:
      - 关键词一
      - 关键词二
    canonical: true
    related: []
    supersedes: []
    last_verified: YYYY-MM-DD
    confidence: high
    update_policy: merge
    when_to_read:
      - 在执行该重复任务前
    ---

    # Runbook 模板

    ## 目的

    - 这个 runbook 解决什么重复任务?

    ## 何时使用

    - 触发条件是什么?

    ## 前置条件

    - 需要哪些文件, 工具, 环境或仓库状态?

    ## 操作步骤

    1. 第一步.
    2. 第二步.
    3. 第三步.

    ## 验证方法

    - 如何确认流程执行成功?

    ## 失败升级

    - 如果某一步失败, 或假设不成立, 应如何处理?

    ## 相关记忆

    - 链接到相关 postmortem, decision 或 pattern.
    """
)

POSTMORTEM_TEMPLATE_CONTENT = dedent(
    """\
    ---
    doc_id: postmortem-YYYY-MM-DD-short-topic
    doc_type: postmortem
    title: 简短失败标题
    status: active
    scope: repo
    tags: [area, failure]
    triggers:
      - 错误信号一
      - 错误信号二
    keywords:
      - 关键词一
      - 关键词二
    canonical: false
    related: []
    supersedes: []
    last_verified: YYYY-MM-DD
    confidence: medium
    update_policy: new-note-only-if-new-root-cause
    when_to_read:
      - 在调试相似症状前
    ---

    # Postmortem 模板

    ## 摘要

    - Date:
    - Task:
    - Scope:

    ## 现象

    - 失败现象是什么?
    - 是什么信号暴露了问题?

    ## 触发信号

    - 哪些日志, 输出, 行为或前置条件有助于未来更快识别?

    ## 根因

    - 实际底层原因是什么?

    ## 修复

    - 什么修复了问题?
    - 哪个变更已经验证?

    ## 验证

    - 使用了哪些命令, 检查或人工验证?

    ## 何时参考

    - 未来哪些任务或条件应该先读这篇?

    ## 升级判断

    - 这篇应该继续停留在 postmortem, 还是后续升级为 runbook 或 pattern?
    """
)

DECISION_TEMPLATE_CONTENT = dedent(
    """\
    ---
    doc_id: decision-ADR-###-short-topic
    doc_type: decision
    title: 简短架构或流程决策标题
    status: active
    scope: repo
    tags: [decision, architecture]
    triggers:
      - 在修改该约定前
    keywords:
      - 关键词一
      - 关键词二
    canonical: true
    related: []
    supersedes: []
    last_verified: YYYY-MM-DD
    confidence: high
    update_policy: merge
    when_to_read:
      - 在重新评估该项目级选择前
    ---

    # Decision 模板

    ## 元信息

    - ID:
    - Status:
    - Date:

    ## 背景

    - 是什么问题或歧义促成了这项决策?

    ## 决策内容

    - 最终选择了什么?

    ## 理由

    - 为什么选择这个方案而不是其他方案?

    ## 影响

    - 这个选择会让哪些事情更简单, 更困难, 被允许, 或被禁止?

    ## 何时重评

    - 哪些条件出现时应重新评估?
    """
)

PATTERN_TEMPLATE_CONTENT = dedent(
    """\
    ---
    doc_id: pattern-short-name
    doc_type: pattern
    title: 简短可复用模式标题
    status: active
    scope: repo
    tags: [pattern, implementation]
    triggers:
      - 在这种实现形态出现时
    keywords:
      - 关键词一
      - 关键词二
    canonical: true
    related: []
    supersedes: []
    last_verified: YYYY-MM-DD
    confidence: high
    update_policy: merge
    when_to_read:
      - 在应用该复用模式前
    ---

    # Pattern 模板

    ## 模式信息

    - Name:
    - Scope:

    ## 何时使用

    - 哪些信号说明这个模式适用?

    ## 何时避免

    - 哪些情况下不应该使用这个模式?

    ## 实现形态

    - 最小结构, 命令形式, 或代码形态是什么?

    ## 验证方法

    - 如何判断这个模式已经被正确应用?

    ## 相关记忆

    - 链接到支撑它的 runbook, postmortem 或 decision.
    """
)

MEMORY_FLUSH_RUNBOOK_CONTENT = dedent(
    """\
    ## 目的

    - 统一规范非琐碎任务结束后的 memory write-back, registry 同步与 hygiene 检查.

    ## 何时使用

    - 完成一次非琐碎实现, 调试, 重构, workflow 改造或长任务阶段后.
    - 需要新建或更新 runbook, postmortem, decision, pattern 时.
    - 周期性检查 `.codex/memory/` 是否出现过期, 重复或占位内容时.

    ## 前置条件

    - 仓库中存在 `.codex/memory/`.
    - 常规入口: `codex-memo`.
    - 若本轮需要写回, 已经明确本次经验属于 `runbook`, `postmortem`, `decision` 或 `pattern` 中的哪一种.

    ## 操作步骤

    1. 先判断本轮是否需要写回记忆.
       - 若本轮出现新根因, 新流程, 新约定或新模式, 需要写回.
       - 若本轮没有新增可复用知识, 可以不新建文档, 但仍要做同步与体检.
    2. 若需要写回, 先判断应更新已有 canonical 文档, 还是新建文档.
       - 先查 `registry.md`.
       - 同根因, 同流程, 同边界, 优先更新已有文档.
       - 只有根因或边界明显不同, 才新建文档.
    3. 需要新建时, 优先使用 CLI:
       - `codex-memo n --type runbook --slug <slug> --title <title>`
       - `codex-memo s`
       - `codex-memo c`
    4. 若本轮只更新已有文档, 不新建文件:
       - 先完成文档编辑.
       - 再执行 `codex-memo s`
       - 再执行 `codex-memo c`
    5. 周期性体检时直接执行:
       - `codex-memo c`
    6. 若 hygiene 发现问题:
       - duplicate_doc_id -> 合并或重命名
       - placeholder_value -> 补齐真实内容
       - stale_active_note -> 重新验证或降级状态
       - duplicate_canonical_title -> 收束成单一主文档

    ## 验证方法

    - `flush` 或 `sync-registry` 命令返回 0.
    - `hygiene` 返回 0, 或明确列出需要后续处理的问题.
    - `registry.md` 中出现最新文档条目, 且路径, doc_id, status 与 canonical 信息正确.

    ## 失败升级

    - 若脚本报错, 先修正 frontmatter 或目录结构, 再重新执行.
    - 若无法判断该更新还是新建, 优先更新已有 canonical 文档, 并在文内补充 variant 或 case.
    - 若出现大量历史碎片, 先做一次手动归并, 再重新跑 hygiene.

    ## 相关记忆

    - [../index.md](../index.md)
    - [../registry.md](../registry.md)
    - [../context.md](../context.md)
    """
)


@dataclass
class NoteRecord:
    path: Path
    rel_path: str
    frontmatter: dict[str, Any]
    body: str


@dataclass
class AssetRecord:
    path: Path
    rel_path: str
    asset_type: str
    name: str
    description: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project memory automation CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    base_parent = argparse.ArgumentParser(add_help=False)
    base_parent.add_argument("--repo-root", required=True, help="Repository root path")
    base_parent.add_argument("--format", choices=["text", "json", "table"], default="text")
    base_parent.add_argument("--force", action="store_true")

    note_parent = argparse.ArgumentParser(add_help=False)
    note_parent.add_argument("--doc-type", choices=sorted(TEMPLATE_DIRS), required=True)
    note_parent.add_argument("--slug", required=True)
    note_parent.add_argument("--title", required=True)
    note_parent.add_argument("--tags", default="")
    note_parent.add_argument("--triggers", default="")
    note_parent.add_argument("--keywords", default="")
    note_parent.add_argument("--aliases", default="", help="Semicolon-separated aliases for the note")
    note_parent.add_argument("--when-to-read", default="")
    note_parent.add_argument("--canonical", choices=["true", "false"], default=None)
    
    subparsers.add_parser("bootstrap", parents=[base_parent], help="Initialize project memory structure for a repository")
    subparsers.add_parser("sync-registry", parents=[base_parent], help="Scan notes and rebuild registry table")

    hygiene = subparsers.add_parser("hygiene", parents=[base_parent], help="Check memory quality and lifecycle issues")
    hygiene.add_argument("--stale-days", type=int, default=45)

    subparsers.add_parser("scaffold", parents=[base_parent, note_parent], help="Create a note from the matching template")
    route = subparsers.add_parser("route", parents=[base_parent], help="Route task summary to relevant memory notes")
    route.add_argument("--task", required=True)
    route.add_argument("--top-k", type=positive_int, default=3)
    overview = subparsers.add_parser("overview", parents=[base_parent], help="Return a low-context onboarding bundle for the repository")
    overview.add_argument("--max-must-read", type=int, default=4)
    inspect = subparsers.add_parser("inspect", parents=[base_parent], help="Explain why one note matches a task summary")
    inspect.add_argument("--task", required=True)
    inspect.add_argument("--path", required=True)

    flush = subparsers.add_parser("flush", parents=[base_parent], help="Optional scaffold + registry sync + hygiene")
    flush.add_argument("--doc-type", choices=sorted(TEMPLATE_DIRS))
    flush.add_argument("--slug")
    flush.add_argument("--title")
    flush.add_argument("--tags", default="")
    flush.add_argument("--triggers", default="")
    flush.add_argument("--keywords", default="")
    flush.add_argument("--when-to-read", default="")
    flush.add_argument("--aliases", default="", help="Semicolon-separated aliases for the note")
    flush.add_argument("--canonical", choices=["true", "false"], default=None)
    flush.add_argument("--stale-days", type=int, default=45)

    return parser.parse_args()


def positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return value


def normalize_list(raw: Any, fallback: list[str] | None = None) -> list[str]:
    if raw is None:
        return fallback or []
    items: list[str] = []
    if isinstance(raw, (list, tuple, set)):
        candidates = [str(item) for item in raw]
    else:
        text = str(raw)
        if ";" in text:
            candidates = text.split(";")
        elif "," in text:
            candidates = text.split(",")
        else:
            candidates = [text]
    for item in candidates:
        cleaned = item.strip()
        if cleaned:
            items.append(cleaned)
    return items or (fallback or [])


def slug_to_words(slug: str) -> str:
    return slug.replace("-", " ").strip()


def default_list(prefix: str, title: str, slug: str) -> list[str]:
    return [prefix.format(title=title, slug=slug_to_words(slug))]


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
    return value.strip("'\"")


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    lines = text.splitlines()
    end_index = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_index = idx
            break
    if end_index is None:
        return {}, text

    fm_lines = lines[1:end_index]
    body = "\n".join(lines[end_index + 1 :]).lstrip("\n")
    data: dict[str, Any] = {}
    i = 0
    while i < len(fm_lines):
        line = fm_lines[i]
        if not line.strip():
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.rstrip()
        if raw_value.strip():
            data[key] = parse_scalar(raw_value)
            i += 1
            continue

        items: list[str] = []
        i += 1
        while i < len(fm_lines):
            next_line = fm_lines[i]
            if next_line.startswith("  - "):
                items.append(next_line[4:].strip().strip("'\""))
                i += 1
                continue
            if not next_line.strip():
                i += 1
                continue
            break
        data[key] = items
    return data, body


def dump_frontmatter(data: dict[str, Any]) -> str:
    order = FRONTMATTER_ORDER + sorted(key for key in data if key not in FRONTMATTER_ORDER)
    lines = ["---"]
    for key in order:
        if key not in data:
            continue
        value = data.get(key)
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            elif key in {"tags"}:
                joined = ", ".join(str(item) for item in value)
                lines.append(f"{key}: [{joined}]")
            else:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def repo_memory_root(repo_root: Path) -> Path:
    return repo_root / ".codex" / "memory"


def resolve_memory_note_path(repo_root: Path, raw_path: str) -> Path:
    cleaned = raw_path.strip()
    if not cleaned:
        raise ValueError("path is required")
    if cleaned.startswith("memory/"):
        candidate = repo_memory_root(repo_root) / cleaned[len("memory/") :]
    else:
        candidate = repo_root / cleaned
    candidate = candidate.resolve()
    memory_root = repo_memory_root(repo_root).resolve()
    try:
        candidate.relative_to(memory_root)
    except ValueError as exc:
        raise ValueError("path must point inside .codex/memory") from exc
    return candidate


def write_file(path: Path, content: str, force: bool) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    if existed and not force:
        return "skipped"
    path.write_text(content, encoding="utf-8")
    if existed and force:
        return "updated"
    return "created"


def ensure_gitignore_has_codex(repo_root: Path) -> str:
    gitignore = repo_root / ".gitignore"
    entry = ".codex/"
    header = "# Codex 本地项目记忆"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        lines = content.splitlines()
        if any(line.strip() == entry for line in lines):
            return "skipped"
        append_block = f"\n{header}\n{entry}\n"
        if content and not content.endswith("\n"):
            content += "\n"
        gitignore.write_text(content + append_block, encoding="utf-8")
        return "updated"

    gitignore.write_text(f"{header}\n{entry}\n", encoding="utf-8")
    return "created"


def command_bootstrap(repo_root: Path, force: bool) -> dict[str, Any]:
    today = date.today().isoformat()
    memory_root = repo_memory_root(repo_root)
    (repo_root / ".codex" / "scripts").mkdir(parents=True, exist_ok=True)
    for directory in ["runbooks", "postmortems", "decisions", "patterns"]:
        (memory_root / directory).mkdir(parents=True, exist_ok=True)

    script_target = repo_root / ".codex" / "scripts" / "memory_tool.py"
    copied_script = False
    if force or not script_target.exists():
        shutil.copy2(Path(__file__), script_target)
        copied_script = True

    files_status: dict[str, str] = {}
    files_status[".gitignore"] = ensure_gitignore_has_codex(repo_root)
    files_status["AGENTS.md"] = write_file(repo_root / "AGENTS.md", ROOT_AGENTS_CONTENT, force)
    files_status[".codex/AGENTS.md"] = write_file(repo_root / ".codex" / "AGENTS.md", CODEX_AGENTS_CONTENT, force)
    files_status[".codex/memory/index.md"] = write_file(
        memory_root / "index.md",
        INDEX_CONTENT.format(today=today),
        force,
    )
    files_status[".codex/memory/registry.md"] = write_file(
        memory_root / "registry.md",
        REGISTRY_CONTENT.format(today=today),
        force,
    )
    files_status[".codex/memory/context.md"] = write_file(
        memory_root / "context.md",
        CONTEXT_CONTENT.format(today=today, repo_name=repo_root.name),
        force,
    )
    files_status[".codex/memory/runbooks/_template.md"] = write_file(
        memory_root / "runbooks" / "_template.md",
        RUNBOOK_TEMPLATE_CONTENT,
        force,
    )
    files_status[".codex/memory/postmortems/_template.md"] = write_file(
        memory_root / "postmortems" / "_template.md",
        POSTMORTEM_TEMPLATE_CONTENT,
        force,
    )
    files_status[".codex/memory/decisions/_template.md"] = write_file(
        memory_root / "decisions" / "_template.md",
        DECISION_TEMPLATE_CONTENT,
        force,
    )
    files_status[".codex/memory/patterns/_template.md"] = write_file(
        memory_root / "patterns" / "_template.md",
        PATTERN_TEMPLATE_CONTENT,
        force,
    )

    flush_note = memory_root / "runbooks" / "memory-flush-and-hygiene.md"
    note_state = command_scaffold(
        repo_root=repo_root,
        doc_type="runbook",
        slug="memory-flush-and-hygiene",
        title="项目记忆收尾与体检流程",
        tags="memory,workflow,hygiene",
        triggers="任务收尾;写回项目记忆;周期性整理",
        keywords="memory flush,registry,hygiene",
        when_to_read="在非琐碎任务结束后;在周期性整理项目记忆前",
        canonical="true",
        force=force,
    )
    if note_state.get("created") or force:
        flush_frontmatter, _ = parse_frontmatter(read_text(flush_note))
        flush_note.write_text(
            dump_frontmatter(flush_frontmatter) + "\n\n# 项目记忆收尾与体检流程\n\n" + MEMORY_FLUSH_RUNBOOK_CONTENT.strip() + "\n",
            encoding="utf-8",
        )

    sync_result = command_sync_registry(repo_root)
    hygiene_result = command_hygiene(repo_root, stale_days=45)

    warnings: list[str] = []
    if files_status.get("AGENTS.md") == "skipped":
        warnings.append("AGENTS.md 已存在且未覆盖, 请确认其中包含 memory 协议入口与收尾规则.")
    if files_status.get(".codex/AGENTS.md") == "skipped":
        warnings.append(".codex/AGENTS.md 已存在且未覆盖, 请确认其中包含 memory 协议入口与收尾规则.")

    return {
        "repo_root": str(repo_root),
        "copied_script": copied_script,
        "script_path": str(script_target.relative_to(repo_root)),
        "files": files_status,
        "seed_runbook": note_state,
        "sync_registry": sync_result,
        "hygiene": hygiene_result,
        "warnings": warnings,
    }


def scan_memory_notes(repo_root: Path) -> list[NoteRecord]:
    memory_root = repo_memory_root(repo_root)
    notes: list[NoteRecord] = []
    for path in sorted(memory_root.rglob("*.md")):
        if path.name == "_template.md":
            continue
        text = read_text(path)
        frontmatter, body = parse_frontmatter(text)
        rel_path = path.relative_to(memory_root).as_posix()
        notes.append(NoteRecord(path=path, rel_path=rel_path, frontmatter=frontmatter, body=body))
    return notes


def build_registry_table(notes: list[NoteRecord]) -> str:
    lines = [
        "| doc_id | doc_type | path | status | canonical | tags | triggers | last_verified | update_policy | related |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for note in sorted(notes, key=lambda item: (str(item.frontmatter.get("doc_type", "")), item.rel_path)):
        fm = note.frontmatter
        tags = ", ".join(fm.get("tags", [])) if isinstance(fm.get("tags"), list) else str(fm.get("tags", ""))
        triggers = ", ".join(fm.get("triggers", [])) if isinstance(fm.get("triggers"), list) else str(fm.get("triggers", ""))
        related = ", ".join(fm.get("related", [])) if isinstance(fm.get("related"), list) else str(fm.get("related", ""))
        lines.append(
            "| {doc_id} | {doc_type} | `{path}` | {status} | {canonical} | `{tags}` | `{triggers}` | {last_verified} | {update_policy} | `{related}` |".format(
                doc_id=fm.get("doc_id", ""),
                doc_type=fm.get("doc_type", ""),
                path=note.rel_path,
                status=fm.get("status", ""),
                canonical=str(fm.get("canonical", "")).lower(),
                tags=tags,
                triggers=triggers,
                last_verified=fm.get("last_verified", ""),
                update_policy=fm.get("update_policy", ""),
                related=related,
            )
        )
    return "\n".join(lines)


def ensure_registry_file(memory_root: Path) -> Path:
    registry_path = memory_root / "registry.md"
    if registry_path.exists():
        return registry_path
    registry_path.write_text(
        "\n".join(
            [
                "---",
                "doc_id: context-memory-registry",
                "doc_type: registry",
                "title: 项目记忆总表",
                "status: active",
                "scope: repo",
                "tags: [memory, registry, metadata]",
                "triggers:",
                "  - 在打开记忆文档前",
                "keywords:",
                "  - registry",
                "  - 记忆总表",
                "canonical: true",
                "related: []",
                "supersedes: []",
                f"last_verified: {date.today().isoformat()}",
                "confidence: high",
                "update_policy: merge",
                "when_to_read:",
                "  - 在选择记忆文档前",
                "---",
                "",
                "# 项目记忆总表",
                "",
                "## 条目表",
                "",
                "| doc_id | doc_type | path | status | canonical | tags | triggers | last_verified | update_policy | related |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                "",
                "## 合并判断规则",
                "",
                "- 当根因和适用边界相同, 优先更新已有 canonical 文档",
                "- 只有根因或操作边界明显变化时, 才新建记忆文档",
            ]
        ),
        encoding="utf-8",
    )
    return registry_path


def update_registry_content(registry_text: str, table_text: str) -> str:
    header_candidates = ["## 条目表", "## Suggested Columns"]
    footer_candidates = ["## 合并判断规则", "## Merge Decision Heuristic"]
    header = next((item for item in header_candidates if item in registry_text), header_candidates[0])
    footer = next((item for item in footer_candidates if item in registry_text), footer_candidates[0])
    if header in registry_text and footer in registry_text:
        before, remainder = registry_text.split(header, 1)
        middle, after = remainder.split(footer, 1)
        return f"{before}{header}\n\n{table_text}\n\n{footer}{after}"
    return registry_text.rstrip() + "\n\n" + header + "\n\n" + table_text + "\n"


def command_sync_registry(repo_root: Path) -> dict[str, Any]:
    memory_root = repo_memory_root(repo_root)
    registry_path = ensure_registry_file(memory_root)
    notes = scan_memory_notes(repo_root)
    table = build_registry_table(notes)
    updated = update_registry_content(read_text(registry_path), table)
    registry_path.write_text(updated, encoding="utf-8")
    return {
        "registry_path": str(registry_path.relative_to(repo_root)),
        "entry_count": len(notes),
        "note_paths": [note.rel_path for note in notes],
    }


def strip_existing_frontmatter(text: str) -> str:
    _, body = parse_frontmatter(text)
    return body if body else text


def infer_frontmatter(
    doc_type: str,
    slug: str,
    title: str,
    tags: list[str],
    triggers: list[str],
    keywords: list[str],
    when_to_read: list[str],
    canonical: bool | None,
    aliases: list[str] | None = None,
) -> dict[str, Any]:
    today = date.today().isoformat()
    default_canonical = canonical if canonical is not None else (doc_type != "postmortem")
    doc_prefix = {
        "runbook": "runbook",
        "postmortem": "postmortem",
        "decision": "decision",
        "pattern": "pattern",
    }[doc_type]
    return {
        "doc_id": f"{doc_prefix}-{slug}",
        "doc_type": doc_type,
        "title": title,
        "status": "active",
        "scope": "repo",
        "tags": tags or [doc_type],
        "triggers": triggers or default_list("处理 {title} 时", title, slug),
        "keywords": keywords or [slug.replace("-", " ")],
        "canonical": default_canonical,
        "related": [],
        "supersedes": [],
        "last_verified": today,
        "confidence": "medium" if doc_type == "postmortem" else "high",
        "update_policy": "new-note-only-if-new-root-cause" if doc_type == "postmortem" else "merge",
        "when_to_read": when_to_read or default_list("在处理 {title} 前", title, slug),
        "aliases": aliases or [],
    }


def command_scaffold(
    repo_root: Path,
    doc_type: str,
    slug: str,
    title: str,
    tags: str,
    triggers: str,
    keywords: str,
    when_to_read: str,
    canonical: str | None,
    aliases: str = "",
    force: bool = False,
) -> dict[str, Any]:
    memory_root = repo_memory_root(repo_root)
    target_dir = memory_root / TEMPLATE_DIRS[doc_type]
    template_path = target_dir / "_template.md"
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    target_path = target_dir / f"{slug}.md"
    if target_path.exists() and not force:
        text = read_text(target_path)
        fm, _ = parse_frontmatter(text)
        return {
            "created": False,
            "path": str(target_path.relative_to(repo_root)),
            "doc_id": fm.get("doc_id", ""),
            "reason": "exists",
        }

    template_body = strip_existing_frontmatter(read_text(template_path))
    frontmatter = infer_frontmatter(
        doc_type=doc_type,
        slug=slug,
        title=title,
        tags=normalize_list(tags, fallback=[doc_type]),
        triggers=normalize_list(triggers),
        keywords=normalize_list(keywords, fallback=[slug]),
        when_to_read=normalize_list(when_to_read),
        canonical=None if canonical is None else canonical == "true",
        aliases=normalize_list(aliases),
    )
    rendered = dump_frontmatter(frontmatter) + "\n\n" + template_body.strip() + "\n"
    target_path.write_text(rendered, encoding="utf-8")
    return {
        "created": True,
        "path": str(target_path.relative_to(repo_root)),
        "doc_id": frontmatter["doc_id"],
    }


def command_update(
    repo_root: Path,
    *,
    path: str,
    title: str | None = None,
    tags: str | None = None,
    triggers: str | None = None,
    keywords: str | None = None,
    when_to_read: str | None = None,
    aliases: str | None = None,
    confidence: str | None = None,
    status: str | None = None,
    canonical: str | None = None,
    body_append: str | None = None,
) -> dict[str, Any]:
    note_path = resolve_memory_note_path(repo_root, path)
    if not note_path.exists():
        raise FileNotFoundError(f"Memory note not found: {note_path}")
    frontmatter, body = parse_frontmatter(read_text(note_path))
    updated_fields: list[str] = []

    updates: list[tuple[str, Any]] = [
        ("title", title.strip() if isinstance(title, str) and title.strip() else None),
        ("tags", normalize_list(tags) if tags is not None else None),
        ("triggers", normalize_list(triggers) if triggers is not None else None),
        ("keywords", normalize_list(keywords) if keywords is not None else None),
        ("when_to_read", normalize_list(when_to_read) if when_to_read is not None else None),
        ("aliases", normalize_list(aliases) if aliases is not None else None),
        ("confidence", confidence.strip() if isinstance(confidence, str) and confidence.strip() else None),
        ("status", status.strip() if isinstance(status, str) and status.strip() else None),
    ]
    for key, value in updates:
        if value is None:
            continue
        if frontmatter.get(key) == value:
            continue
        frontmatter[key] = value
        updated_fields.append(key)

    if canonical is not None:
        canonical_value = canonical == "true"
        if frontmatter.get("canonical") is not canonical_value:
            frontmatter["canonical"] = canonical_value
            updated_fields.append("canonical")

    next_body = body
    if body_append is not None and body_append.strip():
        suffix = body.rstrip()
        next_body = f"{suffix}\n\n{body_append.strip()}\n" if suffix else body_append.strip() + "\n"
        updated_fields.append("body")

    rendered = dump_frontmatter(frontmatter) + "\n\n" + next_body.strip() + "\n"
    note_path.write_text(rendered, encoding="utf-8")
    return {
        "updated": True,
        "path": str(note_path.relative_to(repo_root)),
        "doc_id": str(frontmatter.get("doc_id", "")).strip(),
        "updated_fields": updated_fields,
    }


def command_delete(
    repo_root: Path,
    *,
    path: str,
) -> dict[str, Any]:
    note_path = resolve_memory_note_path(repo_root, path)
    if not note_path.exists():
        raise FileNotFoundError(f"Memory note not found: {note_path}")
    memory_root = repo_memory_root(repo_root)
    relative_note_path = note_path.relative_to(memory_root)
    if not relative_note_path.parts or relative_note_path.parts[0] not in set(TEMPLATE_DIRS.values()):
        raise ValueError("path must point to a canonical memory note entry")
    frontmatter, _ = parse_frontmatter(read_text(note_path))
    note_path.unlink()
    return {
        "deleted": True,
        "path": str(note_path.relative_to(repo_root)),
        "route_path": f"memory/{relative_note_path.as_posix()}",
        "doc_id": str(frontmatter.get("doc_id", "")).strip(),
    }


def normalized_text(value: Any) -> str:
    return qi.normalized_text(value)


def search_normalize(value: Any) -> str:
    return qi.search_normalize(value)


def extract_query_terms(query: str) -> tuple[list[str], list[str], list[str]]:
    return qi.extract_query_terms(query)


def route_match_terms(query: str, text: str) -> list[str]:
    english_terms, cjk_terms, symbol_terms = extract_query_terms(query)
    normalized = search_normalize(text)
    english_tokens = set(re.findall(r"[a-z0-9]{2,}", normalized))
    lowered = str(text).lower()
    matched: list[str] = []
    for term in symbol_terms:
        if term in lowered and term not in matched:
            matched.append(term)
    for term in english_terms:
        if term in english_tokens and term not in matched:
            matched.append(term)
    compact = re.sub(r"\s+", "", text)
    for term in cjk_terms:
        if term in compact and term not in matched:
            matched.append(term)
    return matched


def route_min_score_threshold(query: str) -> float:
    english_terms, cjk_terms, symbol_terms = extract_query_terms(query)
    has_explicit_ascii = bool(re.search(r"[a-z0-9]{2,}", search_normalize(query)))
    if cjk_terms and not has_explicit_ascii and not symbol_terms:
        return MIN_CJK_SCORE_THRESHOLD
    return MIN_SCORE_THRESHOLD




def compute_term_idf(all_texts: list[str], query_terms: tuple[list[str], list[str], list[str]]) -> dict[str, float]:
    """Compute IDF for each query term across all document texts."""
    english_terms, cjk_terms, symbol_terms = query_terms
    n_docs = max(len(all_texts), 1)
    idf_map: dict[str, float] = {}
    for term in english_terms + symbol_terms:
        count = sum(1 for txt in all_texts if term in txt.lower())
        idf_map[term] = math.log((n_docs + 1) / (1 + count)) + 0.5
    for term in cjk_terms:
        compact = [re.sub(r"\s+", "", txt) for txt in all_texts]
        count = sum(1 for txt in compact if term in txt)
        idf_map[term] = math.log((n_docs + 1) / (1 + count)) + 0.5
    return idf_map


def build_query_idf(notes: list[NoteRecord], assets: list[AssetRecord], query: str) -> dict[str, float]:
    all_texts = []
    for note in notes:
        fm = note.frontmatter
        all_texts.append(" ".join([
            str(fm.get("title", "")), str(fm.get("tags", "")),
            str(fm.get("keywords", "")), str(fm.get("triggers", "")),
            str(fm.get("scope", "")), note.path.stem.lower(),
        ]))
    for asset in assets:
        all_texts.append(" ".join([asset.name, asset.description, str(asset.rel_path).lower()]))
    return compute_term_idf(all_texts, extract_query_terms(query))


def empty_asset_index_payload(repo_root: Path) -> dict[str, Any]:
    return {
        "generated_at": "",
        "repo_root": str(repo_root.resolve()),
        "counts": {
            "skills": 0,
            "scripts": 0,
            "task_assets": 0,
            "session_assets": 0,
            "runbooks": 0,
            "patterns": 0,
            "executables": 0,
            "insight_entries": 0,
        },
        "skills": [],
        "scripts": [],
        "task_assets": [],
        "session_assets": [],
        "memory": {"runbooks": [], "patterns": [], "executables": []},
        "insight_entries": [],
    }


def scan_asset_records(
    repo_root: Path,
    asset_payload: dict[str, Any] | None = None,
    *,
    build_if_missing: bool = True,
) -> list[AssetRecord]:
    payload = asset_payload
    if payload is None:
        payload = bai.build_asset_index(repo_root) if build_if_missing else empty_asset_index_payload(repo_root)
    records: list[AssetRecord] = []
    for entry in payload.get("scripts", []):
        rel_path = str(entry.get("path", "")).strip()
        if not rel_path:
            continue
        path = (repo_root / rel_path).resolve()
        records.append(
            AssetRecord(
                path=path,
                rel_path=rel_path,
                asset_type="script",
                name=str(entry.get("name", "")).strip() or path.stem,
                description=f"script {entry.get('language', '')}".strip(),
            )
        )
    for entry in payload.get("skills", []):
        rel_path = str(entry.get("path", "")).strip()
        if not rel_path:
            continue
        path = (repo_root / rel_path).resolve()
        records.append(
            AssetRecord(
                path=path,
                rel_path=rel_path,
                asset_type="skill",
                name=str(entry.get("name", "")).strip() or path.stem,
                description=str(entry.get("description", "")).strip(),
                )
            )
    for entry in payload.get("task_assets", []):
        rel_path = str(entry.get("path", "")).strip()
        if not rel_path:
            continue
        path = (repo_root / rel_path).resolve()
        records.append(
            AssetRecord(
                path=path,
                rel_path=rel_path,
                asset_type="task-doc",
                name=str(entry.get("name", "")).strip() or path.stem,
                description=str(entry.get("description", "")).strip(),
            )
        )
    for entry in payload.get("session_assets", []):
        rel_path = str(entry.get("path", "")).strip()
        if not rel_path:
            continue
        path = (repo_root / rel_path).resolve()
        records.append(
            AssetRecord(
                path=path,
                rel_path=rel_path,
                asset_type=str(entry.get("asset_type", "")).strip() or ("archived_session" if "archived_sessions" in rel_path else "session"),
                name=str(entry.get("name", "")).strip() or path.stem,
                description=str(entry.get("description", "")).strip(),
            )
        )
    for entry in payload.get("memory", {}).get("executables", []):
        rel_path = str(entry.get("path", "")).strip()
        if not rel_path:
            continue
        path = (repo_root / rel_path).resolve()
        records.append(
            AssetRecord(
                path=path,
                rel_path=rel_path,
                asset_type="executable",
                name=str(entry.get("name", "")).strip() or path.stem,
                description=str(entry.get("summary", "")).strip(),
            )
        )
    return records


def note_is_route_excluded(note: NoteRecord) -> bool:
    if note.path.name in ROUTE_EXCLUDED_FILENAMES:
        return True
    if note.path.name == "_template.md":
        return True
    if note.rel_path.endswith("/_template.md"):
        return True
    return False


def note_is_fallback_only(note: NoteRecord) -> bool:
    return note.path.name in ROUTE_FALLBACK_ONLY_FILENAMES


def note_is_runtime_eligible(note: NoteRecord) -> bool:
    if note_is_route_excluded(note):
        return False
    if note.frontmatter.get("status") != "active":
        return False
    if note_is_fallback_only(note):
        return False
    return True


def note_excerpt(note: NoteRecord) -> str:
    return note.body[:BODY_EXCERPT_LIMIT]


def score_note_for_query(note: NoteRecord, query: str, idf_map: dict[str, float] | None = None) -> dict[str, Any]:
    fm = note.frontmatter
    english_terms, cjk_terms, symbol_terms = extract_query_terms(query)
    total_terms = len(english_terms) + len(cjk_terms) + len(symbol_terms)
    total_terms = max(total_terms, 1)
    reasons: list[str] = []
    score = 0.0

    field_values = {
        "title": normalized_text(fm.get("title", "")),
        "aliases": normalized_text(fm.get("aliases", [])),
        "filename": f"{note.path.stem} {note.rel_path}",
        "keywords": normalized_text(fm.get("keywords", [])),
        "triggers": normalized_text(fm.get("triggers", [])),
        "when_to_read": normalized_text(fm.get("when_to_read", [])),
        "tags": normalized_text(fm.get("tags", [])),
        "body": note_excerpt(note),
    }
    for field_name, weight in ROUTE_FIELD_WEIGHTS.items():
        matched = route_match_terms(query, field_values[field_name])
        if not matched:
            continue
        idf_factor = 1.0
        if idf_map:
            idf_factor = max(idf_map.get(t, 1.0) for t in matched) if matched else 1.0
        contribution = weight * (len(matched) / total_terms) * idf_factor
        score += contribution
        reasons.append(f"{field_name}:{', '.join(matched)} (+{contribution:.2f})")

    canonical_boost = CANONICAL_BOOST if score > 0 and fm.get("canonical") is True else 0.0
    if canonical_boost:
        score += canonical_boost
        reasons.append(f"canonical (+{canonical_boost:.2f})")
    doc_type_boost = DOC_TYPE_BOOSTS.get(fm.get("doc_type", ""), 0.0)
    if doc_type_boost and score > 0:
        score += doc_type_boost
        reasons.append(f"doc_type:{fm.get('doc_type','')} (+{doc_type_boost:.2f})")
    confidence = str(fm.get("confidence", "high")).strip().lower() or "high"
    confidence_boost = CONFIDENCE_BOOSTS.get(confidence, 0.0)
    if score > 0:
        score += confidence_boost
        reasons.append(f"confidence:{confidence} ({confidence_boost:+.2f})")

    return {
        "path": str(note.path),
        "repo_path": str(note.path.relative_to(note.path.parents[2])),
        "kind": "memory",
        "title": fm.get("title", ""),
        "doc_type": fm.get("doc_type", ""),
        "canonical": fm.get("canonical") is True,
        "score": round(score, 4),
        "reasons": reasons,
        "eligible": True,
    }


def score_asset_for_query(asset: AssetRecord, query: str, idf_map: dict[str, float] | None = None) -> dict[str, Any]:
    english_terms, cjk_terms, symbol_terms = extract_query_terms(query)
    total_terms = len(english_terms) + len(cjk_terms) + len(symbol_terms)
    total_terms = max(total_terms, 1)
    score = 0.0
    reasons: list[str] = []
    field_values = {
        "name": asset.name,
        "path": asset.rel_path,
        "description": asset.description,
    }
    lowered_path = asset.rel_path.lower()
    for field_name, weight in ASSET_FIELD_WEIGHTS.items():
        matched = route_match_terms(query, field_values[field_name])
        if not matched:
            continue
        idf_factor = 1.0
        if idf_map:
            idf_factor = max(idf_map.get(t, 1.0) for t in matched) if matched else 1.0
        contribution = weight * (len(matched) / total_terms) * idf_factor
        score += contribution
        reasons.append(f"{field_name}:{', '.join(matched)} (+{contribution:.2f})")
    exact_symbols = [term for term in symbol_terms if term in lowered_path]
    if exact_symbols:
        score += ASSET_EXACT_SYMBOL_BOOST
        reasons.append(f"exact_symbol:{', '.join(exact_symbols)} (+{ASSET_EXACT_SYMBOL_BOOST:.2f})")
    type_boost = ASSET_TYPE_BOOSTS.get(asset.asset_type, 0.0)
    if type_boost and score > 0:
        score += type_boost
        reasons.append(f"asset_type:{asset.asset_type} (+{type_boost:.2f})")
    if asset.asset_type == "task-doc" and score > 0:
        normalized_query = qi.search_normalize(query)
        explicit_task_doc = any(term in normalized_query for term in TASK_DOC_QUERY_TERMS)
        path_terms = [
            part
            for part in qi.search_normalize(asset.rel_path).split()
            if len(part) >= 4 and any(ch.isdigit() for ch in part)
        ]
        if any(term in normalized_query for term in path_terms):
            explicit_task_doc = True
        if not explicit_task_doc:
            penalty = max(score * 0.85, 0.9)
            score = max(score - penalty, 0.0)
            reasons.append(f"task_doc_boundary (-{penalty:.2f})")
    return {
        "path": str(asset.path),
        "repo_path": asset.rel_path,
        "kind": "asset",
        "asset_type": asset.asset_type,
        "title": asset.name,
        "doc_type": asset.asset_type,
        "score": round(score, 4),
        "reasons": reasons,
        "eligible": True,
    }


def route_context_signature(repo_root: Path) -> tuple[int, int]:
    candidates = [
        repo_root / ".codex" / "memory",
        repo_root / ".codex" / "tasks",
        bai.asset_index_path(repo_root),
    ]
    existing = [path for path in candidates if path.exists()]
    latest_mtime_ns = max((path.stat().st_mtime_ns for path in existing), default=0)
    return latest_mtime_ns, len(existing)


def cache_route_context(cache_key: str, route_context: dict[str, Any]) -> None:
    ROUTE_CONTEXT_CACHE[cache_key] = route_context
    ROUTE_CONTEXT_CACHE.move_to_end(cache_key)
    while len(ROUTE_CONTEXT_CACHE) > ROUTE_CONTEXT_CACHE_LIMIT:
        ROUTE_CONTEXT_CACHE.popitem(last=False)


def get_route_context(repo_root: Path) -> dict[str, Any]:
    cache_key = str(repo_root.resolve())
    route_context = ROUTE_CONTEXT_CACHE.get(cache_key)
    signature = route_context_signature(repo_root)
    if route_context is None or route_context.get("signature") != signature:
        notes = scan_memory_notes(repo_root)
        asset_payload = bai.read_asset_index(repo_root) or empty_asset_index_payload(repo_root)
        assets = scan_asset_records(repo_root, asset_payload=asset_payload, build_if_missing=False)
        route_context = {
            "signature": signature,
            "notes": notes,
            "asset_payload": asset_payload,
            "assets": assets,
        }
        cache_route_context(cache_key, route_context)
        return route_context
    ROUTE_CONTEXT_CACHE.move_to_end(cache_key)
    return route_context


def score_insight_for_query(entry: dict[str, Any], query: str, idf_map: dict[str, float] | None = None) -> dict[str, Any]:
    english_terms, cjk_terms, symbol_terms = extract_query_terms(query)
    total_terms = len(english_terms) + len(cjk_terms) + len(symbol_terms)
    total_terms = max(total_terms, 1)
    reasons: list[str] = []
    score = 0.0
    field_values = {
        "title": normalized_text(entry.get("title", "")),
        "aliases": normalized_text(entry.get("aliases", [])),
        "keywords": normalized_text(entry.get("keywords", [])),
        "triggers": normalized_text(entry.get("triggers", [])),
        "summary": normalized_text(entry.get("summary", "")),
    }
    field_weights = {
        "title": 0.9,
        "aliases": 1.0,
        "keywords": 1.0,
        "triggers": 1.1,
        "summary": 0.4,
    }
    for field_name, weight in field_weights.items():
        matched = route_match_terms(query, field_values[field_name])
        if not matched:
            continue
        idf_factor = 1.0
        if idf_map:
            idf_factor = max(idf_map.get(t, 1.0) for t in matched) if matched else 1.0
        contribution = weight * (len(matched) / total_terms) * idf_factor
        score += contribution
        reasons.append(f"insight_{field_name}:{', '.join(matched)} (+{contribution:.2f})")
    return {
        "pointer": str(entry.get("pointer", "")).strip(),
        "kind": str(entry.get("kind", "")).strip(),
        "score": round(score, 4),
        "reasons": reasons,
        "source": str(entry.get("source", "")).strip(),
    }


def apply_learning_boost(repo_root: Path, query: str, result: dict[str, Any], *, enabled: bool = True) -> dict[str, Any]:
    if not enabled:
        return result
    repo_path = str(result.get("repo_path", "")).strip()
    if not repo_path:
        return result
    learning = rl.learning_boost(repo_root, query=query, target_path=repo_path)
    if not learning:
        return result
    boosted = dict(result)
    boosted["score"] = round(float(boosted.get("score", 0.0)) + float(learning["boost"]), 4)
    boosted["reasons"] = list(boosted.get("reasons", [])) + [f"{learning['reason']} (+{learning['boost']:.2f})"]
    return boosted


def stabilize_session_asset_ranking(ranked_notes: list[dict[str, Any]], ranked_assets: list[dict[str, Any]]) -> None:
    canonical_runbooks = [
        item
        for item in ranked_notes
        if item.get("doc_type") == "runbook" and item.get("canonical") is True and float(item.get("score", 0.0)) > 0
    ]
    if not canonical_runbooks:
        return
    best_runbook = max(canonical_runbooks, key=lambda item: float(item.get("score", 0.0)))
    ceiling = max(float(best_runbook.get("score", 0.0)) - SESSION_MEMORY_SCORE_MARGIN, 0.0)
    for asset in ranked_assets:
        if asset.get("asset_type") not in SESSION_ASSET_TYPES:
            continue
        current_score = float(asset.get("score", 0.0))
        if current_score < float(best_runbook.get("score", 0.0)):
            continue
        penalty = current_score - ceiling
        if penalty <= 0:
            continue
        asset["score"] = round(ceiling, 4)
        asset["reasons"] = list(asset.get("reasons", [])) + [
            f"session_reference_ceiling:{best_runbook.get('repo_path', '')} (-{penalty:.2f})"
        ]


def has_executable_recall_override(hits: list[dict[str, Any]]) -> bool:
    if not hits:
        return False
    top_hit = hits[0]
    top_is_runbook = top_hit.get("kind") == "memory" and top_hit.get("doc_type") == "runbook"
    if not top_is_runbook:
        return False
    reasons = [str(item) for item in top_hit.get("reasons", [])]
    if any(reason.startswith("learned_related_query:") for reason in reasons):
        return True
    if len(hits) < 2:
        return False
    second_hit = hits[1]
    return second_hit.get("kind") == "asset" and second_hit.get("asset_type") in SESSION_ASSET_TYPES


def route_with_context(
    repo_root: Path,
    task: str,
    top_k: int,
    *,
    route_context: dict[str, Any],
    use_insight: bool = True,
    use_learning: bool = True,
    record_event: bool = True,
) -> dict[str, Any]:
    notes = route_context["notes"]
    asset_payload = route_context["asset_payload"]
    assets = route_context["assets"]
    idf_map = build_query_idf(notes, assets, task)
    ranked_notes: list[dict[str, Any]] = []
    ranked_assets: list[dict[str, Any]] = []
    note_lookup: dict[str, NoteRecord] = {}
    asset_lookup: dict[str, AssetRecord] = {asset.rel_path: asset for asset in assets}
    for note in notes:
        if not note_is_runtime_eligible(note):
            continue
        repo_path = f"memory/{note.rel_path}"
        note_lookup[repo_path] = note
        result = apply_learning_boost(repo_root, task, score_note_for_query(note, task, idf_map), enabled=use_learning)
        if result["score"] <= 0:
            continue
        ranked_notes.append(result)
    for asset in assets:
        result = apply_learning_boost(repo_root, task, score_asset_for_query(asset, task, idf_map), enabled=use_learning)
        if result["score"] <= 0:
            continue
        ranked_assets.append(result)

    stabilize_session_asset_ranking(ranked_notes, ranked_assets)

    if use_insight:
        ranked_by_path: dict[str, dict[str, Any]] = {
            result["repo_path"]: result for result in [*ranked_notes, *ranked_assets]
        }
        for entry in asset_payload.get("insight_entries", []):
            insight = score_insight_for_query(entry, task, idf_map)
            if insight["score"] <= 0:
                continue
            pointer = insight["pointer"]
            existing = ranked_by_path.get(pointer)
            if existing is None:
                if pointer in note_lookup:
                    existing = score_note_for_query(note_lookup[pointer], task, idf_map)
                elif pointer in asset_lookup:
                    existing = score_asset_for_query(asset_lookup[pointer], task, idf_map)
                else:
                    continue
            boosted = dict(existing)
            original_score = float(boosted.get("score", 0.0))
            insight_add = INSIGHT_POINTER_BOOST + float(insight["score"])
            max_insight = max(original_score * 0.5, 0.3)
            insight_add = min(insight_add, max_insight)
            boosted["score"] = round(original_score + insight_add, 4)
            boosted["reasons"] = list(boosted.get("reasons", [])) + insight["reasons"] + [
                f"insight_pointer:{insight['source'] or 'index'} (+{INSIGHT_POINTER_BOOST:.2f})"
            ]
            ranked_by_path[pointer] = boosted

        ranked_notes = [item for item in ranked_by_path.values() if item["kind"] == "memory" and item["score"] > 0]
        ranked_assets = [item for item in ranked_by_path.values() if item["kind"] == "asset" and item["score"] > 0]

    ranked_notes.sort(key=lambda item: (-item["score"], item["path"]))
    ranked_assets.sort(key=lambda item: (-item["score"], item["path"]))
    ranked = ranked_notes + ranked_assets
    ranked.sort(key=lambda item: (-item["score"], item["path"]))
    hits = ranked[: max(top_k, 1)]
    decision_hits = ranked[: max(top_k, 2)]

    fallback_context = False
    executable_recall_override = has_executable_recall_override(decision_hits)
    min_score_threshold = route_min_score_threshold(task)
    if not decision_hits:
        fallback_context = True
    elif decision_hits[0]["score"] < min_score_threshold and not executable_recall_override:
        fallback_context = True
    elif len(decision_hits) > 1 and decision_hits[0]["score"] > 0 and (decision_hits[1]["score"] / decision_hits[0]["score"]) >= AMBIGUITY_RATIO:
        top_hit = decision_hits[0]
        second_hit = decision_hits[1]
        top_is_runbook = top_hit.get("kind") == "memory" and top_hit.get("doc_type") == "runbook"
        second_is_session = second_hit.get("kind") == "asset" and second_hit.get("asset_type") in SESSION_ASSET_TYPES
        if not (top_is_runbook and second_is_session):
            fallback_context = True

    payload = {
        "query": task,
        "route_contract_version": 4,
        "hits": [
            {
                "path": hit["repo_path"],
                "kind": hit["kind"],
                "title": hit["title"],
                "doc_type": hit["doc_type"],
                "score": hit["score"],
                "reasons": hit["reasons"],
                **({"asset_type": hit["asset_type"]} if hit["kind"] == "asset" else {}),
            }
            for hit in hits
        ],
        "memory_hits": [
            {
                "path": hit["repo_path"],
                "kind": "memory",
                "title": hit["title"],
                "doc_type": hit["doc_type"],
                "score": hit["score"],
                "reasons": hit["reasons"],
            }
            for hit in ranked_notes[: max(top_k, 1)]
        ],
        "asset_hits": [
            {
                "path": hit["repo_path"],
                "kind": "asset",
                "asset_type": hit["asset_type"],
                "title": hit["title"],
                "doc_type": hit["doc_type"],
                "score": hit["score"],
                "reasons": hit["reasons"],
            }
            for hit in ranked_assets[: max(top_k, 1)]
        ],
        "fallback_context": fallback_context,
        "adoption_hint": (
            "If you used any hit to complete the task, record adoption:\n"
            "  codex-memo k --task \\<task> --route-query \\<query> --route-event-id \\<event_id> --surfaced-hits-hash \\<hits_hash> --selected-hit \\<path> --adopted-hit \\<path> --observed-actions \\<what> --evidence-paths \\<path1,path2>\n"
            "This improves future route accuracy."
        ),
    }
    route_event = {"event_id": "", "hits_hash": ""}
    if record_event:
        route_event = rl.record_route_event(repo_root, query=task, hits=payload["hits"], fallback_context=fallback_context)
    payload["route_event_id"] = route_event["event_id"]
    payload["surfaced_hits_hash"] = route_event["hits_hash"]
    return payload


def command_route(
    repo_root: Path,
    task: str,
    top_k: int,
    *,
    use_insight: bool = True,
    use_learning: bool = True,
    record_event: bool = True,
) -> dict[str, Any]:
    route_context = get_route_context(repo_root)
    return route_with_context(
        repo_root,
        task,
        top_k,
        route_context=route_context,
        use_insight=use_insight,
        use_learning=use_learning,
        record_event=record_event,
    )


def command_inspect(repo_root: Path, task: str, target_path: str) -> dict[str, Any]:
    candidate = Path(target_path)
    if not candidate.is_absolute():
        parts = candidate.parts
        if len(parts) >= 2 and parts[0] == ".codex" and parts[1] == "memory":
            candidate = (repo_root / candidate).resolve()
        elif parts and parts[0] == "memory":
            candidate = (repo_memory_root(repo_root) / Path(*parts[1:])).resolve()
        else:
            candidate = (repo_root / candidate).resolve()
    if not candidate.exists():
        raise FileNotFoundError(f"Note not found: {target_path}")
    memory_root = repo_memory_root(repo_root)
    if not candidate.is_relative_to(memory_root):
        raise FileNotFoundError(f"Path is not under project memory: {target_path}")

    text = read_text(candidate)
    fm, body = parse_frontmatter(text)
    rel_path = candidate.relative_to(memory_root).as_posix()
    note = NoteRecord(path=candidate, rel_path=rel_path, frontmatter=fm, body=body)

    excluded = note_is_route_excluded(note)
    fallback_only = note_is_fallback_only(note)
    eligible = note_is_runtime_eligible(note)
    reasons: list[str] = []
    score = 0.0
    if excluded:
        reasons.append("excluded:file")
    elif fallback_only:
        reasons.append("fallback_only:context")
    elif fm.get("status") != "active":
        reasons.append(f"excluded:status={fm.get('status')}")
    else:
        notes = scan_memory_notes(repo_root)
        asset_payload = bai.build_asset_index(repo_root)
        assets = scan_asset_records(repo_root, asset_payload=asset_payload)
        idf_map = build_query_idf(notes, assets, task)
        scored = score_note_for_query(note, task, idf_map)
        score = scored["score"]
        reasons = scored["reasons"]

    return {
        "query": task,
        "source": "project",
        "path": rel_path,
        "eligible": eligible,
        "fallback_only": fallback_only,
        "excluded": excluded,
        "score": score,
        "reasons": reasons,
    }


def default_overview_must_read(repo_root: Path, max_must_read: int) -> list[str]:
    selected = ["context.md"]
    notes = scan_memory_notes(repo_root)
    decisions = [
        note.rel_path
        for note in notes
        if note_is_runtime_eligible(note)
        and note.frontmatter.get("canonical") is True
        and note.frontmatter.get("doc_type") == "decision"
    ]
    runbooks = [
        note.rel_path
        for note in notes
        if note_is_runtime_eligible(note)
        and note.frontmatter.get("canonical") is True
        and note.frontmatter.get("doc_type") == "runbook"
    ]
    for rel_path in decisions[:2] + runbooks[:1]:
        if rel_path not in selected:
            selected.append(rel_path)
        if len(selected) >= max_must_read:
            break
    return selected[:max_must_read]


def command_overview(repo_root: Path, max_must_read: int) -> dict[str, Any]:
    context_path = repo_memory_root(repo_root) / "context.md"
    if not context_path.exists():
        return {
            "repo_name": repo_root.name,
            "repo_type": "",
            "project_summary": "",
            "entrypoints": [],
            "key_dirs": [],
            "common_tasks": [],
            "must_read": ["context.md"],
        }

    fm, _ = parse_frontmatter(read_text(context_path))
    must_read = fm.get("must_read")
    if isinstance(must_read, list) and must_read:
        must_read_list = [str(item) for item in must_read[:max_must_read]]
    else:
        must_read_list = default_overview_must_read(repo_root, max_must_read)

    def list_field(name: str) -> list[str]:
        value = fm.get(name, [])
        return [str(item) for item in value] if isinstance(value, list) else []

    return {
        "repo_name": repo_root.name,
        "repo_type": str(fm.get("repo_type", "")).strip().strip("'\""),
        "project_summary": str(fm.get("project_summary", "")).strip().strip("'\""),
        "entrypoints": list_field("entrypoints"),
        "key_dirs": list_field("key_dirs"),
        "common_tasks": list_field("common_tasks"),
        "must_read": must_read_list or ["context.md"],
    }


def parse_iso_date(raw: str) -> date | None:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except Exception:
        return None


def command_hygiene(repo_root: Path, stale_days: int) -> dict[str, Any]:
    notes = scan_memory_notes(repo_root)
    issues: list[dict[str, Any]] = []

    seen_doc_ids: dict[str, list[str]] = {}
    seen_canonical_title: dict[tuple[str, str], list[str]] = {}
    active_canonical_decisions: list[str] = []
    today = date.today()

    for note in notes:
        fm = note.frontmatter
        for field in REQUIRED_FRONTMATTER_FIELDS:
            if field not in fm:
                issues.append(
                    {
                        "type": "missing_frontmatter_field",
                        "path": note.rel_path,
                        "field": field,
                    }
                )

        doc_id = str(fm.get("doc_id", "")).strip()
        if doc_id:
            seen_doc_ids.setdefault(doc_id, []).append(note.rel_path)

        title = str(fm.get("title", "")).strip().lower()
        doc_type = str(fm.get("doc_type", "")).strip()
        if fm.get("status") == "active" and fm.get("canonical") is True and title:
            seen_canonical_title.setdefault((doc_type, title), []).append(note.rel_path)
        if doc_type == "decision" and fm.get("status") == "active" and fm.get("canonical") is True:
            active_canonical_decisions.append(note.rel_path)

        last_verified = parse_iso_date(str(fm.get("last_verified", "")).strip())
        if fm.get("status") == "active" and last_verified is not None:
            age = (today - last_verified).days
            if age > stale_days:
                issues.append(
                    {
                        "type": "stale_active_note",
                        "path": note.rel_path,
                        "age_days": age,
                    }
                )
                if doc_type == "decision":
                    issues.append(
                        {
                            "type": "decision_retirement_review_due",
                            "path": note.rel_path,
                            "age_days": age,
                        }
                    )

        searchable_values: list[str] = []
        for field in REQUIRED_FRONTMATTER_FIELDS:
            searchable_values.append(normalized_text(fm.get(field, "")))
        searchable_values.append(note.body[:400])
        joined = "\n".join(searchable_values)
        for snippet in PLACEHOLDER_SNIPPETS:
            if snippet in joined:
                issues.append(
                    {
                        "type": "placeholder_value",
                        "path": note.rel_path,
                        "snippet": snippet,
                    }
                )
                break

        if doc_type == "decision":
            normalized_body = normalized_text(note.body[:1200]).lower()
            matched_stage_snippets = sorted({snippet for snippet in DECISION_PHASE_SNIPPETS if snippet.lower() in normalized_body})
            if matched_stage_snippets:
                issues.append(
                    {
                        "type": "decision_may_be_stage_note",
                        "path": note.rel_path,
                        "matched": matched_stage_snippets,
                    }
                )

        if doc_type == "context" and fm.get("status") == "active":
            h2_count = len(re.findall(r"(?m)^##\s+", note.body))
            if h2_count > 4:
                issues.append(
                    {
                        "type": "context_scope_bloat",
                        "path": note.rel_path,
                        "h2_count": h2_count,
                    }
                )

    for doc_id, paths in seen_doc_ids.items():
        if len(paths) > 1:
            issues.append(
                {
                    "type": "duplicate_doc_id",
                    "doc_id": doc_id,
                    "paths": sorted(paths),
                }
            )

    for (doc_type, title), paths in seen_canonical_title.items():
        if len(paths) > 1:
            issues.append(
                {
                    "type": "duplicate_canonical_title",
                    "doc_type": doc_type,
                    "title": title,
                    "paths": sorted(paths),
                }
            )

    if len(active_canonical_decisions) > MAX_ACTIVE_CANONICAL_DECISIONS:
        issues.append(
            {
                "type": "too_many_active_canonical_decisions",
                "count": len(active_canonical_decisions),
                "limit": MAX_ACTIVE_CANONICAL_DECISIONS,
                "paths": sorted(active_canonical_decisions),
            }
        )

    return {
        "issue_count": len(issues),
        "issues": sorted(issues, key=lambda item: (item["type"], json.dumps(item, sort_keys=True))),
    }


def command_flush(args: argparse.Namespace, repo_root: Path) -> dict[str, Any]:
    scaffold_result: dict[str, Any] | None = None
    if args.doc_type or args.slug or args.title:
        if not all([args.doc_type, args.slug, args.title]):
            raise ValueError("flush requires --doc-type, --slug, and --title together when scaffolding")
        scaffold_result = command_scaffold(
            repo_root=repo_root,
            doc_type=args.doc_type,
            slug=args.slug,
            title=args.title,
            tags=args.tags,
            triggers=args.triggers,
            keywords=args.keywords,
            when_to_read=args.when_to_read,
            canonical=args.canonical,
            aliases=args.aliases,
            force=args.force,
        )

    sync_result = command_sync_registry(repo_root)
    hygiene_result = command_hygiene(repo_root, stale_days=args.stale_days)
    return {
        "scaffold": scaffold_result,
        "sync_registry": sync_result,
        "hygiene": hygiene_result,
    }


def emit(payload: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if output_format == "table" and "hits" in payload:
        hits = payload.get("hits") or []
        headers = ["score", "path", "title", "doc_type"]
        print("| " + " | ".join(headers) + " |")
        print("| " + " | ".join(["---"] * len(headers)) + " |")
        for hit in hits:
            print(
                "| {score} | `{path}` | {title} | {doc_type} |".format(
                    score=hit.get("score", ""),
                    path=hit.get("path", ""),
                    title=hit.get("title", ""),
                    doc_type=hit.get("doc_type", ""),
                )
            )
        return
    if output_format == "text":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()

    try:
        if args.command == "bootstrap":
            payload = command_bootstrap(repo_root, force=args.force)
            emit(payload, args.format)
            return 0 if payload["hygiene"]["issue_count"] == 0 else 1

        if args.command == "scaffold":
            payload = command_scaffold(
                repo_root=repo_root,
                doc_type=args.doc_type,
                slug=args.slug,
                title=args.title,
                tags=args.tags,
                triggers=args.triggers,
                keywords=args.keywords,
                when_to_read=args.when_to_read,
                canonical=args.canonical,
                aliases=args.aliases,
                force=args.force,
                )
            emit(payload, args.format)
            return 0

        if args.command == "sync-registry":
            payload = command_sync_registry(repo_root)
            emit(payload, args.format)
            return 0

        if args.command == "hygiene":
            payload = command_hygiene(repo_root, stale_days=args.stale_days)
            emit(payload, args.format)
            return 0 if payload["issue_count"] == 0 else 1

        if args.command == "route":
            payload = command_route(repo_root, task=args.task, top_k=args.top_k)
            emit(payload, args.format)
            return 0

        if args.command == "overview":
            payload = command_overview(repo_root, max_must_read=args.max_must_read)
            emit(payload, args.format)
            return 0

        if args.command == "inspect":
            payload = command_inspect(repo_root, task=args.task, target_path=args.path)
            emit(payload, args.format)
            return 0

        if args.command == "flush":
            payload = command_flush(args, repo_root)
            emit(payload, args.format)
            return 0 if payload["hygiene"]["issue_count"] == 0 else 1
    except Exception as exc:
        error_payload = {"error": str(exc), "command": args.command}
        emit(error_payload, args.format)
        return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
