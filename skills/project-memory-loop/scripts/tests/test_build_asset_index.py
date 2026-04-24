from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "build_asset_index.py"


def load_module(module_name: str = "build_asset_index"):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class BuildAssetIndexTests(unittest.TestCase):
    def test_build_asset_index_includes_summary(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skill_dir = root / ".codex" / "skills" / "demo-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / 'SKILL.md').write_text(
                "---\nname: demo-skill\ndescription: demo\n---\n",
                encoding="utf-8",
            )
            scripts_root = root / ".codex" / "scripts"
            scripts_root.mkdir(parents=True)
            (scripts_root / "tool.py").write_text('print("ok")\n', encoding="utf-8")
            runbooks_root = root / ".codex" / "memory" / "runbooks"
            runbooks_root.mkdir(parents=True)
            (runbooks_root / "demo-runbook.md").write_text("# Demo Runbook\n", encoding="utf-8")

            payload = module.build_asset_index(root, summary_limit=3)

            self.assertIn("summary", payload)
            self.assertEqual(payload["summary"]["skills"], ["demo-skill"])
            self.assertEqual(payload["summary"]["scripts"], ["tool"])
            self.assertEqual(payload["summary"]["runbooks"], ["demo-runbook"])

    def test_discover_executables_does_not_depend_on_canonical_module_name(self) -> None:
        sys.modules.pop("build_asset_index", None)
        module = load_module("custom_build_asset_index")
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            executables_root = root / ".codex" / "memory" / "executables"
            executables_root.mkdir(parents=True)
            (executables_root / "demo_exec.py").write_text(
                "# ---\n"
                "# title: Demo Exec\n"
                "# keywords: [demo, exec]\n"
                "# ---\n"
                "def main():\n"
                "    return 'ok'\n",
                encoding="utf-8",
            )

            entries = module.discover_executables(root)

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["path"], ".codex/memory/executables/demo_exec.py")
            self.assertEqual(entries[0]["keywords"], ["demo", "exec"])


if __name__ == "__main__":
    unittest.main()
