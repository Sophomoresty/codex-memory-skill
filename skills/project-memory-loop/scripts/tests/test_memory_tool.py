from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "memory_tool.py"


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ['python3', str(SCRIPT_PATH), *args],
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )


def load_module():
    spec = importlib.util.spec_from_file_location('skill_memory_tool', SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def bootstrap_repo(root: Path) -> None:
    memory_root = root / '.codex' / 'memory'
    for relative in ['runbooks', 'postmortems', 'decisions', 'patterns']:
        (memory_root / relative).mkdir(parents=True, exist_ok=True)

    (memory_root / 'registry.md').write_text(textwrap.dedent('''\
        ---
        doc_id: context-memory-registry
        doc_type: registry
        title: Project Memory Registry
        status: active
        scope: repo
        tags: [memory, registry]
        triggers:
          - before opening memory notes
        keywords:
          - registry
        canonical: true
        related: []
        supersedes: []
        last_verified: 2026-03-25
        confidence: high
        update_policy: merge
        when_to_read:
          - before selecting memory notes
        ---

        # Project Memory Registry
        '''), encoding='utf-8')

    (memory_root / 'index.md').write_text(textwrap.dedent('''\
        ---
        doc_id: context-memory-index
        doc_type: index
        title: Project Memory Index
        status: active
        scope: repo
        tags: [memory, index]
        triggers:
          - before reading project memory
        keywords:
          - index
        canonical: true
        related: []
        supersedes: []
        last_verified: 2026-03-25
        confidence: high
        update_policy: merge
        when_to_read:
          - at the start of non-trivial work
        ---

        # Project Memory Index
        '''), encoding='utf-8')

    (memory_root / 'context.md').write_text(textwrap.dedent('''\
        ---
        doc_id: context-repository-baseline
        doc_type: context
        title: Repository Baseline Context
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
        last_verified: 2026-03-25
        confidence: high
        update_policy: merge
        when_to_read:
          - before repository work
        repo_type: 示例仓库
        project_summary: 用于验证 overview 输出
        entrypoints:
          - main.py
        key_dirs:
          - src/
        common_tasks:
          - 项目接管
        must_read:
          - decisions/core-decision.md
          - runbooks/core-runbook.md
        ---

        # Project Context
        '''), encoding='utf-8')

    for relative, content in {
        'runbooks/_template.md': '---\ndoc_id: runbook-template\ndoc_type: runbook\ntitle: Runbook Template\nstatus: active\nscope: repo\ntags: [workflow]\ntriggers:\n  - trigger\nkeywords:\n  - keyword\ncanonical: true\nrelated: []\nsupersedes: []\nlast_verified: YYYY-MM-DD\nconfidence: high\nupdate_policy: merge\nwhen_to_read:\n  - before task\n---\n',
        'postmortems/_template.md': '---\ndoc_id: postmortem-template\ndoc_type: postmortem\ntitle: Postmortem Template\nstatus: active\nscope: repo\ntags: [failure]\ntriggers:\n  - trigger\nkeywords:\n  - keyword\ncanonical: false\nrelated: []\nsupersedes: []\nlast_verified: YYYY-MM-DD\nconfidence: medium\nupdate_policy: merge\nwhen_to_read:\n  - before debug\n---\n',
        'decisions/_template.md': '---\ndoc_id: decision-template\ndoc_type: decision\ntitle: Decision Template\nstatus: active\nscope: repo\ntags: [decision]\ntriggers:\n  - trigger\nkeywords:\n  - keyword\ncanonical: true\nrelated: []\nsupersedes: []\nlast_verified: YYYY-MM-DD\nconfidence: high\nupdate_policy: merge\nwhen_to_read:\n  - before revisit\n---\n',
        'patterns/_template.md': '---\ndoc_id: pattern-template\ndoc_type: pattern\ntitle: Pattern Template\nstatus: active\nscope: repo\ntags: [pattern]\ntriggers:\n  - trigger\nkeywords:\n  - keyword\ncanonical: true\nrelated: []\nsupersedes: []\nlast_verified: YYYY-MM-DD\nconfidence: high\nupdate_policy: merge\nwhen_to_read:\n  - before apply\n---\n',
    }.items():
        (memory_root / relative).write_text(content, encoding='utf-8')


def seed_route_notes(root: Path) -> None:
    bootstrap_repo(root)
    memory_root = root / '.codex' / 'memory'
    (memory_root / 'runbooks' / 'memory-flush-and-hygiene.md').write_text(textwrap.dedent('''\
        ---
        doc_id: runbook-memory-flush-and-hygiene
        doc_type: runbook
        title: 项目记忆收尾与体检流程
        aliases:
          - 写回记忆
        status: active
        scope: repo
        tags: [memory, hygiene]
        triggers:
          - 任务收尾
        keywords:
          - memory
          - flush
          - hygiene
        canonical: true
        related: []
        supersedes: []
        last_verified: 2026-03-27
        confidence: high
        update_policy: merge
        when_to_read:
          - 在任务收尾前
        ---

        # Runbook

        执行 memory flush 与 hygiene.
        '''), encoding='utf-8')

    (memory_root / 'runbooks' / 'thread-recovery.md').write_text(textwrap.dedent('''\
        ---
        doc_id: runbook-thread-recovery
        doc_type: runbook
        title: 线程恢复流程
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
        confidence: high
        update_policy: merge
        when_to_read:
          - 排查线程丢失时
        ---

        # Thread Recovery

        按 thread id 反查历史会话记录, 恢复线程显示.
        '''), encoding='utf-8')


class SkillMemoryToolTests(unittest.TestCase):
    def test_overview_returns_onboarding_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bootstrap_repo(root)
            result = run_cli('overview', '--repo-root', str(root), '--format', 'json')
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload['repo_type'], '示例仓库')
            self.assertEqual(payload['must_read'], ['decisions/core-decision.md', 'runbooks/core-runbook.md'])

    def test_route_returns_matching_runbook(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            seed_route_notes(root)
            result = run_cli('route', '--repo-root', str(root), '--task', '任务收尾 写回记忆', '--top-k', '3', '--format', 'json')
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload['hits'])
            self.assertEqual(payload['hits'][0]['title'], '项目记忆收尾与体检流程')
            self.assertFalse(payload['fallback_context'])

    def test_route_matches_thread_recovery_for_cjk_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            seed_route_notes(root)
            result = run_cli('route', '--repo-root', str(root), '--task', '读取线程记忆', '--top-k', '3', '--format', 'json')
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload['hits'])
            self.assertEqual(payload['hits'][0]['title'], '线程恢复流程')
            self.assertFalse(payload['fallback_context'])

    def test_write_file_force_on_new_path_returns_created(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'new-file.txt'
            status = module.write_file(path, 'hello', force=True)
            self.assertEqual(status, 'created')


if __name__ == '__main__':
    unittest.main()
