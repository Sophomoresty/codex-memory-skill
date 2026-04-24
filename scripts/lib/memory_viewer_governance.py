from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


LIB_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = LIB_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import codex_memo
import memory_tool as mt


def _benchmark_coverage_gaps(repo_root: Path) -> list[dict[str, Any]]:
    benchmark_path = repo_root / ".codex" / "memory" / "benchmark-cases.json"
    if not benchmark_path.exists():
        return [{"path": "memory/benchmark-cases.json", "reason": "missing"}]
    try:
        payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [{"path": "memory/benchmark-cases.json", "reason": "invalid_json"}]
    cases = payload.get("cases", []) if isinstance(payload, dict) else []
    if not isinstance(cases, list) or not cases:
        return [{"path": "memory/benchmark-cases.json", "reason": "empty_cases"}]
    return []


def build_governance_panel(repo_root: Path, stale_days: int = 45) -> dict[str, Any]:
    hygiene_payload = mt.command_hygiene(repo_root, stale_days=stale_days)
    governance_summary = codex_memo.build_governance_summary(repo_root)
    stale_notes = [
        issue
        for issue in hygiene_payload.get("issues", [])
        if isinstance(issue, dict) and issue.get("type") == "stale_active_note"
    ]
    missing_aliases = [
        {"path": path}
        for path in governance_summary.get("metadata_gaps", {}).get("missing_aliases", [])
    ]
    return {
        "stale_notes": stale_notes,
        "missing_aliases": missing_aliases,
        "missing_benchmark_coverage": _benchmark_coverage_gaps(repo_root),
        "orphan_like_assets": [],
        "reference_only_risks": [],
    }
