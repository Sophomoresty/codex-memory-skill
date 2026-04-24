from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMMAND_PATH = REPO_ROOT / "bin" / "codex-memo"


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


class CodexMemorySmokeTests(unittest.TestCase):
    def test_help(self) -> None:
        result = subprocess.run([str(COMMAND_PATH), "--help"], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("codex-memo", result.stdout)

    def test_bootstrap_and_asset_index(self) -> None:
        with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as home_dir:
            repo_root = Path(repo_dir)
            home_root = Path(home_dir)
            result = run_cli("b", cwd=repo_root, home_root=home_root)
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            asset_result = run_cli("a", cwd=repo_root, home_root=home_root)
            self.assertEqual(asset_result.returncode, 0, msg=asset_result.stderr)
            payload = json.loads(asset_result.stdout)
            self.assertTrue((repo_root / ".codex" / "cache" / "asset-index.json").exists())
            self.assertIn("counts", payload)

    def test_route_can_hit_seeded_runbook(self) -> None:
        with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as home_dir:
            repo_root = Path(repo_dir)
            home_root = Path(home_dir)
            bootstrap = run_cli("b", cwd=repo_root, home_root=home_root)
            self.assertEqual(bootstrap.returncode, 0, msg=bootstrap.stderr)

            note_path = repo_root / ".codex" / "memory" / "runbooks" / "thread-recovery.md"
            write_note(
                note_path,
                textwrap.dedent(
                    """\
                    ---
                    doc_id: runbook-thread-recovery
                    doc_type: runbook
                    title: Thread Recovery
                    status: active
                    scope: repo
                    tags: [memory, recovery]
                    triggers:
                      - restore previous chat history
                    keywords:
                      - thread recovery
                      - chat history recovery
                    aliases:
                      - restore previous chat history
                    canonical: true
                    related: []
                    supersedes: []
                    last_verified: 2026-04-24
                    confidence: high
                    update_policy: merge
                    when_to_read:
                      - before recovering thread history
                    """
                ),
                "Use this runbook to recover previous chat history.",
            )
            sync_result = run_cli("s", cwd=repo_root, home_root=home_root)
            self.assertEqual(sync_result.returncode, 0, msg=sync_result.stderr)
            asset_result = run_cli("a", cwd=repo_root, home_root=home_root)
            self.assertEqual(asset_result.returncode, 0, msg=asset_result.stderr)

            route_result = run_cli("r", "--task", "restore previous chat history", cwd=repo_root, home_root=home_root)
            self.assertEqual(route_result.returncode, 0, msg=route_result.stderr)
            payload = json.loads(route_result.stdout)
            self.assertEqual(
                payload["execution_gate"]["selected_path"],
                "memory/runbooks/thread-recovery.md",
            )


if __name__ == "__main__":
    unittest.main()
