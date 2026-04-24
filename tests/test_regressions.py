from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
LIB_DIR = SCRIPTS_DIR / "lib"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from llm_semantic_client import SemanticLLMClient


class CodexMemoryRegressionTests(unittest.TestCase):
    def test_rerank_route_uses_local_fallback_without_missing_method(self) -> None:
        client = SemanticLLMClient(REPO_ROOT, force_fake=True)
        payload = client.rerank_route(
            {
                "query": "memory governance hygiene",
                "candidates": [
                    {
                        "path": "memory/runbooks/memory-hygiene-scan-cleanup-and-enrichment.md",
                        "title": "Memory Hygiene",
                        "kind": "memory",
                        "doc_type": "runbook",
                        "asset_type": "",
                        "lexical_score": 2.0,
                        "semantic_score": 0.4,
                        "lexical_reasons": ["keywords:memory, hygiene (+1.00)"],
                        "semantic_reasons": ["intent:governance, hygiene (+0.40)"],
                        "intent": "memory governance hygiene routing aliases keywords",
                        "action_summary": "Scan and clean duplicate or stale memory notes.",
                    }
                ],
            }
        )
        self.assertEqual(payload["selected_path"], "memory/runbooks/memory-hygiene-scan-cleanup-and-enrichment.md")
        self.assertIn(payload["model"], {"local-semantic-rerank", "fake-semantic-client"})

    def test_benchmark_replay_passes_against_bundled_fixture(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/memory_benchmark.py",
                "--repo-root",
                ".",
                "--cases",
                "examples/benchmark-cases.json",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + "\n" + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["summary"]["selected_top1_hits"], payload["case_count"])


if __name__ == "__main__":
    unittest.main()
