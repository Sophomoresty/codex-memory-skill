from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "bootstrap_project_codex.py"


def load_module():
    spec = importlib.util.spec_from_file_location("bootstrap_project_codex", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class BootstrapProjectCodexTests(unittest.TestCase):
    def test_bootstrap_project_codex_creates_project_layer(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "demo-repo"
            repo_root.mkdir(parents=True)
            (repo_root / "README.md").write_text("# Demo\n", encoding="utf-8")

            result = module.bootstrap_project_codex(repo_root)

            self.assertTrue((repo_root / ".codex" / "AGENTS.md").exists())
            self.assertTrue((repo_root / ".codex" / "scripts" / "codex_memo.py").exists())
            self.assertTrue((repo_root / ".codex" / "scripts" / "memory_tool.py").exists())
            self.assertTrue((repo_root / ".codex" / "scripts" / "build_asset_index.py").exists())
            self.assertTrue((repo_root / ".codex" / "scripts" / "lib" / "task_status.py").exists())
            self.assertTrue((repo_root / ".codex" / "scripts" / "lib" / "memory_viewer_governance.py").exists())
            self.assertTrue((repo_root / ".codex" / "scripts" / "lib" / "memory_viewer_route.py").exists())
            self.assertTrue((repo_root / ".codex" / "scripts" / "lib" / "memory_viewer_snapshot.py").exists())
            self.assertTrue((repo_root / ".codex" / "scripts" / "lib" / "procedural_candidates.py").exists())
            self.assertTrue((repo_root / ".codex" / "scripts" / "lib" / "runtime_checkpoint.py").exists())
            self.assertTrue((repo_root / ".codex" / "scripts" / "lib" / "session_archive.py").exists())
            self.assertTrue((repo_root / ".codex" / "scripts" / "lib" / "reuse_learning.py").exists())
            self.assertTrue((repo_root / ".codex" / "scripts" / "lib" / "verifier_sidecar.py").exists())
            self.assertTrue((repo_root / ".codex" / "cache" / "asset-index.json").exists())
            self.assertTrue((repo_root / ".codex" / "memory" / "context.md").exists())
            self.assertEqual(result["asset_index"]["counts"]["scripts"], 21)

    def test_bootstrap_project_codex_updates_existing_agents_without_overwriting_body(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "demo-repo"
            repo_root.mkdir(parents=True)
            agents_path = repo_root / "AGENTS.md"
            agents_path.write_text(
                "# Existing Project Guide\n\n## Notes\n\n- Keep this content.\n",
                encoding="utf-8",
            )

            module.bootstrap_project_codex(repo_root)

            content = agents_path.read_text(encoding="utf-8")
            self.assertIn("先读 `./.codex/AGENTS.md`", content)
            self.assertIn("Keep this content.", content)

    def test_bootstrap_project_codex_is_idempotent_for_root_agents_injection(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "demo-repo"
            repo_root.mkdir(parents=True)
            module.bootstrap_project_codex(repo_root)
            module.bootstrap_project_codex(repo_root)

            agents_path = repo_root / "AGENTS.md"
            content = agents_path.read_text(encoding="utf-8")
            self.assertEqual(content.count("## Codex Project Layer"), 1)


if __name__ == "__main__":
    unittest.main()
