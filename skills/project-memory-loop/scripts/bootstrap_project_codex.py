#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_MARKER_START = "<!-- CODEX-PROJECT-LAYER:START -->"
ROOT_MARKER_END = "<!-- CODEX-PROJECT-LAYER:END -->"
CODEX_MARKER_START = "<!-- CODEX-MEMORY-PROTOCOL:START -->"
CODEX_MARKER_END = "<!-- CODEX-MEMORY-PROTOCOL:END -->"

ROOT_AGENTS_BLOCK = """\
## Codex Project Layer

- 处理非琐碎任务前, 先读 `./.codex/AGENTS.md`.
- 新线程首次接手仓库时, 优先执行 `codex-memo ov`, 再读返回的 `context.md` 与 `must_read`.
- 默认先执行 `codex-memo ov`, 读取 `context.md` 与 `must_read`, 再直接开始执行.
- 只有需要命中既有 runbook, project asset, task-doc, 或 session recall 时, 才执行 `codex-memo r --task "<summary>"`.
- 若需要本地 capability 索引, 执行 `codex-memo a`, 先查看 `.codex/cache/asset-index.json` 的 `summary`, 再按需打开完整索引.
"""

CODEX_AGENTS_BLOCK = """\
# Project Memory Agent Instructions

## Entry Protocol

- 项目级记忆统一维护在 `.codex/memory/`.
- 遇到非琐碎任务时, 默认走新入口:
  1. `codex-memo ov`
  2. 读取 overview 返回的 `context.md` 与 `must_read`
  3. 默认直接开始执行
  4. 只有需要命中既有 runbook, project asset, task-doc, 或 session recall 时, 再执行 `codex-memo r --task "<summary>"`
  5. 只继续读取 route 返回的高置信度记忆正文
- `codex-memo r` 默认只使用本地 semantic rerank; 不提供在线 AI rerank 命令面.
- `codex-memo r` 默认只读 `.codex/cache/asset-index.json` 与现有 semantic index, 不现场 rebuild.
- 若 route 无命中或低置信度, 再补读 `.codex/memory/context.md`.
- `registry.md` 与 `index.md` 不作为运行时默认入口, 仅用于 sync-registry, flush, hygiene 与治理.
- 若需要本地 capability 索引, 在非琐碎任务前执行 `codex-memo a`, 先查看 `.codex/cache/asset-index.json` 的 `summary`, 再按需打开完整索引.
- 若本轮修改了项目本地 skill, script, runbook 或 pattern, 收尾前重新执行 `codex-memo a`.
- `.codex/memory/` 不承担任务状态跟踪职责. 若启用了长任务 workflow, 执行状态只放在 `.codex/tasks/<task-id>/`. 单条长动作若使用 `status.json`, 也只作为局部状态.

## Writeback Protocol

- 非琐碎任务结束前, 必须完成一次 memory review, 结果只能是:
  - `create`
  - `update`
  - `merge`
  - `no-op`
- 若需要写回, 优先使用 `codex-memo f ...`.
- 若本轮无需写回, 仍需运行:
  - `codex-memo s`
  - `codex-memo c`
- 面向用户的默认收口保持简短:
  - 只说明实际改动, 当前结果, 以及必要的单句验证结论.
  - 不默认输出 `memory`, `docs`, `资产`, `task-state` 这类治理清单.
  - 只有用户明确要求详细收尾或审计信息时, 再展开这些字段.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap Codex project layer into a repository.")
    parser.add_argument("--repo-root", default=".", help="Repository root. Default: current working directory.")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format.")
    return parser.parse_args()


def _managed_block(start: str, body: str, end: str) -> str:
    return f"{start}\n{body.rstrip()}\n{end}\n"


def upsert_managed_block(path: Path, start: str, body: str, end: str, heading: str | None = None) -> str:
    block = _managed_block(start, body, end)
    if not path.exists():
        content = block if heading is None else f"# {heading}\n\n{block}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return "created"

    current = path.read_text(encoding="utf-8")
    if start in current and end in current:
        before, rest = current.split(start, 1)
        _, after = rest.split(end, 1)
        updated = before + block + after.lstrip("\n")
        path.write_text(updated, encoding="utf-8")
        return "updated"

    separator = "" if current.endswith("\n") else "\n"
    updated = current + separator + "\n" + block
    path.write_text(updated, encoding="utf-8")
    return "appended"


def copy_file(src: Path, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    existed = dst.exists()
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return "updated" if existed else "created"


def run_json_script(script_path: Path, *args: str, allow_returncodes: set[int] | None = None) -> tuple[int, dict[str, Any]]:
    if allow_returncodes is None:
        allow_returncodes = {0}
    result = subprocess.run(
        [sys.executable, str(script_path), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode not in allow_returncodes:
        raise RuntimeError(
            f"Script failed: {script_path.name} rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    try:
        payload = json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from {script_path.name}: {exc}\nstdout:\n{result.stdout}") from exc
    return result.returncode, payload


def bootstrap_project_codex(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    codex_root = repo_root / ".codex"
    scripts_root = codex_root / "scripts"
    lib_root = scripts_root / "lib"

    copied = {
        ".codex/scripts/codex_memo.py": copy_file(SCRIPT_DIR / "codex_memo.py", scripts_root / "codex_memo.py"),
        ".codex/scripts/memory_tool.py": copy_file(SCRIPT_DIR / "memory_tool.py", scripts_root / "memory_tool.py"),
        ".codex/scripts/build_asset_index.py": copy_file(SCRIPT_DIR / "build_asset_index.py", scripts_root / "build_asset_index.py"),
        ".codex/scripts/memory_benchmark.py": copy_file(SCRIPT_DIR / "memory_benchmark.py", scripts_root / "memory_benchmark.py"),
        ".codex/scripts/lib/task_status.py": copy_file(SCRIPT_DIR / "lib" / "task_status.py", lib_root / "task_status.py"),
        ".codex/scripts/lib/evolution_promote.py": copy_file(SCRIPT_DIR / "lib" / "evolution_promote.py", lib_root / "evolution_promote.py"),
        ".codex/scripts/lib/evolution_schema.py": copy_file(SCRIPT_DIR / "lib" / "evolution_schema.py", lib_root / "evolution_schema.py"),
        ".codex/scripts/lib/evolution_signals.py": copy_file(SCRIPT_DIR / "lib" / "evolution_signals.py", lib_root / "evolution_signals.py"),
        ".codex/scripts/lib/evolution_store.py": copy_file(SCRIPT_DIR / "lib" / "evolution_store.py", lib_root / "evolution_store.py"),
        ".codex/scripts/lib/llm_semantic_client.py": copy_file(SCRIPT_DIR / "lib" / "llm_semantic_client.py", lib_root / "llm_semantic_client.py"),
        ".codex/scripts/lib/memory_viewer_governance.py": copy_file(SCRIPT_DIR / "lib" / "memory_viewer_governance.py", lib_root / "memory_viewer_governance.py"),
        ".codex/scripts/lib/memory_viewer_route.py": copy_file(SCRIPT_DIR / "lib" / "memory_viewer_route.py", lib_root / "memory_viewer_route.py"),
        ".codex/scripts/lib/memory_viewer_snapshot.py": copy_file(SCRIPT_DIR / "lib" / "memory_viewer_snapshot.py", lib_root / "memory_viewer_snapshot.py"),
        ".codex/scripts/lib/procedural_candidates.py": copy_file(SCRIPT_DIR / "lib" / "procedural_candidates.py", lib_root / "procedural_candidates.py"),
        ".codex/scripts/lib/query_intel.py": copy_file(SCRIPT_DIR / "lib" / "query_intel.py", lib_root / "query_intel.py"),
        ".codex/scripts/lib/runtime_checkpoint.py": copy_file(SCRIPT_DIR / "lib" / "runtime_checkpoint.py", lib_root / "runtime_checkpoint.py"),
        ".codex/scripts/lib/semantic_store.py": copy_file(SCRIPT_DIR / "lib" / "semantic_store.py", lib_root / "semantic_store.py"),
        ".codex/scripts/lib/session_archive.py": copy_file(SCRIPT_DIR / "lib" / "session_archive.py", lib_root / "session_archive.py"),
        ".codex/scripts/lib/semantic_index.py": copy_file(SCRIPT_DIR / "lib" / "semantic_index.py", lib_root / "semantic_index.py"),
        ".codex/scripts/lib/reuse_learning.py": copy_file(SCRIPT_DIR / "lib" / "reuse_learning.py", lib_root / "reuse_learning.py"),
        ".codex/scripts/lib/verifier_sidecar.py": copy_file(SCRIPT_DIR / "lib" / "verifier_sidecar.py", lib_root / "verifier_sidecar.py"),
    }

    bootstrap_rc, bootstrap_payload = run_json_script(
        scripts_root / "memory_tool.py",
        "bootstrap",
        "--repo-root",
        str(repo_root),
        "--format",
        "json",
        allow_returncodes={0, 1},
    )

    root_agents_status = upsert_managed_block(
        repo_root / "AGENTS.md",
        ROOT_MARKER_START,
        ROOT_AGENTS_BLOCK,
        ROOT_MARKER_END,
        heading="Project Agent Guide",
    )
    codex_agents_status = upsert_managed_block(
        codex_root / "AGENTS.md",
        CODEX_MARKER_START,
        CODEX_AGENTS_BLOCK,
        CODEX_MARKER_END,
        heading=None,
    )

    _, asset_index_payload = run_json_script(
        scripts_root / "build_asset_index.py",
        "--repo-root",
        str(repo_root),
        "--format",
        "json",
        allow_returncodes={0},
    )

    return {
        "repo_root": str(repo_root),
        "copied_scripts": copied,
        "bootstrap_returncode": bootstrap_rc,
        "bootstrap": bootstrap_payload,
        "agents": {
            "root": root_agents_status,
            ".codex/AGENTS.md": codex_agents_status,
        },
        "asset_index": asset_index_payload,
    }


def render_text(payload: dict[str, Any]) -> str:
    counts = payload["asset_index"]["counts"]
    lines = [
        f"repo_root: {payload['repo_root']}",
        f"root_agents: {payload['agents']['root']}",
        f"codex_agents: {payload['agents']['.codex/AGENTS.md']}",
        f"scripts: {payload['copied_scripts']}",
        f"asset_index_counts: {counts}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    payload = bootstrap_project_codex(Path(args.repo_root))
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(payload), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
