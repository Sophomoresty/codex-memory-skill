from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock


COMMAND_PATH = Path("/home/sophomores/.local/bin/codex-memo")
SCRIPT_PATH = Path("/home/sophomores/.codex/scripts/codex_memo.py")
MEMORY_TOOL_SCRIPT = Path("/home/sophomores/.codex/scripts/memory_tool.py")
BOOTSTRAP_SCRIPT = Path("/home/sophomores/.codex/skills/project-memory-loop/scripts/bootstrap_project_codex.py")
sys.path.insert(0, str(SCRIPT_PATH.parent))
sys.path.insert(0, str(BOOTSTRAP_SCRIPT.parent))

import bootstrap_project_codex
import codex_memo
import evolution_promote
import memory_benchmark
import session_archive as sa


def run_cli(*args: str, cwd: Path, home_root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CODEX_MEMO_HOME_ROOT"] = str(home_root)
    return subprocess.run(
        [str(COMMAND_PATH), *args],
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def write_note(path: Path, frontmatter: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter.strip() + "\n---\n\n" + body.strip() + "\n", encoding="utf-8")


def read_sqlite_json_rows(db_path: Path, table: str, key_column: str) -> dict[str, dict[str, object]]:
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(f"SELECT {key_column}, payload_json FROM {table}").fetchall()
    finally:
        connection.close()
    payloads: dict[str, dict[str, object]] = {}
    for key, payload_json in rows:
        payload = json.loads(str(payload_json))
        if isinstance(payload, dict):
            payloads[str(key)] = payload
    return payloads


def seed_memory_root(root: Path, *, repo_type: str, summary: str, note_title: str, note_body: str) -> None:
    memory_root = root / ".codex" / "memory"
    for relative in ["runbooks", "postmortems", "decisions", "patterns"]:
        (memory_root / relative).mkdir(parents=True, exist_ok=True)

    write_note(
        memory_root / "context.md",
        textwrap.dedent(
            f"""\
            ---
            doc_id: context-repository-baseline
            doc_type: context
            title: Repository Baseline Context
            repo_type: {repo_type}
            project_summary: {summary}
            entrypoints:
              - main.py
            key_dirs:
              - src/
            common_tasks:
              - memory routing
            must_read:
              - runbooks/core.md
            status: active
            scope: repo
            tags: [repo, context]
            triggers:
              - before non-trivial work
            keywords:
              - context
            canonical: true
            related: []
            supersedes: []
            last_verified: 2026-04-19
            confidence: high
            update_policy: merge
            when_to_read:
              - before repository work
            """
        ),
        "# Context",
    )

    write_note(
        memory_root / "runbooks" / "core.md",
        textwrap.dedent(
            f"""\
            ---
            doc_id: runbook-core
            doc_type: runbook
            title: {note_title}
            status: active
            scope: repo
            tags: [memory, codex]
            triggers:
              - codex cli
            keywords:
              - codex
              - cli
            canonical: true
            related: []
            supersedes: []
            last_verified: 2026-04-19
            confidence: high
            update_policy: merge
            when_to_read:
              - before codex cli work
            """
        ),
        note_body,
    )


def seed_assets(root: Path) -> None:
    scripts_root = root / ".codex" / "scripts"
    skills_root = root / ".codex" / "skills" / "route-helper"
    scripts_root.mkdir(parents=True, exist_ok=True)
    skills_root.mkdir(parents=True, exist_ok=True)
    (scripts_root / "codex_memo.py").write_text("def route_checkpoint_bridge():\n    return 'ok'\n", encoding="utf-8")
    (skills_root / "SKILL.md").write_text(
        textwrap.dedent(
            """\
            ---
            name: route-helper
            description: Use when route, 状态查询, and checkpoint retrieval needs a helper skill.
            ---

            # Route Helper
            """
        ),
        encoding="utf-8",
    )


def seed_task_docs(root: Path, *, task_id: str = "2026-04-19-memory-system-v2") -> None:
    task_root = root / ".codex" / "tasks" / task_id
    task_root.mkdir(parents=True, exist_ok=True)
    (task_root / "prd.md").write_text(
        textwrap.dedent(
            """\
            # PRD: Memory System V2

            ## Task Goal
            完成 retrieval v2, runtime checkpoint, procedural candidate.
            """
        ),
        encoding="utf-8",
    )
    (task_root / "context.md").write_text(
        textwrap.dedent(
            """\
            # Context: Memory System V2

            ## Route Summary
            - execution_gate: miss

            ## Reusable Assets
            - retrieval v2
            - runtime checkpoint
            - procedural candidate
            """
        ),
        encoding="utf-8",
    )
    (task_root / "plan.md").write_text(
        "# Plan\n\n- route task prd review\n",
        encoding="utf-8",
    )
    (task_root / "summary.md").write_text(
        "# Summary\n\n- closeout evidence\n",
        encoding="utf-8",
    )


def seed_thread_recovery_note(root: Path) -> None:
    memory_root = root / ".codex" / "memory" / "runbooks"
    memory_root.mkdir(parents=True, exist_ok=True)
    write_note(
        memory_root / "thread-recovery.md",
        textwrap.dedent(
            """\
            ---
            doc_id: runbook-thread-recovery
            doc_type: runbook
            title: 线程恢复流程
            status: active
            scope: repo
            tags: [codex, threads, recovery]
            triggers:
              - 线程列表恢复
              - 找回之前聊天记录
            keywords:
              - thread recovery
              - chat history recovery
              - session restore
            aliases:
              - restore previous chat history
              - chat history recovery
            canonical: true
            related: []
            supersedes: []
            last_verified: 2026-04-20
            confidence: high
            update_policy: merge
            when_to_read:
              - 排查线程丢失时
            """
        ),
        "按 thread id 反查历史会话记录, 恢复线程显示.",
    )


def seed_memory_skill_audit_note(root: Path) -> None:
    memory_root = root / ".codex" / "memory" / "runbooks"
    memory_root.mkdir(parents=True, exist_ok=True)
    write_note(
        memory_root / "memory-skill-audit.md",
        textwrap.dedent(
            """\
            ---
            doc_id: runbook-memory-skill-audit
            doc_type: runbook
            title: 记忆 skill 审核入口
            status: active
            scope: repo
            tags: [memory, skill, audit, benchmark, routing]
            triggers:
              - 审核当前记忆 skill
              - 审核记忆 skill 的复用率 质量 速度
              - 复核记忆 route 命中质量
            keywords:
              - memory skill audit
              - reuse rate
              - quality
              - latency
              - benchmark
              - 记忆复用率
              - 记忆质量
              - 记忆速度
            aliases:
              - 审核当前记忆 skill
              - 审核当前记忆 skill 的复用率 质量 速度
              - 记忆 skill 审计
            canonical: true
            related: []
            supersedes: []
            last_verified: 2026-04-24
            confidence: high
            update_policy: merge
            when_to_read:
              - 在审核当前记忆 skill 前
            """
        ),
        "先核对记忆复用率, 记忆质量, 记忆速度, route 命中, codex-memo sk, benchmark 与 spot check.",
    )


def seed_long_task_completion_boundary_note(root: Path) -> None:
    memory_root = root / ".codex" / "memory" / "runbooks"
    memory_root.mkdir(parents=True, exist_ok=True)
    write_note(
        memory_root / "long-task-completion-boundary-enforcement.md",
        textwrap.dedent(
            """\
            ---
            doc_id: runbook-long-task-completion-boundary-enforcement
            doc_type: runbook
            title: 长任务完成边界执行规则
            status: active
            scope: repo
            tags: [codex-long-task, execution, completion-boundary, closeout]
            triggers:
              - 用户列了多个目标, 能不能只完成一部分
              - 长任务完成边界 用户目标全集 部分完成 最小必要 closeout success
              - 什么时候允许 closeout success 长任务
            keywords:
              - long task completion boundary
              - user goal set
              - partial completion
              - closeout success
              - 最小必要
              - 部分完成
              - 用户目标全集
              - 完成边界
            aliases:
              - 长任务完成边界
              - 用户目标全集完成边界
              - 长任务能不能只完成一部分
            canonical: true
            related: []
            supersedes: []
            last_verified: 2026-04-24
            confidence: high
            update_policy: merge
            when_to_read:
              - 编制长任务 plan 或 task.json 前
              - 判断用户目标能否裁剪前
              - 判断是否允许 closeout success 前
            """
        ),
        "把用户显式列出的目标项视为完成边界. 未全部完成且未获确认排除剩余项前, 不得标记 completed 或 closeout success.",
    )


def seed_curated_skill_install_noise_note(root: Path) -> None:
    memory_root = root / ".codex" / "memory" / "runbooks"
    memory_root.mkdir(parents=True, exist_ok=True)
    write_note(
        memory_root / "curated-skill-install.md",
        textwrap.dedent(
            """\
            ---
            doc_id: runbook-curated-skill-install
            doc_type: runbook
            title: Codex app 安装 curated skill 失败
            status: active
            scope: repo
            tags: [codex, app, skill, install]
            triggers:
              - skill install fails
            keywords:
              - curated skill
              - install
              - vendor imports
            aliases:
              - failed skill install
            canonical: true
            related: []
            supersedes: []
            last_verified: 2026-04-24
            confidence: high
            update_policy: merge
            when_to_read:
              - 在排查 skill install 失败前
            """
        ),
        "处理 curated skill install fails 与 vendor imports drift.",
    )


def seed_restore_history_task_contract(root: Path) -> None:
    task_root = root / ".codex" / "tasks" / "2026-04-22-restore-history"
    task_root.mkdir(parents=True, exist_ok=True)
    (task_root / "prd.md").write_text(
        textwrap.dedent(
            """\
            # PRD: Restore Previous Chat History

            ## Task Goal
            restore previous chat history
            """
        ),
        encoding="utf-8",
    )
    (task_root / "context.md").write_text(
        textwrap.dedent(
            """\
            # Context: Restore Previous Chat History

            ## Reusable Assets
            - archived session lookup
            - session restore
            """
        ),
        encoding="utf-8",
    )


def seed_session_asset(
    root: Path,
    *,
    message: str,
    session_id: str = "rollout-2026-04-20T00-00-00-demo",
    archived: bool = False,
) -> None:
    if archived:
        session_dir = root / ".codex" / "archived_sessions"
    else:
        date_part = session_id.split("T", 1)[0].replace("rollout-", "")
        year, month, day = date_part.split("-")
        session_dir = root / ".codex" / "sessions" / year / month / day
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / f"{session_id}.jsonl"
    session_path.write_text(
        "\n".join(
            [
                json.dumps({"timestamp": "2026-04-20T00:00:00Z", "type": "session_meta", "payload": {"id": "demo"}}),
                json.dumps(
                    {
                        "timestamp": "2026-04-20T00:00:01Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": message}],
                        },
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


class CodexMemoTests(unittest.TestCase):
    def test_boot_bootstraps_project_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            home_root = Path(tmpdir) / "home"
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Runbook", note_body="home body")

            result = run_cli("b", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["repo_root"], str(repo_root.resolve()))
            self.assertTrue((repo_root / ".codex" / "memory" / "context.md").exists())
            self.assertTrue((repo_root / ".codex" / "scripts" / "memory_tool.py").exists())

    def test_bootstrap_project_bundle_syncs_semantic_runtime_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Runbook", note_body="repo body")

            payload = bootstrap_project_codex.bootstrap_project_codex(repo_root)

            copied = payload["copied_scripts"]
            expected = {
                ".codex/scripts/memory_benchmark.py",
                ".codex/scripts/lib/evolution_promote.py",
                ".codex/scripts/lib/semantic_index.py",
                ".codex/scripts/lib/llm_semantic_client.py",
            }
            self.assertTrue(expected.issubset(copied.keys()))
            for relative in expected:
                self.assertTrue((repo_root / relative).exists(), msg=relative)

    def test_bootstrap_project_bundle_runs_self_contained_codex_memo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            home_root = Path(tmpdir) / "home"
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Runbook", note_body="home body")

            bootstrap_project_codex.bootstrap_project_codex(repo_root)

            env = os.environ.copy()
            env["CODEX_MEMO_HOME_ROOT"] = str(home_root)
            result = subprocess.run(
                ["python3", str(repo_root / ".codex" / "scripts" / "codex_memo.py"), "d"],
                cwd=str(repo_root),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["repo_root"], str(repo_root.resolve()))

    def test_doctor_reports_repo_and_home_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Runbook", note_body="repo body")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Runbook", note_body="home body")

            result = run_cli("d", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["repo_root"], str(repo_root.resolve()))
            self.assertEqual(payload["home_root"], str(home_root.resolve()))
            self.assertEqual(payload["command_name"], "codex-memo")
            self.assertEqual(payload["command_path"], str(COMMAND_PATH))
            self.assertTrue(payload["project_memory_exists"])
            self.assertTrue(payload["home_memory_exists"])
            self.assertIn("x", payload["commands"])
            self.assertEqual(payload["aliases"]["x"], ["delete", "remove"])
            self.assertEqual(payload["aliases"]["a"], ["asset", "assets", "sk", "skills"])

    def test_long_aliases_are_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Runbook", note_body="repo body")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Runbook", note_body="home body")

            doctor_result = run_cli("doctor", cwd=repo_root, home_root=home_root)
            self.assertEqual(doctor_result.returncode, 0, msg=doctor_result.stderr)

            overview_result = run_cli("overview", cwd=repo_root, home_root=home_root)
            self.assertEqual(overview_result.returncode, 0, msg=overview_result.stderr)

            route_result = run_cli("route", "--task", "codex cli", cwd=repo_root, home_root=home_root)
            self.assertEqual(route_result.returncode, 0, msg=route_result.stderr)
            route_payload = json.loads(route_result.stdout)
            self.assertTrue(route_payload["merged_hits"])

    def test_normalize_command_covers_all_long_aliases(self) -> None:
        expected = {
            "doctor": "d",
            "overview": "ov",
            "boot": "b",
            "bootstrap": "b",
            "agent": "g",
            "route": "r",
            "inspect": "i",
            "flush": "f",
            "asset": "a",
            "assets": "a",
            "sk": "a",
            "skills": "a",
            "maintain": "m",
            "cap": "q",
            "capability": "q",
            "l4": "l4",
            "archive-session": "l4",
            "replay-session": "l4",
            "checkpoint": "k",
            "promote": "lp",
            "promotion": "lp",
            "candidate": "p",
            "propose": "p",
            "update": "u",
            "delete": "x",
            "remove": "x",
            "sync": "s",
            "sync-registry": "s",
            "check": "c",
            "hygiene": "c",
            "new": "n",
            "scaffold": "n",
            "verify": "v",
        }
        for raw, normalized in expected.items():
            self.assertEqual(codex_memo.normalize_command(raw), normalized)

    def test_merge_hits_orders_by_score_with_project_tie_breaker(self) -> None:
        merged = codex_memo.merge_hits(
            [
                {
                    "path": "memory/runbooks/project-weak.md",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "score": 1.0,
                },
                {
                    "path": "memory/runbooks/project-tie.md",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "score": 5.0,
                },
            ],
            [
                {
                    "path": "memory/runbooks/home-strong.md",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "score": 9.0,
                },
                {
                    "path": "memory/runbooks/home-tie.md",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "score": 5.0,
                },
            ],
            top_k=4,
        )

        self.assertEqual(merged[0]["path"], "memory/runbooks/home-strong.md")
        self.assertEqual(merged[1]["path"], "memory/runbooks/project-tie.md")
        self.assertEqual(merged[2]["path"], "memory/runbooks/home-tie.md")

    def test_precise_lookup_slash_detection_ignores_abbreviations(self) -> None:
        self.assertFalse(codex_memo.query_has_precise_lookup("A/B 测试 memory route quality"))
        self.assertFalse(codex_memo.query_has_precise_lookup("复核 yes/no 分支"))
        self.assertTrue(codex_memo.query_has_precise_lookup("memory/runbooks/thread-recovery"))
        self.assertTrue(codex_memo.query_has_precise_lookup(".codex/scripts/codex_memo.py"))

    def test_semantic_ambiguity_ratio_catches_close_runner_up(self) -> None:
        should_rerank, reason = codex_memo.should_apply_semantic_rerank(
            task="review route ranking quality",
            merged_hits=[
                {
                    "path": "memory/runbooks/primary.md",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "source": "project",
                    "score": 10.0,
                },
                {
                    "path": "memory/runbooks/runner-up.md",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "source": "project",
                    "score": 8.5,
                },
            ],
            semantic_candidates=[],
            execution_gate={"state": "hit", "selected_path": "memory/runbooks/primary.md"},
        )

        self.assertTrue(should_rerank)
        self.assertEqual(reason, "lexical_gap_ambiguous")

    def test_governance_query_detection_matches_mixed_governance_query(self) -> None:
        self.assertTrue(codex_memo.query_has_governance_intent("记忆治理入口 session routing aliases keywords"))
        self.assertTrue(codex_memo.query_has_governance_intent("memory governance hygiene routing aliases keywords"))
        self.assertFalse(codex_memo.query_has_governance_intent("收紧 session recall 策略并降低索引负担"))

    def test_governance_intent_forces_semantic_rerank_for_english_query(self) -> None:
        should_rerank, reason = codex_memo.should_apply_semantic_rerank(
            task="memory governance hygiene routing aliases keywords",
            merged_hits=[
                {
                    "path": "memory/runbooks/memory-hygiene-scan-cleanup-and-enrichment.md",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "source": "project",
                    "score": 7.0,
                },
                {
                    "path": "memory/runbooks/secondary.md",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "source": "project",
                    "score": 1.5,
                },
            ],
            semantic_candidates=[
                {
                    "path": "memory/runbooks/memory-hygiene-scan-cleanup-and-enrichment.md",
                    "score": 0.31,
                }
            ],
            execution_gate={
                "state": "hit",
                "selected_path": "memory/runbooks/memory-hygiene-scan-cleanup-and-enrichment.md",
            },
        )

        self.assertTrue(should_rerank)
        self.assertEqual(reason, "governance_intent_query")

    def test_apply_semantic_rerank_keeps_governance_runbook_over_session_strategy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            lexical_hits = [
                {
                    "path": "memory/runbooks/memory-hygiene-scan-cleanup-and-enrichment.md",
                    "ref": "project:memory/runbooks/memory-hygiene-scan-cleanup-and-enrichment.md",
                    "title": "记忆扫描清理与检索面补齐入口",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "source": "project",
                    "score": 3.0,
                    "reasons": ["keywords:hygiene (+0.21)"],
                },
                {
                    "path": "memory/runbooks/session-recall-window-and-archive-priority.md",
                    "ref": "project:memory/runbooks/session-recall-window-and-archive-priority.md",
                    "title": "Session recall 窗口与 archived 优先级收敛",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "source": "project",
                    "score": 2.8,
                    "reasons": ["keywords:session recall (+0.21)"],
                },
            ]
            semantic_candidates = [
                {
                    "path": "memory/runbooks/memory-hygiene-scan-cleanup-and-enrichment.md",
                    "title": "记忆扫描清理与检索面补齐入口",
                    "doc_type": "runbook",
                    "score": 0.58,
                    "semantic_reasons": ["problem_signals:governance,aliases,keywords"],
                    "intent": "记忆治理入口",
                    "action_summary": "记忆治理入口, aliases keywords routing, session cleanup",
                },
                {
                    "path": "memory/runbooks/session-recall-window-and-archive-priority.md",
                    "title": "Session recall 窗口与 archived 优先级收敛",
                    "doc_type": "runbook",
                    "score": 0.64,
                    "semantic_reasons": ["problem_signals:session,recall"],
                    "intent": "session recall strategy",
                    "action_summary": "session recall window archived priority",
                },
            ]
            fake_rerank = {
                "selected_path": "memory/runbooks/session-recall-window-and-archive-priority.md",
                "rerank_reasons": ["semantic_overlap:aliases,session", "prefer_canonical_runbook"],
                "gate_override_reason": "semantic rerank selected the strongest semantic runbook candidate",
            }

            with mock.patch.object(codex_memo.SemanticLLMClient, "local_rerank", return_value=fake_rerank):
                payload = codex_memo.apply_semantic_rerank(
                    repo_root=repo_root,
                    task="记忆治理入口 session routing aliases keywords",
                    lexical_hits=lexical_hits,
                    semantic_candidates=semantic_candidates,
                    execution_gate={
                        "state": "hit",
                        "selected_path": "memory/runbooks/memory-hygiene-scan-cleanup-and-enrichment.md",
                        "selected_kind": "memory",
                    },
                )

        self.assertEqual(payload["semantic_mode"], "local")
        self.assertEqual(
            payload["rerank_selected_path"],
            "memory/runbooks/memory-hygiene-scan-cleanup-and-enrichment.md",
        )
        self.assertEqual(
            payload["rerank_selected_ref"],
            "project:memory/runbooks/memory-hygiene-scan-cleanup-and-enrichment.md",
        )
        self.assertTrue(
            {
                "governance_guard:keep_execution_gate_runbook",
                "governance_guard:keep_lexical_governance_entry",
            }
            & set(payload["rerank_reasons"])
        )

    def test_execution_gate_keeps_fallback_hits_as_reference_only(self) -> None:
        gate = codex_memo.build_execution_gate(
            project_memory_hits=[],
            project_hits=[
                {
                    "path": "memory/runbooks/low-confidence.md",
                    "ref": "project:memory/runbooks/low-confidence.md",
                    "title": "Low Confidence",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "source": "project",
                }
            ],
            merged_hits=[
                {
                    "path": "memory/runbooks/low-confidence.md",
                    "ref": "project:memory/runbooks/low-confidence.md",
                    "title": "Low Confidence",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "source": "project",
                }
            ],
            project_fallback_context=True,
            fallback_context=True,
        )

        self.assertEqual(gate["state"], "reference_only")
        self.assertEqual(gate["selected_path"], "memory/runbooks/low-confidence.md")

    def test_score_note_for_query_applies_confidence_penalty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            seed_memory_root(
                repo_root,
                repo_type="repo-memory",
                summary="repo summary",
                note_title="Repo Route Flow",
                note_body="review route flow",
            )
            notes_root = repo_root / ".codex" / "memory" / "runbooks"
            write_note(
                notes_root / "high-confidence.md",
                textwrap.dedent(
                    """\
                    ---
                    doc_id: runbook-high-confidence
                    doc_type: runbook
                    title: Memory Route Confidence
                    status: active
                    scope: repo
                    tags: [memory, route]
                    triggers:
                      - memory route confidence
                    keywords:
                      - memory route confidence
                    canonical: true
                    related: []
                    supersedes: []
                    last_verified: 2026-04-24
                    confidence: high
                    update_policy: merge
                    when_to_read:
                      - before scoring route confidence
                    """
                ),
                "Use this runbook when memory route confidence needs review.",
            )
            write_note(
                notes_root / "medium-confidence.md",
                textwrap.dedent(
                    """\
                    ---
                    doc_id: runbook-medium-confidence
                    doc_type: runbook
                    title: Memory Route Confidence
                    status: active
                    scope: repo
                    tags: [memory, route]
                    triggers:
                      - memory route confidence
                    keywords:
                      - memory route confidence
                    canonical: true
                    related: []
                    supersedes: []
                    last_verified: 2026-04-24
                    confidence: medium
                    update_policy: merge
                    when_to_read:
                      - before scoring route confidence
                    """
                ),
                "Use this runbook when memory route confidence needs review.",
            )

            notes = {
                note.path.name: note
                for note in codex_memo.mt.scan_memory_notes(repo_root)
                if note.path.name in {"high-confidence.md", "medium-confidence.md"}
            }

        high = codex_memo.mt.score_note_for_query(notes["high-confidence.md"], "memory route confidence")
        medium = codex_memo.mt.score_note_for_query(notes["medium-confidence.md"], "memory route confidence")

        self.assertGreater(high["score"], medium["score"])
        self.assertIn("confidence:high (+0.00)", high["reasons"])
        self.assertIn("confidence:medium (-0.08)", medium["reasons"])

    def test_main_flush_updates_asset_index_after_scaffold(self) -> None:
        repo_root = Path("/tmp/repo")
        flush_payload = {"scaffold": {"created": True}, "hygiene": {"issue_count": 0}}
        asset_payload = {"output_path": "/tmp/repo/.codex/cache/asset-index.json"}
        with (
            mock.patch.object(codex_memo, "infer_repo_root", return_value=repo_root),
            mock.patch.object(codex_memo, "resolve_home_root", return_value=repo_root),
            mock.patch.object(codex_memo, "ensure_project_layer"),
            mock.patch.object(codex_memo.mt, "command_flush", return_value=flush_payload),
            mock.patch.object(codex_memo, "command_asset", return_value=asset_payload) as asset_mock,
            mock.patch.object(codex_memo, "emit_json") as emit_mock,
        ):
            result = codex_memo.main(["f"])

        self.assertEqual(result, 0)
        asset_mock.assert_called_once_with(repo_root)
        emit_mock.assert_called_once()
        emitted_payload = emit_mock.call_args.args[0]
        self.assertEqual(emitted_payload["asset_index"]["output_path"], asset_payload["output_path"])

    def test_main_flush_skips_asset_index_when_no_scaffold_created(self) -> None:
        repo_root = Path("/tmp/repo")
        flush_payload = {"scaffold": {"created": False}, "hygiene": {"issue_count": 0}}
        with (
            mock.patch.object(codex_memo, "infer_repo_root", return_value=repo_root),
            mock.patch.object(codex_memo, "resolve_home_root", return_value=repo_root),
            mock.patch.object(codex_memo, "ensure_project_layer"),
            mock.patch.object(codex_memo.mt, "command_flush", return_value=flush_payload),
            mock.patch.object(codex_memo, "command_asset") as asset_mock,
            mock.patch.object(codex_memo, "emit_json"),
        ):
            result = codex_memo.main(["f"])

        self.assertEqual(result, 0)
        asset_mock.assert_not_called()

    def test_main_checkpoint_syncs_registry_for_memory_coverage_updates(self) -> None:
        repo_root = Path("/tmp/repo")
        checkpoint_payload = {"checkpoint_path": ".codex/cache/memory-state.db", "closeout_gate": {"status": "pending"}}
        sync_payload = {"updated": ["memory/registry.md"]}
        with (
            mock.patch.object(codex_memo, "infer_repo_root", return_value=repo_root),
            mock.patch.object(codex_memo, "resolve_home_root", return_value=repo_root),
            mock.patch.object(codex_memo, "ensure_project_layer"),
            mock.patch.object(codex_memo, "command_checkpoint", return_value=checkpoint_payload),
            mock.patch.object(codex_memo, "command_sync", return_value=sync_payload) as sync_mock,
            mock.patch.object(codex_memo, "emit_json") as emit_mock,
        ):
            result = codex_memo.main(
                [
                    "k",
                    "--task",
                    "memory coverage sync",
                    "--coverage-mode",
                    "new_family",
                    "--runbook-paths",
                    "memory/runbooks/thread-recovery.md",
                ]
            )

        self.assertEqual(result, 0)
        sync_mock.assert_called_once_with(repo_root)
        emit_mock.assert_called_once()
        emitted_payload = emit_mock.call_args.args[0]
        self.assertEqual(emitted_payload["sync_registry"], sync_payload)

    def test_main_checkpoint_skips_sync_registry_without_memory_changes(self) -> None:
        repo_root = Path("/tmp/repo")
        checkpoint_payload = {"checkpoint_path": ".codex/cache/memory-state.db", "closeout_gate": {"status": "pending"}}
        with (
            mock.patch.object(codex_memo, "infer_repo_root", return_value=repo_root),
            mock.patch.object(codex_memo, "resolve_home_root", return_value=repo_root),
            mock.patch.object(codex_memo, "ensure_project_layer"),
            mock.patch.object(codex_memo, "command_checkpoint", return_value=checkpoint_payload),
            mock.patch.object(codex_memo, "command_sync") as sync_mock,
            mock.patch.object(codex_memo, "emit_json"),
        ):
            result = codex_memo.main(["k", "--task", "ordinary checkpoint"])

        self.assertEqual(result, 0)
        sync_mock.assert_not_called()

    def test_semantic_index_prefers_local_embedding_when_available(self) -> None:
        class FakeSemanticClient:
            def __init__(self, repo_root: Path) -> None:
                self.mode = "fake"

            def generate_index_entry(self, payload: dict[str, object]) -> dict[str, object]:
                return {
                    "model": "fake-semantic-client",
                    "prompt_version": 1,
                    "intent": str(payload.get("title", "")),
                    "problem_signals": ["thread recovery"],
                    "paraphrases": ["restore previous chat history"],
                    "when_to_use": ["排查线程丢失时"],
                    "when_not_to_use": ["generic lookup"],
                    "related_queries": ["找回之前聊天记录"],
                    "action_summary": str(payload.get("excerpt", "")),
                    "confidence": "fake",
                    "evidence_spans": ["title"],
                    "source_excerpt_refs": ["excerpt"],
                }

        class FakeEmbeddingClient:
            def __init__(self, model_name: str | None = None) -> None:
                self.available = True
                self.mode = "local_embedding"
                self.model_name = model_name or "test-local-embedding"

            def encode_texts(self, texts: list[str]) -> list[list[float]]:
                vectors: list[list[float]] = []
                for text in texts:
                    lowered = text.lower()
                    if "repo route flow" in lowered:
                        vectors.append([0.0, 1.0])
                    elif "thread-recovery" in lowered or "thread recovery" in lowered or "线程恢复" in text:
                        vectors.append([1.0, 0.0])
                    else:
                        vectors.append([0.0, 1.0])
                return vectors

            def score_candidates(self, query: str, candidate_vectors: list[list[float]]) -> list[float]:
                if "线程" in query or "thread" in query.lower():
                    return [vector[0] for vector in candidate_vectors]
                return [vector[1] for vector in candidate_vectors]

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            seed_memory_root(
                repo_root,
                repo_type="repo-memory",
                summary="repo summary",
                note_title="Repo Route Flow",
                note_body="review route flow",
            )
            seed_thread_recovery_note(repo_root)
            with (
                mock.patch.object(codex_memo.sidx, "SemanticLLMClient", FakeSemanticClient),
                mock.patch.object(codex_memo.sidx, "LocalEmbeddingClient", FakeEmbeddingClient),
            ):
                build_payload = codex_memo.sidx.build_semantic_index(repo_root, force=True)
                inspect_payload = codex_memo.sidx.inspect_semantic_candidates(repo_root, task="线程恢复", top_k=3)

        self.assertEqual(build_payload["semantic_index"]["mode"], "local_embedding")
        self.assertEqual(inspect_payload["semantic_index_mode"], "local_embedding")
        self.assertEqual(inspect_payload["candidates"][0]["path"], "memory/runbooks/thread-recovery.md")
        self.assertTrue(any(reason.startswith("embedding_cosine:") for reason in inspect_payload["candidates"][0]["semantic_reasons"]))

    def test_semantic_inspect_migrates_legacy_json_cache_into_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            cache_root = repo_root / ".codex" / "cache"
            cache_root.mkdir(parents=True, exist_ok=True)
            (cache_root / "semantic-index.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "entries": [
                            {
                                "path": "memory/runbooks/thread-recovery.md",
                                "doc_type": "runbook",
                                "asset_type": "memory",
                                "title": "线程恢复流程",
                                "intent": "线程恢复流程",
                                "problem_signals": ["线程恢复"],
                                "paraphrases": ["恢复线程"],
                                "when_to_use": ["排查线程丢失时"],
                                "related_queries": ["thread recovery"],
                                "action_summary": "恢复历史会话",
                                "source_hash": "legacy-hash",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )
            (cache_root / "semantic-index.meta.json").write_text(
                json.dumps({"mode": "fake", "embedding_model": ""}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            lib_dir = SCRIPT_PATH.parent / "lib"
            if str(lib_dir) not in sys.path:
                sys.path.insert(0, str(lib_dir))
            spec = importlib.util.spec_from_file_location("semantic_index_sqlite_test", lib_dir / "semantic_index.py")
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            semantic_index_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(semantic_index_module)
            payload = semantic_index_module.inspect_semantic_candidates(repo_root, task="线程恢复", top_k=3)

            self.assertEqual(payload["candidates"][0]["path"], "memory/runbooks/thread-recovery.md")
            self.assertTrue((cache_root / "memory-state.db").exists())

    def test_command_update_refreshes_frontmatter_and_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            seed_memory_root(
                repo_root,
                repo_type="repo-memory",
                summary="repo summary",
                note_title="Repo Route Flow",
                note_body="review route flow",
            )
            codex_memo.vs.upsert_sidecar(
                repo_root,
                task_id="memory-update-review",
                task_summary="verify update",
                deliverables=["memory/runbooks/core.md"],
                required_checks=["review"],
                evidence_paths=["memory/runbooks/core.md"],
            )
            args = argparse.Namespace(
                path="memory/runbooks/core.md",
                title="Repo Route Flow Updated",
                tags="memory;updated",
                triggers="route refresh",
                keywords="route;refresh",
                when_to_read="before refresh",
                aliases="route refresh flow",
                confidence="medium",
                status="active",
                canonical="true",
                body_append="追加一段更新说明.",
                task="",
                task_id="memory-update-review",
                evidence_paths="memory/runbooks/core.md",
            )
            with (
                mock.patch.object(codex_memo, "command_sync", return_value={"updated": ["memory/registry.md"]}),
                mock.patch.object(codex_memo, "command_asset", return_value={"output_path": "/tmp/repo/.codex/cache/asset-index.json"}),
            ):
                payload = codex_memo.command_update(args, repo_root)

            updated_path = repo_root / ".codex" / "memory" / "runbooks" / "core.md"
            frontmatter, body = codex_memo.mt.parse_frontmatter(updated_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["path"], ".codex/memory/runbooks/core.md")
        self.assertIn("keywords", payload["updated_fields"])
        self.assertEqual(frontmatter["title"], "Repo Route Flow Updated")
        self.assertEqual(frontmatter["keywords"], ["route", "refresh"])
        self.assertEqual(frontmatter["aliases"], ["route refresh flow"])
        self.assertEqual(frontmatter["confidence"], "medium")
        self.assertIn("追加一段更新说明.", body)
        self.assertEqual(payload["verification_gate"]["sources"], ["verifier_sidecar"])

    def test_command_delete_removes_note_and_semantic_entry(self) -> None:
        class FakeSemanticClient:
            def __init__(self, repo_root: Path) -> None:
                self.mode = "fake"

            def generate_index_entry(self, payload: dict[str, object]) -> dict[str, object]:
                return {
                    "model": "fake-semantic-client",
                    "prompt_version": 1,
                    "intent": str(payload.get("title", "")),
                    "problem_signals": ["route flow"],
                    "paraphrases": ["route flow"],
                    "when_to_use": ["before route work"],
                    "when_not_to_use": [],
                    "related_queries": ["route flow"],
                    "action_summary": str(payload.get("excerpt", "")),
                    "confidence": "fake",
                    "evidence_spans": ["title"],
                    "source_excerpt_refs": ["excerpt"],
                }

        class FakeEmbeddingClient:
            def __init__(self, model_name: str | None = None) -> None:
                self.available = False
                self.mode = "unavailable"
                self.model_name = model_name or ""

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            seed_memory_root(
                repo_root,
                repo_type="repo-memory",
                summary="repo summary",
                note_title="Repo Route Flow",
                note_body="review route flow",
            )
            with (
                mock.patch.object(codex_memo.sidx, "SemanticLLMClient", FakeSemanticClient),
                mock.patch.object(codex_memo.sidx, "LocalEmbeddingClient", FakeEmbeddingClient),
            ):
                codex_memo.sidx.build_semantic_index(repo_root, force=True)
            store_path = repo_root / ".codex" / "cache" / "memory-state.db"
            before_rows = read_sqlite_json_rows(store_path, "semantic_entries", "path")
            self.assertIn("memory/runbooks/core.md", before_rows)

            args = argparse.Namespace(path="memory/runbooks/core.md")
            with (
                mock.patch.object(codex_memo, "command_sync", return_value={"updated": ["memory/registry.md"]}),
                mock.patch.object(codex_memo, "command_asset", return_value={"output_path": "/tmp/repo/.codex/cache/asset-index.json"}),
            ):
                payload = codex_memo.command_delete(args, repo_root)

            deleted_path = repo_root / ".codex" / "memory" / "runbooks" / "core.md"
            after_rows = read_sqlite_json_rows(store_path, "semantic_entries", "path")

        self.assertFalse(deleted_path.exists())
        self.assertTrue(payload["deleted"])
        self.assertEqual(payload["path"], ".codex/memory/runbooks/core.md")
        self.assertEqual(payload["doc_id"], "runbook-core")
        self.assertNotIn("memory/runbooks/core.md", after_rows)

    def test_command_delete_rejects_non_entry_memory_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            seed_memory_root(
                repo_root,
                repo_type="repo-memory",
                summary="repo summary",
                note_title="Repo Route Flow",
                note_body="review route flow",
            )
            args = argparse.Namespace(path="context.md")

            with self.assertRaises(ValueError):
                codex_memo.command_delete(args, repo_root)

    def test_route_can_include_extra_root_reference_hits(self) -> None:
        repo_root = Path("/tmp/repo")
        home_root = repo_root
        extra_root = Path("/tmp/extra-project")
        project_hit = {
            "path": "memory/runbooks/project.md",
            "kind": "memory",
            "title": "Project Runbook",
            "doc_type": "runbook",
            "score": 3.0,
            "reasons": ["project"],
        }
        extra_hit = {
            "path": "memory/runbooks/extra.md",
            "kind": "memory",
            "title": "Extra Runbook",
            "doc_type": "runbook",
            "score": 2.4,
            "reasons": ["extra"],
        }
        route_event = {
            "route_event_id": "evt_demo",
            "surfaced_hits_hash": "hash_demo",
        }

        def fake_route(target_root: Path, *, task: str, top_k: int, record_event: bool) -> dict[str, object]:
            if target_root == repo_root:
                return {
                    "hits": [project_hit],
                    "memory_hits": [project_hit],
                    "asset_hits": [],
                    "fallback_context": False,
                    **route_event,
                }
            if target_root == extra_root:
                return {
                    "hits": [extra_hit],
                    "memory_hits": [extra_hit],
                    "asset_hits": [],
                    "fallback_context": False,
                }
            raise AssertionError(f"unexpected root: {target_root}")

        with (
            mock.patch.object(codex_memo.mt, "command_route", side_effect=fake_route),
            mock.patch.object(codex_memo.sidx, "inspect_semantic_candidates", return_value={"candidates": [], "semantic_index_mode": "missing"}),
            mock.patch.object(
                codex_memo,
                "apply_semantic_rerank",
                return_value={
                    "semantic_mode": "skipped",
                    "semantic_cache_hit": False,
                    "semantic_model_used": "",
                    "semantic_trigger_reason": "high_confidence_runbook_hit",
                    "semantic_reasons": {},
                    "lexical_reasons": {},
                    "rerank_reasons": [],
                    "gate_override_reason": "",
                    "rerank_candidates": [],
                    "rerank_skipped_reason": "high_confidence_runbook_hit",
                    "semantic_index_rebuild": {},
                },
            ),
        ):
            payload = codex_memo.command_route(repo_root, home_root, task="route extra root", top_k=3, extra_roots=[extra_root], record_event=False)

        self.assertEqual(payload["execution_gate"]["selected_path"], "memory/runbooks/project.md")
        self.assertTrue(any(hit["source"] == "extra:extra-project" for hit in payload["extra_hits"]))
        self.assertTrue(any(hit["path"] == "memory/runbooks/extra.md" for hit in payload["merged_hits"]))

    def test_checkpoint_records_corrections(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_thread_recovery_note(repo_root)

            route_result = run_cli("r", "--task", "找回之前聊天记录", cwd=repo_root, home_root=home_root)
            self.assertEqual(route_result.returncode, 0, msg=route_result.stderr)
            route_payload = json.loads(route_result.stdout)

            checkpoint_result = run_cli(
                "k",
                "--task",
                "thread recovery correction",
                "--route-query",
                "找回之前聊天记录",
                "--route-event-id",
                route_payload["route_event_id"],
                "--surfaced-hits-hash",
                route_payload["surfaced_hits_hash"],
                "--selected-hit",
                "memory/runbooks/thread-recovery.md",
                "--correction",
                "confidence:medium->high",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(checkpoint_result.returncode, 0, msg=checkpoint_result.stderr)
            checkpoint_payload = json.loads(checkpoint_result.stdout)

        corrections = checkpoint_payload["retrieval_traces"][0]["corrections"]
        self.assertEqual(corrections[0]["field"], "confidence")
        self.assertEqual(corrections[0]["old_value"], "medium")
        self.assertEqual(corrections[0]["new_value"], "high")

    def test_query_variant_limit_caps_extra_route_calls(self) -> None:
        variants = [f"variant {index}" for index in range(6)]
        synthetic_payload = {
            "merged_hits": [],
            "execution_gate": {"state": "miss", "selected_path": ""},
        }
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            mock.patch.object(codex_memo, "build_query_variants", return_value=variants),
            mock.patch.object(codex_memo.mt, "get_route_context", return_value={"notes": [], "asset_payload": {}, "assets": []}),
            mock.patch.object(codex_memo.mt, "route_with_context", return_value=synthetic_payload) as route_with_context,
        ):
            repo_root = Path(tmpdir) / "repo"
            home_root = Path(tmpdir) / "home"
            repo_root.mkdir()
            home_root.mkdir()

            payload = codex_memo.build_hybrid_recall(
                repo_root=repo_root,
                home_root=home_root,
                task="speed route variants",
                top_k=3,
                checkpoint={"exists": False, "key_facts": [], "current_invariant": [], "task_assets": [], "reused_assets": [], "retrieval_traces": []},
                base_route_payload=synthetic_payload,
            )

        self.assertLessEqual(len(payload["query_variants"]), 4)
        self.assertLessEqual(len(route_with_context.call_args_list), 3)

    def test_agent_command_returns_route_and_working_memory_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="review route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_thread_recovery_note(repo_root)

            initial = run_cli("g", "--task", "读取线程记忆", cwd=repo_root, home_root=home_root)

            self.assertEqual(initial.returncode, 0, msg=initial.stderr)
            initial_payload = json.loads(initial.stdout)
            self.assertEqual(initial_payload["agent_context_version"], 1)
            self.assertEqual(initial_payload["route"]["execution_gate"]["state"], "hit")
            self.assertIn("hybrid_recall", initial_payload)
            self.assertEqual(initial_payload["hybrid_recall"]["query_variants"][0], "读取线程记忆")
            self.assertTrue(initial_payload["hybrid_recall"]["recall_candidates"])
            self.assertNotIn("candidates", initial_payload["hybrid_recall"])
            self.assertIn("### [HYBRID RECALL]", initial_payload["hybrid_recall"]["prompt_block"])
            self.assertEqual(initial_payload["working_memory"]["exists"], False)
            self.assertIn("### [WORKING MEMORY]", initial_payload["working_memory"]["prompt_block"])
            self.assertIn("暂无", initial_payload["working_memory"]["prompt_block"])
            self.assertTrue(initial_payload["memory_context"]["project_memory"])

            checkpoint = run_cli(
                "k",
                "--task",
                "读取线程记忆",
                "--key-facts",
                "thread id 可用于恢复会话",
                "--current-invariant",
                "优先沿用 thread recovery runbook",
                "--verified-steps",
                "route hit thread recovery runbook",
                "--task-assets",
                "memory/runbooks/thread-recovery.md",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(checkpoint.returncode, 0, msg=checkpoint.stderr)

            hydrated = run_cli("agent", "--task", "读取线程记忆", cwd=repo_root, home_root=home_root)

            self.assertEqual(hydrated.returncode, 0, msg=hydrated.stderr)
            hydrated_payload = json.loads(hydrated.stdout)
            self.assertEqual(hydrated_payload["working_memory"]["exists"], True)
            self.assertGreaterEqual(len(hydrated_payload["hybrid_recall"]["query_variants"]), 2)
            self.assertIn("thread recovery", " ".join(hydrated_payload["hybrid_recall"]["query_variants"]))
            self.assertTrue(hydrated_payload["hybrid_recall"]["recommended_path"])
            self.assertIn("thread id 可用于恢复会话", hydrated_payload["working_memory"]["prompt_block"])
            self.assertIn("优先沿用 thread recovery runbook", hydrated_payload["working_memory"]["prompt_block"])
            self.assertIn("route hit thread recovery runbook", hydrated_payload["working_memory"]["prompt_block"])
            self.assertIn("### [PROJECT MEMORY RECALL]", hydrated_payload["agent_prompt"])
            self.assertIn("### [EXECUTION GATE]", hydrated_payload["agent_prompt"])
            self.assertIn("### [HYBRID RECALL]", hydrated_payload["agent_prompt"])
            self.assertIn("### [WORKING MEMORY]", hydrated_payload["agent_prompt"])

    def test_agent_query_variants_expand_mixed_language_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="review route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")

            payload = codex_memo.build_hybrid_recall(
                repo_root=repo_root,
                home_root=home_root,
                task="找回之前聊天记录",
                top_k=3,
                checkpoint={"exists": False, "key_facts": [], "current_invariant": [], "task_assets": [], "reused_assets": [], "retrieval_traces": []},
                base_route_payload={
                    "merged_hits": [],
                    "execution_gate": {"state": "miss", "selected_path": ""},
                },
            )

            joined = " | ".join(payload["query_variants"]).lower()
            self.assertIn("chat history", joined)
            self.assertTrue(
                any("recover" in variant.lower() or "restore" in variant.lower() for variant in payload["query_variants"]),
                msg=payload["query_variants"],
            )

    def test_agent_hybrid_recall_disables_route_event_recording_for_synthetic_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="review route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")

            synthetic_payload = {
                "merged_hits": [],
                "execution_gate": {"state": "miss", "selected_path": ""},
            }
            with (
                mock.patch.object(codex_memo, "build_query_variants", return_value=["读取线程记忆", "restore previous chat history", "thread recovery flow"]),
                mock.patch.object(codex_memo.mt, "get_route_context", return_value={"notes": [], "asset_payload": {}, "assets": []}),
                mock.patch.object(codex_memo.mt, "route_with_context", return_value=synthetic_payload) as route_with_context,
            ):
                codex_memo.build_hybrid_recall(
                    repo_root=repo_root,
                    home_root=home_root,
                    task="读取线程记忆",
                    top_k=3,
                    checkpoint={"exists": False, "key_facts": [], "current_invariant": [], "task_assets": [], "reused_assets": [], "retrieval_traces": []},
                    base_route_payload=synthetic_payload,
                )

        self.assertEqual(len(route_with_context.call_args_list), 2)
        for call in route_with_context.call_args_list:
            self.assertEqual(call.kwargs["record_event"], False)

    def test_learning_query_terms_follow_route_extractor(self) -> None:
        terms = codex_memo.rl.query_terms("读取线程记忆")
        self.assertIn("线程", terms)
        self.assertIn("thread", terms)

    def test_agent_hybrid_recall_uses_history_for_related_mixed_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_thread_recovery_note(repo_root)
            seed_session_asset(repo_root, message="restore previous chat history before digging into archived sessions")

            first_route = run_cli("r", "--task", "找回之前聊天记录", cwd=repo_root, home_root=home_root)
            self.assertEqual(first_route.returncode, 0, msg=first_route.stderr)
            first_payload = json.loads(first_route.stdout)

            adopted = run_cli(
                "k",
                "--task",
                "thread recovery history bridge",
                "--route-query",
                "找回之前聊天记录",
                "--route-event-id",
                first_payload["route_event_id"],
                "--surfaced-hits-hash",
                first_payload["surfaced_hits_hash"],
                "--selected-hit",
                "memory/runbooks/thread-recovery.md",
                "--adopted-hit",
                "memory/runbooks/thread-recovery.md",
                "--observed-actions",
                "沿用 thread recovery runbook 处理聊天记录恢复",
                "--evidence-paths",
                "memory/runbooks/thread-recovery.md",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(adopted.returncode, 0, msg=adopted.stderr)

            mixed_query = run_cli("g", "--task", "restore previous chat history", cwd=repo_root, home_root=home_root)
            self.assertEqual(mixed_query.returncode, 0, msg=mixed_query.stderr)
            mixed_payload = json.loads(mixed_query.stdout)

            self.assertIn(mixed_payload["route"]["execution_gate"]["state"], {"hit", "reference_only"})
            self.assertEqual(mixed_payload["hybrid_recall"]["recommended_path"], "memory/runbooks/thread-recovery.md")
            self.assertTrue(
                any("找回之前聊天记录" == variant for variant in mixed_payload["hybrid_recall"]["query_variants"]),
                msg=mixed_payload["hybrid_recall"]["query_variants"],
            )

    def test_agent_hybrid_recall_history_reason_reuses_learning_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_thread_recovery_note(repo_root)

            codex_memo.rl.record_success(
                repo_root,
                query="找回之前聊天记录",
                target_paths=["memory/runbooks/thread-recovery.md"],
                source="adoption",
            )
            shared_history = codex_memo.rl.related_matches(repo_root, query="restore previous chat history", limit=3)
            self.assertTrue(shared_history)

            mixed_query = run_cli("g", "--task", "restore previous chat history", cwd=repo_root, home_root=home_root)
            self.assertEqual(mixed_query.returncode, 0, msg=mixed_query.stderr)
            mixed_payload = json.loads(mixed_query.stdout)
            recall_candidates = mixed_payload["hybrid_recall"]["recall_candidates"]
            thread_recovery = next(item for item in recall_candidates if item["path"] == "memory/runbooks/thread-recovery.md")

            self.assertTrue(
                any(str(reason).startswith(shared_history[0]["reason"]) for reason in thread_recovery["reasons"]),
                msg=thread_recovery["reasons"],
            )

    def test_agent_hybrid_recall_keeps_strongest_history_reason_per_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_thread_recovery_note(repo_root)

            codex_memo.rl.record_success(
                repo_root,
                query="找回之前聊天记录",
                target_paths=["memory/runbooks/thread-recovery.md"],
                source="adoption",
            )
            codex_memo.rl.record_success(
                repo_root,
                query="聊天恢复",
                target_paths=["memory/runbooks/thread-recovery.md"],
                source="adoption",
            )

            history_matches = codex_memo.related_history_matches(repo_root, "restore previous chat history")
            strongest = max(
                [item for item in history_matches if item["target_path"] == "memory/runbooks/thread-recovery.md"],
                key=lambda item: float(item["boost"]),
            )
            weakest = min(
                [item for item in history_matches if item["target_path"] == "memory/runbooks/thread-recovery.md"],
                key=lambda item: float(item["boost"]),
            )

            mixed_query = run_cli("g", "--task", "restore previous chat history", cwd=repo_root, home_root=home_root)
            self.assertEqual(mixed_query.returncode, 0, msg=mixed_query.stderr)
            mixed_payload = json.loads(mixed_query.stdout)
            thread_recovery = next(
                item
                for item in mixed_payload["hybrid_recall"]["recall_candidates"]
                if item["path"] == "memory/runbooks/thread-recovery.md"
            )

            self.assertTrue(
                any(str(reason).startswith(strongest["reason"]) for reason in thread_recovery["reasons"]),
                msg=thread_recovery["reasons"],
            )
            self.assertNotIn(weakest["reason"], thread_recovery["reasons"])

    def test_evolution_promote_emits_retrieval_hints_and_agent_uses_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_thread_recovery_note(repo_root)

            capsules = [
                {
                    "id": "cap_session_restore_gene_route",
                    "source_gene_id": "gene_route",
                    "signal_signature": "session_restore|thread_recovery",
                    "rule": "Prefer thread recovery workflow for session restore issues.",
                    "promotion_evidence": {"success_count": 4, "failure_count": 0, "distinct_sessions": 2},
                    "status": "active",
                    "created_at": "2026-04-20T00:00:00+00:00",
                    "last_verified": "2026-04-21",
                }
            ]
            suggestions = evolution_promote.suggest_memory_writeback(capsules)
            self.assertTrue(suggestions["retrieval_hints"])
            self.assertIn("session restore", suggestions["retrieval_hints"][0]["query_variants"])

            capsules_path = repo_root / ".codex" / "evolution" / "capsules.jsonl"
            capsules_path.parent.mkdir(parents=True, exist_ok=True)
            capsules_path.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in capsules) + "\n",
                encoding="utf-8",
            )

            payload = codex_memo.build_hybrid_recall(
                repo_root=repo_root,
                home_root=home_root,
                task="恢复会话",
                top_k=3,
                checkpoint={"exists": False, "key_facts": [], "current_invariant": [], "task_assets": [], "reused_assets": [], "retrieval_traces": []},
                base_route_payload={
                    "merged_hits": [],
                    "execution_gate": {"state": "miss", "selected_path": ""},
                },
            )

            self.assertIn("session restore", " | ".join(payload["query_variants"]).lower())

    def test_shadowed_hint_filter_skips_weak_single_term_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_thread_recovery_note(repo_root)

            capsules = [
                {
                    "id": "cap_windows_shell_gene_route",
                    "source_gene_id": "gene_route",
                    "signal_signature": "cmd|powershell|utf8|windows_shell|wsl",
                    "rule": "Prefer windows shell workflow.",
                    "promotion_evidence": {"success_count": 1, "failure_count": 0, "distinct_sessions": 1},
                    "status": "shadowed",
                    "created_at": "2026-04-20T00:00:00+00:00",
                    "last_verified": "2026-04-21",
                },
                {
                    "id": "cap_noise_gene_route",
                    "source_gene_id": "gene_route",
                    "signal_signature": "agents_updated|symlinks_removed|wsl_local_assets",
                    "rule": "Prefer asset cleanup workflow.",
                    "promotion_evidence": {"success_count": 1, "failure_count": 0, "distinct_sessions": 1},
                    "status": "shadowed",
                    "created_at": "2026-04-20T00:00:00+00:00",
                    "last_verified": "2026-04-21",
                },
            ]
            capsules_path = repo_root / ".codex" / "evolution" / "capsules.jsonl"
            capsules_path.parent.mkdir(parents=True, exist_ok=True)
            capsules_path.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in capsules) + "\n",
                encoding="utf-8",
            )

            payload = codex_memo.build_hybrid_recall(
                repo_root=repo_root,
                home_root=home_root,
                task="windows shell wsl",
                top_k=3,
                checkpoint={"exists": False, "key_facts": [], "current_invariant": [], "task_assets": [], "reused_assets": [], "retrieval_traces": []},
                base_route_payload={
                    "merged_hits": [],
                    "execution_gate": {"state": "miss", "selected_path": ""},
                },
            )

            joined = " | ".join(payload["query_variants"]).lower()
            self.assertIn("windows shell", joined)
            self.assertNotIn("agents updated", joined)
            self.assertNotIn("symlinks removed", joined)

    def test_evolution_review_promotes_single_verified_success_to_shadowed(self) -> None:
        result = evolution_promote.review_promotions(
            events=[
                {
                    "id": "evt_demo_shadowed",
                    "task_summary": "thread recovery recall",
                    "task_fingerprint": "sha256:demo-shadowed",
                    "signals": ["thread_recovery", "memory_update"],
                    "status": "success",
                    "score": 0.92,
                    "created_at": "2026-04-21T00:00:00+00:00",
                    "evidence": {"tests_passed": True, "validation_mode": "shell"},
                    "artifacts": {},
                }
            ],
            promotion_state={"version": 1, "clusters": {}},
            existing_capsules=[],
        )

        self.assertEqual(result["capsules"][0]["status"], "shadowed")

    def test_evolution_shadowed_capsule_emits_retrieval_hints(self) -> None:
        payload = evolution_promote.suggest_memory_writeback(
            [
                {
                    "id": "cap_thread_recovery_gene_route",
                    "source_gene_id": "gene_route",
                    "signal_signature": "thread_recovery|memory_update",
                    "rule": "Prefer thread recovery workflow.",
                    "promotion_evidence": {"success_count": 1, "failure_count": 0, "distinct_sessions": 1},
                    "status": "shadowed",
                    "created_at": "2026-04-20T00:00:00+00:00",
                    "last_verified": "2026-04-21",
                }
            ]
        )

        self.assertEqual(payload["suggestions"], [])
        self.assertTrue(payload["retrieval_hints"])
        self.assertEqual(payload["retrieval_hints"][0]["retrieval_stage"], "shadowed")

    def test_overview_returns_project_and_home_bundles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Runbook", note_body="repo body")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Runbook", note_body="home body")

            result = run_cli("ov", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["project"]["repo_type"], "repo-memory")
            self.assertEqual(payload["home"]["repo_type"], "home-memory")

    def test_route_returns_project_home_and_merged_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Codex CLI Flow", note_body="repo codex cli route")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Codex CLI Flow", note_body="home codex cli route")
            seed_assets(repo_root)
            codex_memo.mt.bai.write_asset_index(repo_root)

            result = run_cli("r", "--task", "codex cli", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["project_hits"])
            self.assertTrue(payload["project_memory_hits"])
            self.assertTrue(payload["project_asset_hits"])
            self.assertTrue(payload["home_hits"])
            self.assertGreaterEqual(len(payload["merged_hits"]), 2)
            self.assertEqual(payload["merged_hits"][0]["source"], "project")
            self.assertIn(payload["merged_hits"][1]["source"], {"project", "home"})
            self.assertEqual(payload["route_contract_version"], 4)
            self.assertTrue(payload["route_event_id"])
            self.assertTrue(payload["surfaced_hits_hash"])

    def test_route_returns_asset_hits_for_code_oriented_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="review route flow before codex memo changes")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_assets(repo_root)
            codex_memo.mt.bai.write_asset_index(repo_root)

            result = run_cli("r", "--task", "审查 codex_memo.py route", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["project_asset_hits"])
            self.assertEqual(payload["project_asset_hits"][0]["kind"], "asset")
            self.assertEqual(payload["project_asset_hits"][0]["asset_type"], "script")
            self.assertEqual(payload["project_asset_hits"][0]["path"], ".codex/scripts/codex_memo.py")
            self.assertEqual(payload["execution_gate"]["state"], "reference_only")

    def test_route_handles_chinese_query_with_asset_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="review checkpoint before route changes")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_assets(repo_root)
            codex_memo.mt.bai.write_asset_index(repo_root)

            result = run_cli("r", "--task", "状态查询 checkpoint", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["project_asset_hits"])
            self.assertEqual(payload["project_asset_hits"][0]["asset_type"], "skill")
            self.assertEqual(payload["project_asset_hits"][0]["path"], ".codex/skills/route-helper/SKILL.md")
            self.assertNotEqual(payload["execution_gate"]["state"], "hit")

    def test_capability_search_returns_local_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="review route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_assets(repo_root)
            executables_root = repo_root / ".codex" / "memory" / "executables"
            executables_root.mkdir(parents=True, exist_ok=True)
            (executables_root / "play-topic.py").write_text(
                textwrap.dedent(
                    """\
                    # ---
                    # title: Play First Topic
                    # keywords:
                    #   - first topic
                    # triggers:
                    #   - play topic
                    # aliases:
                    #   - topic player
                    # summary: play the first topic capability
                    # ---
                    def main():
                        return "ok"
                    """
                ),
                encoding="utf-8",
            )
            codex_memo.command_asset(repo_root)

            skill_result = run_cli("q", "--task", "route helper checkpoint codex_memo.py", "--top-k", "10", cwd=repo_root, home_root=home_root)
            self.assertEqual(skill_result.returncode, 0, msg=skill_result.stderr)
            skill_payload = json.loads(skill_result.stdout)
            skill_types = {item["capability_type"] for item in skill_payload["capability_hits"]}
            self.assertIn("skill", skill_types)
            self.assertIn("script", skill_types)

            insight_result = run_cli("q", "--task", "Repo Route Flow", cwd=repo_root, home_root=home_root)
            self.assertEqual(insight_result.returncode, 0, msg=insight_result.stderr)
            insight_payload = json.loads(insight_result.stdout)
            insight_types = {item["capability_type"] for item in insight_payload["capability_hits"]}
            self.assertIn("runbook", insight_types)
            self.assertIn("insight", insight_types)

            executable_result = run_cli("q", "--task", "first topic player", cwd=repo_root, home_root=home_root)
            self.assertEqual(executable_result.returncode, 0, msg=executable_result.stderr)
            executable_payload = json.loads(executable_result.stdout)
            self.assertEqual(executable_payload["capability_hits"][0]["capability_type"], "executable")

    def test_l4_closeout_archive_and_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="review route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            session_id = "rollout-2026-04-20T00-00-00-demo"
            seed_session_asset(repo_root, message="restore previous chat history before digging into archived sessions", session_id=session_id)

            archive_result = run_cli("l4", "--closeout", "--task", "closeout archive", cwd=repo_root, home_root=home_root)
            self.assertEqual(archive_result.returncode, 0, msg=archive_result.stderr)
            archive_payload = json.loads(archive_result.stdout)
            self.assertEqual(archive_payload["mode"], "archive")
            self.assertTrue(archive_payload["archived"])
            self.assertIn(".codex/archived_sessions/", archive_payload["archived_path"])

            replay_result = run_cli("l4", "--session-id", session_id, cwd=repo_root, home_root=home_root)
            self.assertEqual(replay_result.returncode, 0, msg=replay_result.stderr)
            replay_payload = json.loads(replay_result.stdout)
            self.assertEqual(replay_payload["mode"], "replay")
            self.assertEqual(replay_payload["session_id"], session_id)
            self.assertTrue(replay_payload["archived"])
            self.assertTrue(replay_payload["snippets"])

            query_result = run_cli("l4", "--query", "restore previous chat history", cwd=repo_root, home_root=home_root)
            self.assertEqual(query_result.returncode, 0, msg=query_result.stderr)
            query_payload = json.loads(query_result.stdout)
            self.assertTrue(query_payload["matches"])
            self.assertEqual(query_payload["matches"][0]["session_id"], session_id)

    def test_route_matches_thread_recovery_note_for_cjk_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="review route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_thread_recovery_note(repo_root)
            seed_session_asset(repo_root, message="读取线程记忆时, 先翻 session 线索, 但最终还是要按 thread recovery runbook 执行")
            codex_memo.mt.bai.write_asset_index(repo_root)

            result = run_cli("r", "--task", "读取线程记忆", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["project_memory_hits"][0]["path"], "memory/runbooks/thread-recovery.md")
            self.assertEqual(payload["project_asset_hits"][0]["asset_type"], "session")
            self.assertFalse(payload["fallback_context"])
            self.assertEqual(payload["execution_gate"]["state"], "hit")
            self.assertEqual(payload["execution_gate"]["selected_ref"], "project:memory/runbooks/thread-recovery.md")
            self.assertEqual(payload["execution_gate"]["selected_path"], "memory/runbooks/thread-recovery.md")
            self.assertIn("已命中可执行记忆", payload["execution_gate"]["prompt"])
            self.assertIn("adoption_evidence", payload["execution_gate"]["required_closeout"])

    def test_route_prefers_memory_skill_audit_runbook_for_audit_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="review route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_memory_skill_audit_note(repo_root)
            seed_curated_skill_install_noise_note(repo_root)

            result = run_cli("r", "--task", "审核当前记忆 skill 的复用率 质量 速度", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["project_memory_hits"][0]["path"], "memory/runbooks/memory-skill-audit.md")
            self.assertEqual(payload["execution_gate"]["state"], "hit")
            self.assertEqual(payload["execution_gate"]["selected_path"], "memory/runbooks/memory-skill-audit.md")

    def test_route_prefers_long_task_completion_boundary_runbook_for_partial_completion_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="review route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_long_task_completion_boundary_note(repo_root)
            seed_thread_recovery_note(repo_root)

            result = run_cli("r", "--task", "用户列了多个目标 能不能只完成一部分", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["project_memory_hits"][0]["path"], "memory/runbooks/long-task-completion-boundary-enforcement.md")
            self.assertEqual(payload["execution_gate"]["state"], "hit")
            self.assertEqual(payload["execution_gate"]["selected_path"], "memory/runbooks/long-task-completion-boundary-enforcement.md")

    def test_route_prefers_long_task_completion_boundary_runbook_for_closeout_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="review route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_long_task_completion_boundary_note(repo_root)
            seed_curated_skill_install_noise_note(repo_root)

            result = run_cli("r", "--task", "什么时候允许 closeout success 长任务", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["project_memory_hits"][0]["path"], "memory/runbooks/long-task-completion-boundary-enforcement.md")
            self.assertEqual(payload["execution_gate"]["state"], "hit")
            self.assertEqual(payload["execution_gate"]["selected_path"], "memory/runbooks/long-task-completion-boundary-enforcement.md")

    def test_route_top_k_one_keeps_runbook_hit_when_session_is_runner_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="review route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_thread_recovery_note(repo_root)
            seed_session_asset(repo_root, message="读取线程记忆时, 先翻 session 线索, 但最终还是要按 thread recovery runbook 执行")

            result = run_cli("r", "--task", "读取线程记忆", "--top-k", "1", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["fallback_context"])
            self.assertEqual(payload["execution_gate"]["state"], "hit")
            self.assertEqual(payload["execution_gate"]["selected_path"], "memory/runbooks/thread-recovery.md")

    def test_route_returns_mandatory_prompt_when_no_executable_memory_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="review route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")

            result = run_cli("r", "--task", "quantum flux capacitor mismatch", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["fallback_context"])
            self.assertEqual(payload["execution_gate"]["state"], "miss")

    def test_route_rejects_non_positive_top_k(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")

            result = run_cli("r", "--task", "codex cli", "--top-k", "0", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 2)
            self.assertIn("must be > 0", result.stderr)

    def test_route_can_recall_task_prd_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="review route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_assets(repo_root)
            seed_task_docs(repo_root)
            codex_memo.mt.bai.write_asset_index(repo_root)

            result = run_cli(
                "r",
                "--task",
                "审查 memory-system-v2 prd retrieval checkpoint candidate",
                cwd=repo_root,
                home_root=home_root,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            task_paths = {hit["path"] for hit in payload["project_asset_hits"]}
            self.assertIn(".codex/tasks/2026-04-19-memory-system-v2/prd.md", task_paths)

    def test_route_can_recall_task_summary_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="review route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_assets(repo_root)
            seed_task_docs(repo_root)
            codex_memo.mt.bai.write_asset_index(repo_root)

            result = run_cli(
                "r",
                "--task",
                "审查 memory-system-v2 summary closeout evidence",
                cwd=repo_root,
                home_root=home_root,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            task_paths = {hit["path"] for hit in payload["project_asset_hits"]}
            self.assertIn(".codex/tasks/2026-04-19-memory-system-v2/summary.md", task_paths)

    def test_route_can_recall_session_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="review route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_session_asset(repo_root, message="最近关于记忆系统复用率的讨论, 我们这个检索是不是太垃圾了")
            codex_memo.mt.bai.write_asset_index(repo_root)

            result = run_cli("r", "--task", "最近关于记忆系统复用率的讨论", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["project_asset_hits"])
            self.assertEqual(payload["project_asset_hits"][0]["asset_type"], "session")
            self.assertIn(".codex/sessions/2026/04/20/rollout-2026-04-20T00-00-00-demo.jsonl", payload["project_asset_hits"][0]["path"])

    def test_asset_index_caps_session_recall_and_prioritizes_active_over_archived(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")

            for idx in range(30):
                seed_session_asset(
                    repo_root,
                    message=f"active session {idx}",
                    session_id=f"rollout-2026-04-21T12-{idx:02d}-00-active-{idx:02d}",
                )
            for idx in range(15):
                seed_session_asset(
                    repo_root,
                    message=f"archived session {idx}",
                    session_id=f"rollout-2026-04-10T08-{idx:02d}-00-archived-{idx:02d}",
                    archived=True,
                )

            payload = codex_memo.bai.build_asset_index(repo_root)
            session_assets = payload["session_assets"]

            self.assertEqual(len(session_assets), 32)
            active_assets = [entry for entry in session_assets if ".codex/sessions/" in entry["path"]]
            archived_assets = [entry for entry in session_assets if ".codex/archived_sessions/" in entry["path"]]
            self.assertEqual(len(active_assets), 24)
            self.assertEqual(len(archived_assets), 8)
            self.assertTrue(all(".codex/sessions/" in entry["path"] for entry in session_assets[:24]))

    def test_asset_index_builds_memory_insights_for_canonical_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            write_note(
                repo_root / ".codex" / "memory" / "decisions" / "memory-layering.md",
                textwrap.dedent(
                    """\
                    ---
                    doc_id: decision-memory-layering
                    doc_type: decision
                    title: 记忆分层决策
                    status: active
                    scope: repo
                    tags: [memory, layering]
                    triggers:
                      - 设计记忆分层
                    keywords:
                      - memory layering
                    aliases:
                      - L1 insight
                    canonical: true
                    related: []
                    supersedes: []
                    last_verified: 2026-04-24
                    confidence: high
                    update_policy: merge
                    when_to_read:
                      - before memory architecture changes
                    """
                ),
                "使用分层记忆结构承接全局索引与长期沉淀.",
            )

            payload = codex_memo.bai.build_asset_index(repo_root)
            pointers = {entry["pointer"]: entry for entry in payload["insight_entries"]}

        self.assertIn("memory/runbooks/core.md", pointers)
        self.assertIn("memory/decisions/memory-layering.md", pointers)
        self.assertIn("L1 insight", pointers["memory/decisions/memory-layering.md"]["aliases"])

    def test_route_uses_insight_aliases_to_surface_canonical_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            write_note(
                repo_root / ".codex" / "memory" / "runbooks" / "insight-layer.md",
                textwrap.dedent(
                    """\
                    ---
                    doc_id: runbook-insight-layer
                    doc_type: runbook
                    title: Insight Layer Protocol
                    status: active
                    scope: repo
                    tags: [memory, insight]
                    triggers:
                      - 维护 insight layer
                    keywords:
                      - insight protocol
                    aliases:
                      - L1 insight
                    canonical: true
                    related: []
                    supersedes: []
                    last_verified: 2026-04-24
                    confidence: high
                    update_policy: merge
                    when_to_read:
                      - before insight changes
                    """
                ),
                "维护全局 insight 索引层.",
            )

            codex_memo.command_asset(repo_root)
            payload = codex_memo.mt.command_route(repo_root, task="L1 insight", top_k=3, record_event=False)

        self.assertTrue(payload["hits"])
        self.assertEqual(payload["hits"][0]["path"], "memory/runbooks/insight-layer.md")

    def test_session_asset_cache_invalidates_when_window_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)

            for idx in range(4):
                seed_session_asset(
                    repo_root,
                    message=f"active cache session {idx}",
                    session_id=f"rollout-2026-04-21T10-{idx:02d}-00-cache-{idx:02d}",
                )
            for idx in range(3):
                seed_session_asset(
                    repo_root,
                    message=f"archived cache session {idx}",
                    session_id=f"rollout-2026-04-10T08-{idx:02d}-00-cache-archived-{idx:02d}",
                    archived=True,
                )

            first = sa.discover_session_assets(repo_root, active_limit=3, archived_limit=2)
            self.assertEqual(len(first), 5)

            second = sa.discover_session_assets(repo_root, active_limit=2, archived_limit=1)
            self.assertEqual(len(second), 3)

            cache_payload = json.loads((repo_root / ".codex" / "cache" / "session-assets.json").read_text(encoding="utf-8"))
            self.assertEqual(cache_payload["version"], 2)
            self.assertEqual(cache_payload["active_limit"], 2)
            self.assertEqual(cache_payload["archived_limit"], 1)

    def test_session_asset_cache_invalidates_when_extraction_config_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)

            seed_session_asset(
                repo_root,
                message="first topic",
                session_id="rollout-2026-04-21T10-00-00-cache-config",
            )

            original_version = sa.EXTRACTION_CONFIG_VERSION
            try:
                first = sa.discover_session_assets(repo_root, active_limit=1, archived_limit=0)
                self.assertEqual(len(first), 1)
                sa.EXTRACTION_CONFIG_VERSION = original_version + 1
                second = sa.discover_session_assets(repo_root, active_limit=1, archived_limit=0)
                self.assertEqual(len(second), 1)
            finally:
                sa.EXTRACTION_CONFIG_VERSION = original_version

            cache_payload = json.loads((repo_root / ".codex" / "cache" / "session-assets.json").read_text(encoding="utf-8"))
            self.assertEqual(cache_payload["extraction_config"]["version"], original_version + 1)

    def test_session_asset_keeps_tail_snippet_for_longer_thread(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            session_path = repo_root / ".codex" / "sessions" / "2026" / "04" / "21" / "rollout-2026-04-21T00-00-00-tail.jsonl"
            session_path.parent.mkdir(parents=True, exist_ok=True)
            messages = [
                "first topic",
                "second topic",
                "third topic",
                "final decision",
            ]
            lines = [
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": text}],
                    },
                }
                for text in messages
            ]
            session_path.write_text("".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines), encoding="utf-8")

            assets = sa.discover_session_assets(repo_root, active_limit=1, archived_limit=0)
            self.assertEqual(len(assets), 1)
            description = assets[0]["description"]
            self.assertIn("first topic", description)
            self.assertIn("final decision", description)

    def test_route_prefers_canonical_runbook_over_session_when_both_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(
                repo_root,
                repo_type="repo-memory",
                summary="repo summary",
                note_title="记忆治理入口",
                note_body="memory hygiene aliases keywords governance session routing",
            )
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Runbook", note_body="home body")
            seed_session_asset(repo_root, message="记忆治理入口 session routing aliases keywords")
            codex_memo.mt.bai.write_asset_index(repo_root)

            result = run_cli("r", "--task", "记忆治理入口 session routing aliases keywords", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["project_memory_hits"])
            self.assertTrue(payload["project_asset_hits"])
            self.assertEqual(payload["project_memory_hits"][0]["doc_type"], "runbook")
            self.assertGreaterEqual(payload["project_memory_hits"][0]["score"], payload["project_asset_hits"][0]["score"])

    def test_inspect_accepts_route_style_memory_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Codex CLI Flow", note_body="repo codex cli route")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Codex CLI Flow", note_body="home codex cli route")

            result = run_cli("i", "--task", "codex cli", "--path", "memory/runbooks/core.md", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["source"], "project")
            self.assertEqual(payload["path"], "runbooks/core.md")

    def test_direct_memory_tool_inspect_command_is_usable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Codex CLI Flow", note_body="repo codex cli route")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Codex CLI Flow", note_body="home codex cli route")

            result = subprocess.run(
                [sys.executable, str(MEMORY_TOOL_SCRIPT), "inspect", "--repo-root", str(repo_root), "--task", "codex cli route", "--path", "memory/runbooks/core.md", "--format", "json"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                env={"PATH": os.environ.get("PATH", "")},
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["path"], "runbooks/core.md")
            self.assertGreaterEqual(payload["score"], 0.0)

            cli_result = run_cli("i", "--task", "codex cli route", "--path", "memory/runbooks/core.md", cwd=repo_root, home_root=home_root)
            self.assertEqual(cli_result.returncode, 0, msg=cli_result.stderr)
            cli_payload = json.loads(cli_result.stdout)
            self.assertEqual(payload["score"], cli_payload["score"])
            self.assertEqual(payload["reasons"], cli_payload["reasons"])

    def test_inspect_note_uses_cached_asset_index_without_rebuilding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Codex CLI Flow", note_body="repo codex cli route")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Codex CLI Flow", note_body="home codex cli route")
            codex_memo.bai.write_asset_index(repo_root)
            candidate, source = codex_memo.resolve_note_path(
                "memory/runbooks/core.md",
                repo_root=repo_root,
                home_root=home_root,
            )

            with mock.patch.object(codex_memo.bai, "build_asset_index", side_effect=AssertionError("unexpected rebuild")):
                payload = codex_memo.inspect_note(candidate, source=source, task="codex cli route", repo_root=repo_root, home_root=home_root)

        self.assertEqual(payload["path"], "runbooks/core.md")
        self.assertGreaterEqual(payload["score"], 0.0)

    def test_inspect_rejects_non_memory_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Codex CLI Flow", note_body="repo codex cli route")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Codex CLI Flow", note_body="home codex cli route")
            seed_assets(repo_root)

            result = run_cli("i", "--task", "codex cli", "--path", ".codex/scripts/codex_memo.py", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("not under project/home memory", result.stderr.lower())

            absolute_result = run_cli("i", "--task", "codex cli", "--path", str(repo_root / ".codex" / "scripts" / "codex_memo.py"), cwd=repo_root, home_root=home_root)
            self.assertEqual(absolute_result.returncode, 1)
            self.assertIn("not under project/home memory", absolute_result.stderr.lower())

    def test_maintain_runs_default_governance_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Runbook", note_body="repo body")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Runbook", note_body="home body")

            result = run_cli("m", cwd=repo_root, home_root=home_root)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("asset_index", payload)
            self.assertIn("sync", payload)
            self.assertIn("hygiene", payload)
            self.assertIn("governance_summary", payload)
            self.assertIn("session_recall_window", payload["governance_summary"])

    def test_semantic_index_rebuild_command_generates_cache_for_canonical_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(
                repo_root,
                repo_type="repo-memory",
                summary="repo summary",
                note_title="线程恢复流程",
                note_body="按 thread id 恢复历史会话与配置状态",
            )
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Runbook", note_body="home body")

            env = os.environ.copy()
            env["CODEX_MEMO_HOME_ROOT"] = str(home_root)
            env["CODEX_MEMO_SEMANTIC_FAKE"] = "1"
            result = subprocess.run(
                ["python3", str(SCRIPT_PATH), "sx"],
                cwd=str(repo_root),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["semantic_index"]["entry_count"], 1)
            self.assertEqual(payload["semantic_index"]["mode"], "fake")
            store_path = repo_root / ".codex" / "cache" / "memory-state.db"
            self.assertTrue(store_path.exists())
            cache_rows = read_sqlite_json_rows(store_path, "semantic_entries", "path")
            self.assertEqual(len(cache_rows), 1)
            self.assertIn("memory/runbooks/core.md", cache_rows)
            self.assertEqual(cache_rows["memory/runbooks/core.md"]["schema_version"], 1)
            self.assertIn("source_hash", cache_rows["memory/runbooks/core.md"])

    def test_semantic_inspect_command_returns_candidates_from_cached_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(
                repo_root,
                repo_type="repo-memory",
                summary="repo summary",
                note_title="线程恢复流程",
                note_body="按 thread id 恢复历史会话与配置状态",
            )
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Runbook", note_body="home body")

            env = os.environ.copy()
            env["CODEX_MEMO_HOME_ROOT"] = str(home_root)
            env["CODEX_MEMO_SEMANTIC_FAKE"] = "1"
            rebuild = subprocess.run(
                ["python3", str(SCRIPT_PATH), "sx"],
                cwd=str(repo_root),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rebuild.returncode, 0, msg=rebuild.stderr)

            inspect_result = subprocess.run(
                ["python3", str(SCRIPT_PATH), "si", "--task", "restore previous chat history"],
                cwd=str(repo_root),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(inspect_result.returncode, 0, msg=inspect_result.stderr)
            payload = json.loads(inspect_result.stdout)
            self.assertEqual(payload["semantic_mode"], "cached")
            self.assertTrue(payload["candidates"])
            self.assertEqual(payload["candidates"][0]["path"], "memory/runbooks/core.md")
            self.assertIn("semantic_reasons", payload["candidates"][0])

    def test_route_defaults_to_local_semantic_rerank_for_ambiguous_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Runbook", note_body="home body")
            seed_thread_recovery_note(repo_root)
            seed_restore_history_task_contract(repo_root)

            env = os.environ.copy()
            env["CODEX_MEMO_HOME_ROOT"] = str(home_root)
            env["CODEX_MEMO_SEMANTIC_FAKE"] = "1"

            rebuild = subprocess.run(
                ["python3", str(SCRIPT_PATH), "sx"],
                cwd=str(repo_root),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rebuild.returncode, 0, msg=rebuild.stderr)

            result = subprocess.run(
                ["python3", str(SCRIPT_PATH), "r", "--task", "restore previous chat history"],
                cwd=str(repo_root),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["semantic_mode"], "local")
            self.assertEqual(payload["execution_gate"]["state"], "hit")
            self.assertEqual(payload["execution_gate"]["selected_path"], "memory/runbooks/thread-recovery.md")
            self.assertEqual(payload["execution_gate"]["selected_ref"], "project:memory/runbooks/thread-recovery.md")
            self.assertTrue(payload["semantic_cache_hit"])
            self.assertEqual(payload["semantic_model_used"], "local-semantic-rerank")
            self.assertTrue(payload["rerank_reasons"])
            self.assertTrue(payload["rerank_candidates"])

    def test_route_rejects_removed_online_rerank_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Runbook", note_body="home body")
            seed_thread_recovery_note(repo_root)
            seed_restore_history_task_contract(repo_root)
            env = os.environ.copy()
            env["CODEX_MEMO_HOME_ROOT"] = str(home_root)

            result = subprocess.run(
                ["python3", str(SCRIPT_PATH), "r", "--task", "restore previous chat history", "--online-rerank"],
                cwd=str(repo_root),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("unrecognized arguments: --online-rerank", result.stderr)

    def test_route_does_not_rebuild_semantic_index_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Runbook", note_body="home body")
            seed_thread_recovery_note(repo_root)
            seed_restore_history_task_contract(repo_root)

            with mock.patch.object(codex_memo.sidx, "build_semantic_index", side_effect=AssertionError("should not rebuild semantic index")):
                payload = codex_memo.command_route(repo_root, home_root, task="restore previous chat history", top_k=3)

            self.assertIn(payload["semantic_mode"], {"local", "skipped"})
            self.assertEqual(payload["execution_gate"]["selected_path"], "memory/runbooks/thread-recovery.md")

    def test_route_uses_cached_asset_index_without_live_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Runbook", note_body="home body")
            seed_thread_recovery_note(repo_root)
            seed_assets(repo_root)
            codex_memo.mt.bai.write_asset_index(repo_root)
            codex_memo.mt.ROUTE_CONTEXT_CACHE.clear()

            with mock.patch.object(codex_memo.mt.bai, "build_asset_index", side_effect=AssertionError("should not rebuild asset index")):
                payload = codex_memo.command_route(repo_root, home_root, task="route helper skill", top_k=3, record_event=False)

            self.assertEqual(payload["project_hits"][0]["path"], ".codex/skills/route-helper/SKILL.md")
            self.assertEqual(payload["semantic_mode"], "local")
            self.assertEqual(payload["semantic_reasons"], {})
            self.assertIn("memory/runbooks/core.md", payload["lexical_reasons"])

    def test_route_task_doc_boundary_keeps_abstract_query_on_runbook(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Runbook", note_body="home body")
            seed_thread_recovery_note(repo_root)
            seed_restore_history_task_contract(repo_root)

            env = os.environ.copy()
            env["CODEX_MEMO_HOME_ROOT"] = str(home_root)
            env["CODEX_MEMO_SEMANTIC_FAKE"] = "1"

            rebuild = subprocess.run(
                ["python3", str(SCRIPT_PATH), "sx"],
                cwd=str(repo_root),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rebuild.returncode, 0, msg=rebuild.stderr)

            result = subprocess.run(
                ["python3", str(SCRIPT_PATH), "r", "--task", "restore previous chat history"],
                cwd=str(repo_root),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["project_hits"][0]["path"], "memory/runbooks/thread-recovery.md")
            self.assertNotEqual(payload["project_hits"][0]["doc_type"], "task-doc")

    def test_memory_tool_reuses_route_context_within_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_thread_recovery_note(repo_root)
            codex_memo.mt.bai.write_asset_index(repo_root)

            original_build = codex_memo.mt.bai.build_asset_index
            original_scan = codex_memo.mt.scan_memory_notes
            build_calls = 0
            scan_calls = 0

            def wrapped_build(active_repo_root):
                nonlocal build_calls
                build_calls += 1
                return original_build(active_repo_root)

            def wrapped_scan(active_repo_root):
                nonlocal scan_calls
                scan_calls += 1
                return original_scan(active_repo_root)

            codex_memo.mt.ROUTE_CONTEXT_CACHE.clear()
            codex_memo.mt.bai.build_asset_index = wrapped_build
            codex_memo.mt.scan_memory_notes = wrapped_scan
            try:
                codex_memo.mt.command_route(repo_root, task="读取线程记忆", top_k=3, record_event=False)
                codex_memo.mt.command_route(repo_root, task="restore previous chat history", top_k=3, record_event=False)
            finally:
                codex_memo.mt.bai.build_asset_index = original_build
                codex_memo.mt.scan_memory_notes = original_scan
                codex_memo.mt.ROUTE_CONTEXT_CACHE.clear()

            self.assertEqual(build_calls, 0)
            self.assertEqual(scan_calls, 1)

    def test_memory_tool_route_context_cache_evicts_oldest_entry(self) -> None:
        original_limit = codex_memo.mt.ROUTE_CONTEXT_CACHE_LIMIT
        try:
            codex_memo.mt.ROUTE_CONTEXT_CACHE_LIMIT = 2
            codex_memo.mt.ROUTE_CONTEXT_CACHE.clear()
            codex_memo.mt.cache_route_context("repo-a", {"signature": (1, 1)})
            codex_memo.mt.cache_route_context("repo-b", {"signature": (1, 1)})
            codex_memo.mt.cache_route_context("repo-c", {"signature": (1, 1)})
            self.assertNotIn("repo-a", codex_memo.mt.ROUTE_CONTEXT_CACHE)
            self.assertIn("repo-b", codex_memo.mt.ROUTE_CONTEXT_CACHE)
            self.assertIn("repo-c", codex_memo.mt.ROUTE_CONTEXT_CACHE)
        finally:
            codex_memo.mt.ROUTE_CONTEXT_CACHE_LIMIT = original_limit
            codex_memo.mt.ROUTE_CONTEXT_CACHE.clear()

    def test_session_assets_use_lightweight_summary_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            seed_session_asset(
                repo_root,
                message="restore previous chat history before digging into archived sessions",
            )
            sa_path = repo_root / ".codex" / "cache" / "session-assets.json"
            if sa_path.exists():
                sa_path.unlink()

            assets = sa.discover_session_assets(repo_root)

            self.assertEqual(len(assets), 1)
            self.assertEqual(assets[0]["name"], "restore previous chat history before digging into archived sessions")
            self.assertTrue(assets[0]["description"].startswith("task: "))

    def test_route_skips_semantic_rerank_for_high_confidence_runbook_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="review route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_thread_recovery_note(repo_root)
            seed_session_asset(repo_root, message="读取线程记忆时, 先翻 session 线索, 但最终还是要按 thread recovery runbook 执行")

            env = os.environ.copy()
            env["CODEX_MEMO_HOME_ROOT"] = str(home_root)
            env["CODEX_MEMO_SEMANTIC_FAKE"] = "1"

            rebuild = subprocess.run(
                ["python3", str(SCRIPT_PATH), "sx"],
                cwd=str(repo_root),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rebuild.returncode, 0, msg=rebuild.stderr)

            result = subprocess.run(
                ["python3", str(SCRIPT_PATH), "r", "--task", "读取线程记忆"],
                cwd=str(repo_root),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["semantic_mode"], "skipped")
            self.assertEqual(payload["execution_gate"]["state"], "hit")
            self.assertEqual(payload["execution_gate"]["selected_path"], "memory/runbooks/thread-recovery.md")
            self.assertEqual(payload["semantic_model_used"], "")
            self.assertFalse(payload["rerank_reasons"])
            self.assertFalse(payload["gate_override_reason"])

    def test_route_triggers_semantic_rerank_for_abstract_ga_memory_query(self) -> None:
        lexical_hits = [
            {
                "path": "memory/runbooks/genericagent-memory-retrieval-and-review-entry.md",
                "kind": "memory",
                "title": "GA 记忆系统, 检索入口与语义召回总入口",
                "doc_type": "runbook",
                "source": "project",
                "score": 10.0,
            },
            {
                "path": ".codex/sessions/demo.jsonl",
                "kind": "asset",
                "title": "ga memory session",
                "doc_type": "session",
                "asset_type": "session",
                "source": "project",
                "score": 2.0,
            },
        ]

        should_rerank, reason = codex_memo.should_apply_semantic_rerank(
            task="GA 的记忆系统, 记忆检索, 语义召回, LLM 参与检索",
            merged_hits=lexical_hits,
            semantic_candidates=[],
            execution_gate={"state": "hit", "selected_path": "memory/runbooks/genericagent-memory-retrieval-and-review-entry.md"},
        )

        self.assertTrue(should_rerank)
        self.assertIn(reason, {"mixed_language_query", "abstract_intent_query"})

    def test_route_keeps_execution_gate_on_surfaced_hit_when_rerank_selects_unsurfaced_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            surfaced_hit = {
                "path": "memory/runbooks/thread-recovery.md",
                "kind": "memory",
                "title": "线程恢复流程",
                "doc_type": "runbook",
                "score": 1.0,
                "reasons": [],
                "source": "project",
                "ref": "project:memory/runbooks/thread-recovery.md",
            }
            rerank_candidate = {
                "path": "memory/runbooks/unsurfaced.md",
                "kind": "memory",
                "title": "未 surfaced 的 runbook",
                "doc_type": "runbook",
                "source": "project",
                "ref": "project:memory/runbooks/unsurfaced.md",
            }
            route_payload = {
                "hits": [surfaced_hit],
                "memory_hits": [surfaced_hit],
                "asset_hits": [],
                "fallback_context": False,
                "route_event_id": "evt_demo",
                "surfaced_hits_hash": "hash_demo",
            }
            semantic_payload = {
                "lexical_reasons": {},
                "semantic_reasons": {},
                "rerank_reasons": ["semantic override"],
                "gate_override_reason": "promoted unsurfaced candidate",
                "semantic_mode": "local",
                "semantic_model_used": "fake-semantic-client",
                "semantic_cache_hit": True,
                "rerank_candidates": [rerank_candidate],
                "rerank_skipped_reason": "",
                "semantic_trigger_reason": "semantic_conflict",
                "rerank_selected_path": "memory/runbooks/unsurfaced.md",
                "rerank_selected_ref": "project:memory/runbooks/unsurfaced.md",
                "rerank_selected_state": "hit",
            }
            with (
                mock.patch.object(codex_memo.mt, "command_route", return_value=route_payload),
                mock.patch.object(codex_memo.sidx, "inspect_semantic_candidates", return_value={"candidates": []}),
                mock.patch.object(codex_memo, "apply_semantic_rerank", return_value=semantic_payload),
            ):
                payload = codex_memo.command_route(repo_root, repo_root, task="restore previous chat history", top_k=3, record_event=False)

        self.assertEqual(payload["execution_gate"]["state"], "hit")
        self.assertEqual(payload["execution_gate"]["selected_path"], "memory/runbooks/thread-recovery.md")
        self.assertEqual(payload["execution_gate"]["selected_ref"], "project:memory/runbooks/thread-recovery.md")

    def test_route_can_promote_semantic_index_candidate_into_execution_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            surfaced_hit = {
                "path": "memory/runbooks/lexical.md",
                "kind": "memory",
                "title": "Lexical",
                "doc_type": "runbook",
                "score": 1.0,
                "reasons": [],
                "source": "project",
                "ref": "project:memory/runbooks/lexical.md",
            }
            semantic_candidate = {
                "path": "memory/runbooks/semantic-only.md",
                "kind": "memory",
                "title": "Semantic Only",
                "doc_type": "runbook",
                "source": "project",
                "score": 6.0,
                "semantic_reasons": ["intent:route quality"],
            }
            route_payload = {
                "hits": [surfaced_hit],
                "memory_hits": [surfaced_hit],
                "asset_hits": [],
                "fallback_context": False,
                "route_event_id": "evt_demo",
                "surfaced_hits_hash": "hash_demo",
            }
            semantic_payload = {
                "lexical_reasons": {},
                "semantic_reasons": {"memory/runbooks/semantic-only.md": ["intent:route quality"]},
                "rerank_reasons": ["semantic index match"],
                "gate_override_reason": "promoted semantic candidate",
                "semantic_mode": "local",
                "semantic_model_used": "fake-semantic-client",
                "semantic_cache_hit": True,
                "rerank_candidates": [semantic_candidate],
                "rerank_skipped_reason": "",
                "semantic_trigger_reason": "semantic_conflict",
                "rerank_selected_path": "memory/runbooks/semantic-only.md",
                "rerank_selected_ref": "project:memory/runbooks/semantic-only.md",
                "rerank_selected_state": "hit",
            }
            with (
                mock.patch.object(codex_memo.mt, "command_route", return_value=route_payload),
                mock.patch.object(codex_memo.sidx, "inspect_semantic_candidates", return_value={"candidates": [semantic_candidate]}),
                mock.patch.object(codex_memo, "apply_semantic_rerank", return_value=semantic_payload),
            ):
                payload = codex_memo.command_route(repo_root, repo_root, task="route quality", top_k=3, record_event=False)

        self.assertEqual(payload["execution_gate"]["state"], "hit")
        self.assertEqual(payload["execution_gate"]["selected_path"], "memory/runbooks/semantic-only.md")
        self.assertEqual(payload["execution_gate"]["selected_ref"], "project:memory/runbooks/semantic-only.md")

    def test_strong_lexical_runbook_guard_keeps_execution_gate_for_weaker_semantic_runbook(self) -> None:
        gate_candidate = {
            "path": "memory/runbooks/long-task-completion-boundary-enforcement.md",
            "kind": "memory",
            "doc_type": "runbook",
            "lexical_score": 4.7,
        }
        selected_candidate = {
            "path": "memory/runbooks/windows-user-installed-tools-default-d-drive.md",
            "kind": "memory",
            "doc_type": "runbook",
            "lexical_score": 0.6,
        }

        kept_candidate, reasons = codex_memo.strong_lexical_runbook_guard(
            candidates=[gate_candidate, selected_candidate],
            selected_candidate=selected_candidate,
            execution_gate={"state": "hit", "selected_path": "memory/runbooks/long-task-completion-boundary-enforcement.md"},
        )

        self.assertEqual(kept_candidate, gate_candidate)
        self.assertEqual(reasons, ["lexical_guard:keep_strong_execution_gate_runbook"])

    def test_memory_benchmark_emits_full_breakdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            cases_path = Path(tmpdir) / "cases.json"
            cases_path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "semantic-case",
                                "query": "restore previous chat history",
                                "mode": "semantic_required",
                                "expected_top1": "memory/runbooks/thread-recovery.md",
                                "expected_any": [{"path": "memory/runbooks/thread-recovery.md"}],
                            },
                            {
                                "id": "lexical-case",
                                "query": "session recall strategy",
                                "mode": "lexical_or_semantic",
                                "expected_top1": "memory/runbooks/session-recall.md",
                                "expected_any": [{"path": "memory/runbooks/session-recall.md"}],
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def fake_legacy(_repo_root: Path, query: str, _top_k: int) -> dict[str, object]:
                path = "memory/runbooks/thread-recovery.md" if "history" in query else "memory/runbooks/session-recall.md"
                return {"hits": [{"path": path, "title": path, "kind": "memory", "score": 1.0}], "fallback_context": False}

            def fake_enhanced(_repo_root: Path, query: str, _top_k: int) -> dict[str, object]:
                if "history" in query:
                    return {
                        "hits": [{"path": "memory/runbooks/thread-recovery.md", "title": "thread", "kind": "memory", "score": 2.0}],
                        "fallback_context": False,
                        "execution_gate": {"selected_path": "memory/runbooks/thread-recovery.md"},
                        "semantic_mode": "local",
                    }
                return {
                    "hits": [{"path": "memory/runbooks/session-recall.md", "title": "session", "kind": "memory", "score": 1.0}],
                    "fallback_context": False,
                    "execution_gate": {"selected_path": "memory/runbooks/session-recall.md"},
                    "semantic_mode": "skipped",
                }

            args = argparse.Namespace(repo_root=str(repo_root), cases=str(cases_path))
            with (
                mock.patch.object(memory_benchmark, "parse_args", return_value=args),
                mock.patch.object(memory_benchmark, "_legacy_route", side_effect=fake_legacy),
                mock.patch.object(memory_benchmark, "_baseline_route", side_effect=fake_legacy),
                mock.patch.object(memory_benchmark, "_enhanced_route", side_effect=fake_enhanced),
                mock.patch.object(memory_benchmark, "_insight_replay", return_value={}),
                mock.patch.object(memory_benchmark, "_learning_replay", return_value={}),
                mock.patch.object(memory_benchmark, "_adoption_replay", return_value={}),
                mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
            ):
                rc = memory_benchmark.main()

            self.assertEqual(rc, 0)
            payload = json.loads(stdout.getvalue())
            self.assertIn("mode_breakdown", payload["summary"])
            self.assertEqual(payload["summary"]["mode_breakdown"]["full"]["case_count"], 2)
            self.assertEqual(payload["summary"]["mode_breakdown"]["full"]["selected_top1_hits"], 2)
            self.assertEqual(payload["summary"]["enhanced_top1_hits"], payload["summary"]["mode_breakdown"]["full"]["top1_hits"])
            self.assertEqual(payload["summary"]["enhanced_topk_hits"], payload["summary"]["mode_breakdown"]["full"]["topk_hits"])
            self.assertEqual(payload["summary"]["enhanced_fallback_count"], payload["summary"]["mode_breakdown"]["full"]["fallback_count"])
            self.assertEqual(payload["summary"]["selected_top1_hits"], payload["summary"]["mode_breakdown"]["full"]["selected_top1_hits"])
            self.assertNotIn("degraded_probe", payload["cases"][0])

    def test_memory_benchmark_rejects_semantic_required_case_when_full_mode_skips_semantic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            cases_path = Path(tmpdir) / "cases.json"
            cases_path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "semantic-case",
                                "query": "restore previous chat history",
                                "mode": "semantic_required",
                                "expected_top1": "memory/runbooks/thread-recovery.md",
                                "expected_any": [{"path": "memory/runbooks/thread-recovery.md"}],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            route_payload = {
                "hits": [{"path": "memory/runbooks/thread-recovery.md", "title": "thread", "kind": "memory", "score": 1.0}],
                "fallback_context": False,
                "execution_gate": {"selected_path": "memory/runbooks/thread-recovery.md"},
                "semantic_mode": "skipped",
            }
            args = argparse.Namespace(repo_root=str(repo_root), cases=str(cases_path))
            with (
                mock.patch.object(memory_benchmark, "parse_args", return_value=args),
                mock.patch.object(memory_benchmark, "_legacy_route", return_value=route_payload),
                mock.patch.object(memory_benchmark, "_baseline_route", return_value=route_payload),
                mock.patch.object(memory_benchmark, "_enhanced_route", return_value=route_payload),
                mock.patch.object(memory_benchmark, "_insight_replay", return_value={}),
                mock.patch.object(memory_benchmark, "_learning_replay", return_value={}),
                mock.patch.object(memory_benchmark, "_adoption_replay", return_value={}),
                mock.patch("sys.stdout", new_callable=io.StringIO),
            ):
                rc = memory_benchmark.main()

        self.assertEqual(rc, 1)

    def test_memory_benchmark_enhanced_route_disables_route_event_recording(self) -> None:
        with mock.patch.object(
            memory_benchmark.codex_memo,
            "command_route",
            return_value={
                "merged_hits": [],
                "fallback_context": False,
                "execution_gate": {"selected_path": ""},
                "semantic_mode": "skipped",
            },
        ) as command_route:
            payload = memory_benchmark._enhanced_route(Path("/tmp/repo"), "benchmark query", 3)

        self.assertEqual(payload["semantic_mode"], "skipped")
        self.assertEqual(command_route.call_args.kwargs["record_event"], False)

    def test_memory_benchmark_auxiliary_routes_disable_route_event_recording(self) -> None:
        payload = {"hits": [], "fallback_context": False}
        with mock.patch.object(memory_benchmark.mt, "command_route", return_value=payload) as command_route:
            memory_benchmark._baseline_route(Path("/tmp/repo"), "benchmark query", 3)
            memory_benchmark._route_without_learning(Path("/tmp/repo"), "benchmark query", 3)

        self.assertEqual(command_route.call_args_list[0].kwargs["record_event"], False)
        self.assertEqual(command_route.call_args_list[1].kwargs["record_event"], False)

    def test_memory_benchmark_replays_disable_route_event_recording(self) -> None:
        route_payload = {
            "hits": [{"path": "memory/runbooks/thread-recovery.md", "score": 1.0, "reasons": []}],
            "fallback_context": False,
        }
        checkpoint_payload = {"retrieval_traces": []}
        with (
            mock.patch.object(memory_benchmark.mt, "command_route", return_value=route_payload) as command_route,
            mock.patch.object(memory_benchmark.rl, "record_success"),
            mock.patch.object(memory_benchmark.rc, "upsert_checkpoint"),
            mock.patch.object(memory_benchmark.rc, "read_checkpoint", return_value=checkpoint_payload),
        ):
            memory_benchmark._insight_replay()
            memory_benchmark._learning_replay()
            memory_benchmark._adoption_replay()

        self.assertGreaterEqual(len(command_route.call_args_list), 6)
        for call in command_route.call_args_list:
            self.assertEqual(call.kwargs["record_event"], False)

    def test_checkpoint_accepts_selected_hit_beyond_five_route_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Runbook", note_body="repo body")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Runbook", note_body="home body")
            memory_root = repo_root / ".codex" / "memory" / "runbooks"
            for idx in range(6):
                write_note(
                    memory_root / f"extra-{idx}.md",
                    textwrap.dedent(
                        f"""\
                        ---
                        doc_id: runbook-extra-{idx}
                        doc_type: runbook
                        title: Extra Route {idx}
                        aliases: [extra route {idx}, extra-{idx}, route-{idx}]
                        status: active
                        scope: repo
                        tags: [route]
                        triggers:
                          - route fixture {idx}
                        keywords:
                          - route fixture
                          - extra
                          - {idx}
                        canonical: true
                        related: []
                        supersedes: []
                        last_verified: 2026-04-22
                        confidence: high
                        update_policy: merge
                        when_to_read:
                          - route fixture
                        ---
                        """
                    ),
                    f"# Extra {idx}\n\nroute fixture extra {idx}\n",
                )

            route_result = run_cli("r", "--task", "route fixture extra", "--top-k", "6", cwd=repo_root, home_root=home_root)
            self.assertEqual(route_result.returncode, 0, msg=route_result.stderr)
            route_payload = json.loads(route_result.stdout)
            selected_hit = route_payload["project_hits"][5]["path"]

            checkpoint_result = run_cli(
                "k",
                "--task",
                "route fixture closeout",
                "--route-query",
                "route fixture extra",
                "--route-event-id",
                route_payload["route_event_id"],
                "--surfaced-hits-hash",
                route_payload["surfaced_hits_hash"],
                "--selected-hit",
                selected_hit,
                "--adopted-hit",
                selected_hit,
                "--observed-actions",
                "validated sixth surfaced hit",
                "--evidence-paths",
                selected_hit,
                cwd=repo_root,
                home_root=home_root,
            )

            self.assertEqual(checkpoint_result.returncode, 0, msg=checkpoint_result.stderr)

    def test_new_sync_and_check_work_on_project_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Codex CLI Flow", note_body="repo codex cli route")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Codex CLI Flow", note_body="home codex cli route")
            templates = repo_root / ".codex" / "memory"
            write_note(
                templates / "runbooks" / "_template.md",
                textwrap.dedent(
                    """\
                    ---
                    doc_id: runbook-template
                    doc_type: runbook
                    title: Template
                    status: active
                    scope: repo
                    tags: [workflow]
                    triggers:
                      - trigger
                    keywords:
                      - keyword
                    canonical: true
                    related: []
                    supersedes: []
                    last_verified: 2026-04-19
                    confidence: high
                    update_policy: merge
                    when_to_read:
                      - before task
                    """
                ),
                "# Template Body",
            )

            checkpoint_result = run_cli(
                "k",
                "--task",
                "fresh note creation",
                "--verified-steps",
                "validated fresh note",
                "--related-assets",
                "memory/runbooks/core.md",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(checkpoint_result.returncode, 0, msg=checkpoint_result.stderr)

            create_result = run_cli(
                "n",
                "--type",
                "runbook",
                "--slug",
                "fresh-note",
                "--title",
                "Fresh Note",
                "--task",
                "fresh note creation",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(create_result.returncode, 0, msg=create_result.stderr)
            self.assertTrue((repo_root / ".codex" / "memory" / "runbooks" / "fresh-note.md").exists())

            asset_result = run_cli("a", cwd=repo_root, home_root=home_root)
            self.assertEqual(asset_result.returncode, 0, msg=asset_result.stderr)
            asset_payload = json.loads(asset_result.stdout)
            self.assertEqual(asset_payload["counts"]["runbooks"], 2)
            self.assertTrue((repo_root / ".codex" / "cache" / "asset-index.json").exists())

            sync_result = run_cli("s", cwd=repo_root, home_root=home_root)
            self.assertEqual(sync_result.returncode, 0, msg=sync_result.stderr)
            sync_payload = json.loads(sync_result.stdout)
            self.assertEqual(sync_payload["registry_path"], ".codex/memory/registry.md")

            check_result = run_cli("c", cwd=repo_root, home_root=home_root)
            self.assertEqual(check_result.returncode, 0, msg=check_result.stderr)
            check_payload = json.loads(check_result.stdout)
            self.assertEqual(check_payload["issue_count"], 0)

    def test_checkpoint_roundtrip_stays_out_of_canonical_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")

            write_result = run_cli(
                "k",
                "--task",
                "memory route refinement",
                "--key-facts",
                "asset aware retrieval;checkpoint layer",
                "--related-assets",
                ".codex/scripts/codex_memo.py",
                "--current-invariant",
                "do not touch canonical memory",
                "--verified-steps",
                "route tests pass",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(write_result.returncode, 0, msg=write_result.stderr)
            write_payload = json.loads(write_result.stdout)
            self.assertTrue(write_payload["exists"])
            self.assertIn("asset aware retrieval", write_payload["key_facts"])
            checkpoint_path = repo_root / ".codex" / "cache" / "memory-state.db"
            self.assertTrue(checkpoint_path.exists())
            self.assertFalse((repo_root / ".codex" / "memory" / "runtime-checkpoints.json").exists())

            read_result = run_cli("k", "--task", "memory route refinement", cwd=repo_root, home_root=home_root)
            self.assertEqual(read_result.returncode, 0, msg=read_result.stderr)
            read_payload = json.loads(read_result.stdout)
            self.assertEqual(read_payload["task"], "memory route refinement")
            self.assertNotIn("learning", write_payload)
            self.assertEqual(read_payload["task_assets"], [".codex/scripts/codex_memo.py"])

    def test_new_requires_verification_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")

            result = run_cli(
                "n",
                "--type",
                "runbook",
                "--slug",
                "guarded-note",
                "--title",
                "Guarded Note",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("requires --task with a verified checkpoint or --task-id with a verifier sidecar", result.stderr)

    def test_new_accepts_verified_checkpoint_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            write_note(
                repo_root / ".codex" / "memory" / "runbooks" / "_template.md",
                textwrap.dedent(
                    """\
                    ---
                    doc_id: runbook-template
                    doc_type: runbook
                    title: Template
                    status: active
                    scope: repo
                    tags: [workflow]
                    triggers:
                      - trigger
                    keywords:
                      - keyword
                    canonical: true
                    related: []
                    supersedes: []
                    last_verified: 2026-04-24
                    confidence: high
                    update_policy: merge
                    when_to_read:
                      - before task
                    """
                ),
                "# Template Body",
            )

            checkpoint_result = run_cli(
                "k",
                "--task",
                "create guarded note",
                "--verified-steps",
                "validated note structure",
                "--related-assets",
                "memory/runbooks/core.md",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(checkpoint_result.returncode, 0, msg=checkpoint_result.stderr)

            result = run_cli(
                "n",
                "--type",
                "runbook",
                "--slug",
                "guarded-note",
                "--title",
                "Guarded Note",
                "--task",
                "create guarded note",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue((repo_root / ".codex" / "memory" / "runbooks" / "guarded-note.md").exists())
            self.assertEqual(payload["verification_gate"]["sources"], ["checkpoint"])

    def test_update_requires_verification_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")

            result = run_cli(
                "u",
                "--path",
                "memory/runbooks/core.md",
                "--title",
                "Updated Title",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("requires --task with a verified checkpoint or --task-id with a verifier sidecar", result.stderr)

    def test_flush_scaffold_requires_verification_but_plain_flush_still_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")

            blocked = run_cli(
                "f",
                "--doc-type",
                "runbook",
                "--slug",
                "guarded-flush",
                "--title",
                "Guarded Flush",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(blocked.returncode, 1)
            self.assertIn("requires --task with a verified checkpoint or --task-id with a verifier sidecar", blocked.stderr)

            allowed = run_cli("f", cwd=repo_root, home_root=home_root)
            self.assertEqual(allowed.returncode, 0, msg=allowed.stderr)

    def test_promotion_roundtrip_reads_separately_from_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")

            checkpoint_result = run_cli(
                "k",
                "--task",
                "memory route refinement",
                "--key-facts",
                "asset aware retrieval;checkpoint layer",
                "--related-assets",
                "memory/runbooks/core.md",
                "--current-invariant",
                "do not touch canonical memory",
                "--verified-steps",
                "route tests pass",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(checkpoint_result.returncode, 0, msg=checkpoint_result.stderr)

            create_result = run_cli(
                "lp",
                "--task",
                "memory route refinement",
                "--title",
                "Promote route refinement",
                "--summary",
                "Summarize the stable route refinement protocol.",
                "--doc-type",
                "decision",
                "--evidence-paths",
                "memory/runbooks/core.md",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(create_result.returncode, 0, msg=create_result.stderr)
            create_payload = json.loads(create_result.stdout)
            self.assertEqual(create_payload["doc_type"], "decision")
            self.assertEqual(create_payload["source_checkpoint"]["task"], "memory route refinement")

            read_result = run_cli("lp", "--task", "memory route refinement", cwd=repo_root, home_root=home_root)
            self.assertEqual(read_result.returncode, 0, msg=read_result.stderr)
            read_payload = json.loads(read_result.stdout)
            self.assertEqual(read_payload["count"], 1)
            self.assertEqual(read_payload["promotions"][0]["promotion_id"], create_payload["promotion_id"])

            db_path = repo_root / ".codex" / "cache" / "memory-state.db"
            promotion_rows = read_sqlite_json_rows(db_path, "promotions", "promotion_id")
            checkpoint_rows = read_sqlite_json_rows(db_path, "checkpoints", "task_fingerprint")
            self.assertIn(create_payload["promotion_id"], promotion_rows)
            self.assertEqual(len(checkpoint_rows), 1)

            checkpoint_read = run_cli("k", "--task", "memory route refinement", cwd=repo_root, home_root=home_root)
            self.assertEqual(checkpoint_read.returncode, 0, msg=checkpoint_read.stderr)
            checkpoint_payload = json.loads(checkpoint_read.stdout)
            self.assertTrue(checkpoint_payload["exists"])
            self.assertNotIn("promotions", checkpoint_payload)

    def test_promotion_requires_existing_working_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")

            result = run_cli(
                "lp",
                "--task",
                "missing checkpoint task",
                "--title",
                "Promote route refinement",
                "--summary",
                "Summarize the stable route refinement protocol.",
                "--doc-type",
                "decision",
                "--evidence-paths",
                "memory/runbooks/core.md",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("existing working checkpoint is required", result.stderr)

    def test_agent_surfaces_long_term_promotions_separately(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")

            checkpoint_result = run_cli(
                "k",
                "--task",
                "memory route refinement",
                "--key-facts",
                "asset aware retrieval",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(checkpoint_result.returncode, 0, msg=checkpoint_result.stderr)

            create_result = run_cli(
                "lp",
                "--task",
                "memory route refinement",
                "--title",
                "Promote route refinement",
                "--summary",
                "Summarize the stable route refinement protocol.",
                "--doc-type",
                "decision",
                "--evidence-paths",
                "memory/runbooks/core.md",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(create_result.returncode, 0, msg=create_result.stderr)

            agent_result = run_cli("g", "--task", "memory route refinement", cwd=repo_root, home_root=home_root)
            self.assertEqual(agent_result.returncode, 0, msg=agent_result.stderr)
            agent_payload = json.loads(agent_result.stdout)
            self.assertEqual(agent_payload["long_term_memory"]["count"], 1)
            self.assertIn("Promote route refinement", agent_payload["long_term_memory"]["prompt_block"])
            self.assertNotIn("Promote route refinement", agent_payload["working_memory"]["prompt_block"])

    def test_task_assets_do_not_write_learning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_thread_recovery_note(repo_root)

            before = run_cli("r", "--task", "找回之前聊天记录", cwd=repo_root, home_root=home_root)
            self.assertEqual(before.returncode, 0, msg=before.stderr)
            before_payload = json.loads(before.stdout)
            self.assertEqual(before_payload["project_hits"][0]["path"], "memory/runbooks/thread-recovery.md")
            before_score = before_payload["project_hits"][0]["score"]

            learned = run_cli(
                "k",
                "--task",
                "找回之前聊天记录",
                "--related-assets",
                "memory/runbooks/thread-recovery.md",
                "--key-facts",
                "thread recovery reused",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(learned.returncode, 0, msg=learned.stderr)
            learned_payload = json.loads(learned.stdout)
            self.assertNotIn("learning", learned_payload)

            after = run_cli("r", "--task", "找回之前聊天记录", cwd=repo_root, home_root=home_root)
            self.assertEqual(after.returncode, 0, msg=after.stderr)
            after_payload = json.loads(after.stdout)
            self.assertEqual(after_payload["project_hits"][0]["path"], "memory/runbooks/thread-recovery.md")
            self.assertEqual(after_payload["project_hits"][0]["score"], before_score)

    def test_checkpoint_adoption_records_trace_and_strengthens_future_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_thread_recovery_note(repo_root)
            seed_session_asset(repo_root, message="找回之前聊天记录, 线程恢复补充讨论")
            write_note(
                repo_root / ".codex" / "memory" / "runbooks" / "thread-recovery-alt.md",
                textwrap.dedent(
                    """\
                    ---
                    doc_id: runbook-thread-recovery-alt
                    doc_type: runbook
                    title: 线程恢复补充流程
                    status: active
                    scope: repo
                    tags: [codex, threads, recovery]
                    triggers:
                      - 线程列表恢复
                    keywords:
                      - thread recovery
                    canonical: true
                    related: []
                    supersedes: []
                    last_verified: 2026-04-20
                    confidence: medium
                    update_policy: merge
                    when_to_read:
                      - 排查线程丢失时
                    """
                ),
                "按 session 线索补充恢复路径.",
            )

            route_result = run_cli("r", "--task", "找回之前聊天记录", cwd=repo_root, home_root=home_root)
            self.assertEqual(route_result.returncode, 0, msg=route_result.stderr)
            route_payload = json.loads(route_result.stdout)
            top_hit = route_payload["project_hits"][0]["path"]
            before_score = route_payload["project_hits"][0]["score"]
            route_event_id = route_payload["route_event_id"]
            surfaced_hits_hash = route_payload["surfaced_hits_hash"]

            checkpoint_result = run_cli(
                "k",
                "--task",
                "thread recovery adoption",
                "--route-query",
                "找回之前聊天记录",
                "--route-event-id",
                route_event_id,
                "--surfaced-hits-hash",
                surfaced_hits_hash,
                "--selected-hit",
                top_hit,
                "--adopted-hit",
                top_hit,
                "--observed-actions",
                "使用 thread id 反查历史会话;沿用 thread recovery runbook",
                "--evidence-paths",
                top_hit,
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(checkpoint_result.returncode, 0, msg=checkpoint_result.stderr)
            checkpoint_payload = json.loads(checkpoint_result.stdout)
            self.assertIn("adoption_learning", checkpoint_payload)
            self.assertEqual(checkpoint_payload["adoption_learning"]["count"], 1)
            self.assertEqual(checkpoint_payload["retrieval_traces"][0]["adoption_state"], "adopted")
            self.assertEqual(checkpoint_payload["retrieval_traces"][0]["selected_hit"], top_hit)
            self.assertEqual(checkpoint_payload["retrieval_traces"][0]["adopted_hit"], top_hit)
            self.assertIn(top_hit, checkpoint_payload["retrieval_traces"][0]["surfaced_hits"])

            after_result = run_cli("r", "--task", "找回之前聊天记录", cwd=repo_root, home_root=home_root)
            self.assertEqual(after_result.returncode, 0, msg=after_result.stderr)
            after_payload = json.loads(after_result.stdout)
            self.assertEqual(after_payload["project_hits"][0]["path"], top_hit)
            self.assertGreater(after_payload["project_hits"][0]["score"], before_score)
            self.assertTrue(
                any("adoption:1" in reason for reason in after_payload["project_hits"][0]["reasons"]),
                msg=after_payload["project_hits"][0]["reasons"],
            )

    def test_checkpoint_adoption_requires_route_event_or_explicit_surfaced_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_thread_recovery_note(repo_root)

            result = run_cli(
                "k",
                "--task",
                "thread recovery adoption",
                "--route-query",
                "找回之前聊天记录",
                "--selected-hit",
                "memory/runbooks/thread-recovery.md",
                cwd=repo_root,
                home_root=home_root,
            )

            self.assertEqual(result.returncode, 1)
            error_payload = json.loads(result.stderr)
            self.assertIn("route_event_id", error_payload["error"])

    def test_checkpoint_adoption_requires_actions_and_allows_distinct_adopted_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_thread_recovery_note(repo_root)
            seed_session_asset(repo_root, message="找回之前聊天记录, 先看 session 线索, 再按 thread recovery runbook 执行")

            top_hit = ".codex/sessions/2026/04/20/rollout-2026-04-20T00-00-00-demo.jsonl"
            adopted_hit = "memory/runbooks/thread-recovery.md"
            fabricated_hits = [top_hit, adopted_hit]
            fabricated_event_id = "evt_manual_mismatch"
            fabricated_hash = codex_memo.rl.surfaced_hits_hash(fabricated_hits)
            route_events_path = repo_root / ".codex" / "evolution" / "route-events.jsonl"
            route_events_path.parent.mkdir(parents=True, exist_ok=True)
            with route_events_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "event_id": fabricated_event_id,
                            "recorded_at": "2026-04-21T00:00:00+00:00",
                            "query": "找回之前聊天记录",
                            "normalized_query": codex_memo.rl.normalize_query("找回之前聊天记录"),
                            "fallback_context": False,
                            "hits_hash": fabricated_hash,
                            "hits": [{"path": top_hit}, {"path": adopted_hit}],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            surfaced_hits = ",".join(fabricated_hits)

            distinct_adoption = run_cli(
                "k",
                "--task",
                "thread recovery adoption mismatch",
                "--route-query",
                "找回之前聊天记录",
                "--route-event-id",
                fabricated_event_id,
                "--surfaced-hits-hash",
                fabricated_hash,
                "--surfaced-hits",
                surfaced_hits,
                "--selected-hit",
                top_hit,
                "--adopted-hit",
                adopted_hit,
                "--observed-actions",
                "先读 session, 最终沿用 thread recovery runbook",
                "--evidence-paths",
                "memory/runbooks/thread-recovery.md",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(distinct_adoption.returncode, 0, msg=distinct_adoption.stderr)
            distinct_payload = json.loads(distinct_adoption.stdout)
            latest_trace = distinct_payload["retrieval_traces"][-1]
            self.assertEqual(latest_trace["selected_hit"], top_hit)
            self.assertEqual(latest_trace["adopted_hit"], adopted_hit)

            missing_actions = run_cli(
                "k",
                "--task",
                "thread recovery adoption missing actions",
                "--route-query",
                "找回之前聊天记录",
                "--route-event-id",
                fabricated_event_id,
                "--surfaced-hits-hash",
                fabricated_hash,
                "--selected-hit",
                top_hit,
                "--adopted-hit",
                adopted_hit,
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(missing_actions.returncode, 1)
            missing_actions_payload = json.loads(missing_actions.stderr)
            self.assertIn("observed_actions", missing_actions_payload["error"])

    def test_checkpoint_reports_closeout_gate_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_thread_recovery_note(repo_root)

            route_result = run_cli("r", "--task", "找回之前聊天记录", cwd=repo_root, home_root=home_root)
            self.assertEqual(route_result.returncode, 0, msg=route_result.stderr)
            route_payload = json.loads(route_result.stdout)

            pending_result = run_cli(
                "k",
                "--task",
                "thread recovery pending closeout",
                "--route-query",
                "找回之前聊天记录",
                "--route-event-id",
                route_payload["route_event_id"],
                "--surfaced-hits-hash",
                route_payload["surfaced_hits_hash"],
                "--selected-hit",
                "memory/runbooks/thread-recovery.md",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(pending_result.returncode, 0, msg=pending_result.stderr)
            pending_payload = json.loads(pending_result.stdout)
            self.assertEqual(pending_payload["closeout_gate"]["status"], "pending")
            self.assertEqual(pending_payload["closeout_gate"]["required"], ["adoption_evidence"])

            done_result = run_cli(
                "k",
                "--task",
                "thread recovery done closeout",
                "--route-query",
                "找回之前聊天记录",
                "--route-event-id",
                route_payload["route_event_id"],
                "--surfaced-hits-hash",
                route_payload["surfaced_hits_hash"],
                "--selected-hit",
                "memory/runbooks/thread-recovery.md",
                "--adopted-hit",
                "memory/runbooks/thread-recovery.md",
                "--observed-actions",
                "沿用 thread recovery runbook",
                "--evidence-paths",
                "memory/runbooks/thread-recovery.md",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(done_result.returncode, 0, msg=done_result.stderr)
            done_payload = json.loads(done_result.stdout)
            self.assertEqual(done_payload["closeout_gate"]["status"], "satisfied")
            self.assertEqual(done_payload["closeout_gate"]["required"], [])

            coverage_result = run_cli(
                "k",
                "--task",
                "thread recovery new family closeout",
                "--route-query",
                "找回之前聊天记录",
                "--route-event-id",
                route_payload["route_event_id"],
                "--surfaced-hits-hash",
                route_payload["surfaced_hits_hash"],
                "--coverage-mode",
                "new_family",
                "--runbook-paths",
                "memory/runbooks/thread-recovery.md",
                "--benchmark-queries",
                "找回之前聊天记录,读取线程记忆",
                "--coverage-evidence",
                "memory/runbooks/thread-recovery.md",
                "--evidence-paths",
                "memory/runbooks/thread-recovery.md",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(coverage_result.returncode, 0, msg=coverage_result.stderr)
            coverage_payload = json.loads(coverage_result.stdout)
            self.assertEqual(coverage_payload["closeout_gate"]["status"], "satisfied")

    def test_checkpoint_adoption_requires_selected_hit_and_keeps_distinct_traces(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_thread_recovery_note(repo_root)

            route_result = run_cli("r", "--task", "找回之前聊天记录", cwd=repo_root, home_root=home_root)
            self.assertEqual(route_result.returncode, 0, msg=route_result.stderr)
            route_payload = json.loads(route_result.stdout)

            missing_selected = run_cli(
                "k",
                "--task",
                "thread recovery adoption missing selected",
                "--route-query",
                "找回之前聊天记录",
                "--route-event-id",
                route_payload["route_event_id"],
                "--surfaced-hits-hash",
                route_payload["surfaced_hits_hash"],
                "--adopted-hit",
                "memory/runbooks/thread-recovery.md",
                "--observed-actions",
                "沿用 thread recovery runbook",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(missing_selected.returncode, 1)
            missing_selected_payload = json.loads(missing_selected.stderr)
            self.assertIn("selected_hit", missing_selected_payload["error"])

            first = run_cli(
                "k",
                "--task",
                "thread recovery repeated adoption",
                "--route-query",
                "找回之前聊天记录",
                "--route-event-id",
                route_payload["route_event_id"],
                "--surfaced-hits-hash",
                route_payload["surfaced_hits_hash"],
                "--selected-hit",
                "memory/runbooks/thread-recovery.md",
                "--adopted-hit",
                "memory/runbooks/thread-recovery.md",
                "--observed-actions",
                "第一次按 runbook 执行",
                "--evidence-paths",
                "memory/runbooks/thread-recovery.md",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(first.returncode, 0, msg=first.stderr)

            second = run_cli(
                "k",
                "--task",
                "thread recovery repeated adoption",
                "--route-query",
                "找回之前聊天记录",
                "--route-event-id",
                route_payload["route_event_id"],
                "--surfaced-hits-hash",
                route_payload["surfaced_hits_hash"],
                "--selected-hit",
                "memory/runbooks/thread-recovery.md",
                "--adopted-hit",
                "memory/runbooks/thread-recovery.md",
                "--observed-actions",
                "第二次按 runbook 执行",
                "--evidence-paths",
                "memory/runbooks/thread-recovery.md",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(second.returncode, 0, msg=second.stderr)
            second_payload = json.loads(second.stdout)
            self.assertEqual(len(second_payload["retrieval_traces"]), 2)
            self.assertEqual(second_payload["retrieval_traces"][0]["observed_actions"], ["第一次按 runbook 执行"])
            self.assertEqual(second_payload["retrieval_traces"][1]["observed_actions"], ["第二次按 runbook 执行"])

    def test_checkpoint_adoption_rejects_hits_outside_surfaced_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")
            seed_thread_recovery_note(repo_root)

            route_result = run_cli("r", "--task", "找回之前聊天记录", cwd=repo_root, home_root=home_root)
            self.assertEqual(route_result.returncode, 0, msg=route_result.stderr)
            route_payload = json.loads(route_result.stdout)
            surfaced_hits = ",".join(hit["path"] for hit in route_payload["project_hits"])

            bad_selected = run_cli(
                "k",
                "--task",
                "thread recovery bad selected",
                "--route-query",
                "找回之前聊天记录",
                "--route-event-id",
                route_payload["route_event_id"],
                "--surfaced-hits-hash",
                route_payload["surfaced_hits_hash"],
                "--surfaced-hits",
                surfaced_hits,
                "--selected-hit",
                "memory/runbooks/core.md",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(bad_selected.returncode, 1)
            bad_selected_payload = json.loads(bad_selected.stderr)
            self.assertIn("selected_hit must come from surfaced hits", bad_selected_payload["error"])

            bad_adopted = run_cli(
                "k",
                "--task",
                "thread recovery bad adopted",
                "--route-query",
                "找回之前聊天记录",
                "--route-event-id",
                route_payload["route_event_id"],
                "--surfaced-hits-hash",
                route_payload["surfaced_hits_hash"],
                "--surfaced-hits",
                surfaced_hits,
                "--selected-hit",
                "memory/runbooks/thread-recovery.md",
                "--adopted-hit",
                "memory/runbooks/core.md",
                "--observed-actions",
                "沿用 thread recovery runbook",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(bad_adopted.returncode, 1)
            bad_adopted_payload = json.loads(bad_adopted.stderr)
            self.assertIn("adopted_hit must come from surfaced hits", bad_adopted_payload["error"])

    def test_candidate_creation_stays_in_evolution_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            repo_root = workspace / "repo"
            home_root = workspace / "home"
            seed_memory_root(repo_root, repo_type="repo-memory", summary="repo summary", note_title="Repo Route Flow", note_body="repo route flow")
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")

            result = run_cli(
                "p",
                "--task-summary",
                "stabilize route retrieval",
                "--type",
                "skill",
                "--title",
                "Route Retrieval Review Loop",
                "--summary",
                "Turn successful route debugging into a reusable review skill candidate.",
                "--source-paths",
                ".codex/scripts/memory_tool.py,.codex/scripts/codex_memo.py",
                "--related-assets",
                ".codex/scripts/codex_memo.py",
                "--event-ids",
                "evt_demo_01",
                "--validation-mode",
                "shell",
                "--tests-passed",
                "true",
                cwd=repo_root,
                home_root=home_root,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["candidate"]["candidate_type"], "skill")
            self.assertIsNone(payload["learning"])
            candidates_path = repo_root / ".codex" / "evolution" / "procedural-candidates.json"
            self.assertTrue(candidates_path.exists())
            self.assertFalse((repo_root / ".codex" / "memory" / "procedural-candidates.json").exists())

    def test_checkpoint_and_candidate_fail_outside_project_memory_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            outside_root = workspace / "outside"
            outside_root.mkdir(parents=True, exist_ok=True)
            home_root = workspace / "home"
            seed_memory_root(home_root, repo_type="home-memory", summary="home summary", note_title="Home Route Flow", note_body="home route flow")

            checkpoint_result = run_cli("k", "--task", "tmp checkpoint", "--key-facts", "x", cwd=outside_root, home_root=home_root)
            self.assertEqual(checkpoint_result.returncode, 1)
            self.assertIn("project memory layer", checkpoint_result.stderr.lower())
            self.assertFalse((outside_root / ".codex" / "cache" / "memory-state.db").exists())

            candidate_result = run_cli(
                "p",
                "--task-summary",
                "tmp candidate",
                "--type",
                "skill",
                "--title",
                "Tmp",
                "--summary",
                "Tmp summary",
                cwd=outside_root,
                home_root=home_root,
            )
            self.assertEqual(candidate_result.returncode, 1)
            self.assertIn("project memory layer", candidate_result.stderr.lower())
            self.assertFalse((outside_root / ".codex" / "evolution" / "procedural-candidates.json").exists())


if __name__ == "__main__":
    unittest.main()
