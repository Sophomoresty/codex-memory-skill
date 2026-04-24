from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


BUNDLE_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "codex_memo.py"
ROOT_SCRIPT_PATH = BUNDLE_SCRIPT_PATH.parents[3] / "scripts" / "codex_memo.py"


def load_bundle_module():
    spec = importlib.util.spec_from_file_location("skill_codex_memo", BUNDLE_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    original_sys_path = list(sys.path)
    try:
        sys.path.insert(0, str(BUNDLE_SCRIPT_PATH.parent))
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_sys_path
    return module


class CodexMemoGuardTests(unittest.TestCase):
    def test_root_codex_memo_matches_skill_bundle_copy(self) -> None:
        self.assertTrue(ROOT_SCRIPT_PATH.exists(), msg=f"Missing root script: {ROOT_SCRIPT_PATH}")
        self.assertTrue(BUNDLE_SCRIPT_PATH.exists(), msg=f"Missing bundle script: {BUNDLE_SCRIPT_PATH}")
        self.assertEqual(
            ROOT_SCRIPT_PATH.read_text(encoding="utf-8"),
            BUNDLE_SCRIPT_PATH.read_text(encoding="utf-8"),
        )

    def test_bundle_execution_gate_contract(self) -> None:
        module = load_bundle_module()

        hit_gate = module.build_execution_gate(
            project_memory_hits=[
                {
                    "path": "memory/runbooks/core.md",
                    "ref": "project:memory/runbooks/core.md",
                    "title": "Core Runbook",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "source": "project",
                }
            ],
            project_hits=[
                {
                    "path": "memory/runbooks/core.md",
                    "ref": "project:memory/runbooks/core.md",
                    "title": "Core Runbook",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "source": "project",
                }
            ],
            merged_hits=[
                {
                    "path": "memory/runbooks/core.md",
                    "ref": "project:memory/runbooks/core.md",
                    "title": "Core Runbook",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "source": "project",
                }
            ],
            project_fallback_context=False,
            fallback_context=False,
        )
        self.assertEqual(hit_gate["state"], "hit")
        self.assertEqual(hit_gate["selected_ref"], "project:memory/runbooks/core.md")
        self.assertEqual(hit_gate["selected_path"], "memory/runbooks/core.md")
        self.assertEqual(hit_gate["selected_kind"], "memory")
        self.assertEqual(hit_gate["selected_source"], "project")
        self.assertEqual(hit_gate["required_closeout"], ["adoption_evidence"])
        self.assertIn("adoption evidence", hit_gate["prompt"])

        ref_gate = module.build_execution_gate(
            project_memory_hits=[],
            project_hits=[
                {
                    "path": ".codex/scripts/codex_memo.py",
                    "ref": "project:.codex/scripts/codex_memo.py",
                    "title": "codex_memo",
                    "kind": "asset",
                    "doc_type": "script",
                    "source": "project",
                }
            ],
            merged_hits=[
                {
                    "path": ".codex/scripts/codex_memo.py",
                    "ref": "project:.codex/scripts/codex_memo.py",
                    "title": "codex_memo",
                    "kind": "asset",
                    "doc_type": "script",
                    "source": "project",
                }
            ],
            project_fallback_context=False,
            fallback_context=False,
        )
        self.assertEqual(ref_gate["state"], "reference_only")

        preferred_runbook_gate = module.build_execution_gate(
            project_memory_hits=[
                {
                    "path": "memory/runbooks/thread-recovery.md",
                    "ref": "project:memory/runbooks/thread-recovery.md",
                    "title": "Thread Recovery",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "source": "project",
                }
            ],
            project_hits=[
                {
                    "path": ".codex/sessions/2026/04/21/demo.jsonl",
                    "ref": "project:.codex/sessions/2026/04/21/demo.jsonl",
                    "title": "session recall note",
                    "kind": "asset",
                    "doc_type": "session",
                    "asset_type": "session",
                    "source": "project",
                }
                ,
                {
                    "path": "memory/runbooks/thread-recovery.md",
                    "ref": "project:memory/runbooks/thread-recovery.md",
                    "title": "Thread Recovery",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "source": "project",
                }
            ],
            merged_hits=[
                {
                    "path": ".codex/sessions/2026/04/21/demo.jsonl",
                    "ref": "project:.codex/sessions/2026/04/21/demo.jsonl",
                    "title": "session recall note",
                    "kind": "asset",
                    "doc_type": "session",
                    "asset_type": "session",
                    "source": "project",
                },
                {
                    "path": "memory/runbooks/thread-recovery.md",
                    "ref": "project:memory/runbooks/thread-recovery.md",
                    "title": "Thread Recovery",
                    "kind": "memory",
                    "doc_type": "runbook",
                    "source": "project",
                },
            ],
            project_fallback_context=False,
            fallback_context=False,
        )
        self.assertEqual(preferred_runbook_gate["state"], "hit")
        self.assertEqual(preferred_runbook_gate["selected_path"], "memory/runbooks/thread-recovery.md")

        miss_gate = module.build_execution_gate(
            project_memory_hits=[],
            project_hits=[],
            merged_hits=[],
            project_fallback_context=False,
            fallback_context=False,
        )
        self.assertEqual(miss_gate["state"], "miss")
        self.assertEqual(
            miss_gate["required_closeout"],
            ["runbook", "benchmark_query", "adoption_evidence", "script_if_needed"],
        )
        self.assertIn("runbook + benchmark query + adopted evidence", miss_gate["prompt"])

    def test_bundle_closeout_gate_contract(self) -> None:
        module = load_bundle_module()

        not_started_gate = module.build_closeout_gate({})
        self.assertEqual(not_started_gate["status"], "not_started")
        self.assertEqual(not_started_gate["required"], [])

        pending_gate = module.build_closeout_gate(
            {"retrieval_traces": [{"selected_hit": "memory/runbooks/core.md", "adopted_hit": "", "evidence_paths": []}]}
        )
        self.assertEqual(pending_gate["status"], "pending")
        self.assertEqual(pending_gate["required"], ["adoption_evidence"])
        self.assertIn("adoption evidence", pending_gate["prompt"])

        satisfied_gate = module.build_closeout_gate(
            {
                "retrieval_traces": [
                    {
                        "selected_hit": "memory/runbooks/core.md",
                        "adopted_hit": "memory/runbooks/core.md",
                        "evidence_paths": ["memory/runbooks/core.md"],
                    }
                ]
            }
        )
        self.assertEqual(satisfied_gate["status"], "satisfied")
        self.assertEqual(satisfied_gate["required"], [])

    def test_bundle_working_memory_prompt_contract(self) -> None:
        module = load_bundle_module()

        prompt = module.build_working_memory_prompt(
            {
                "exists": True,
                "key_facts": ["thread id 可用于恢复会话"],
                "current_invariant": ["优先沿用 thread recovery runbook"],
                "verified_steps": ["route hit thread recovery runbook"],
                "task_assets": ["memory/runbooks/thread-recovery.md"],
                "reused_assets": [],
                "retrieval_traces": [],
            }
        )

        self.assertIn("### [WORKING MEMORY]", prompt)
        self.assertIn("thread id 可用于恢复会话", prompt)
        self.assertIn("优先沿用 thread recovery runbook", prompt)
        self.assertIn("route hit thread recovery runbook", prompt)


if __name__ == "__main__":
    unittest.main()
