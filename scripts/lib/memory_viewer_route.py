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
import runtime_checkpoint as rc


SUPPORTED_ROUTE_STATES = ["hit", "reference_only", "miss", "missing_closeout"]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _latest_checkpoint(repo_root: Path) -> dict[str, Any]:
    return rc.latest_checkpoint(repo_root)


def build_route_inspector(repo_root: Path, query: str = "") -> dict[str, Any]:
    route_events = _read_jsonl(repo_root / ".codex" / "evolution" / "route-events.jsonl")
    latest_event = route_events[-1] if route_events else {}
    query_input = str(query).strip() or str(latest_event.get("query", "")).strip()
    route_payload: dict[str, Any] = {}
    if query_input:
        route_payload = codex_memo.command_route(repo_root, repo_root, task=query_input, top_k=5, record_event=False)

    checkpoint = _latest_checkpoint(repo_root)
    closeout_gate = codex_memo.build_closeout_gate(checkpoint) if checkpoint else {
        "status": "not_started",
        "required": [],
        "prompt": "当前没有 checkpoint, 暂无 closeout 状态.",
    }
    execution_gate = route_payload.get("execution_gate", {}) if isinstance(route_payload, dict) else {}
    if (
        closeout_gate.get("status") == "not_started"
        and isinstance(execution_gate, dict)
        and str(execution_gate.get("selected_path", "")).strip()
    ):
        closeout_gate = {
            "status": "pending",
            "required": list(execution_gate.get("required_closeout", [])),
            "prompt": "当前 query 已命中 route, 但还没有对应的 closeout evidence.",
        }
    return {
        "query_input": query_input,
        "selected_hit": str(execution_gate.get("selected_path", "")).strip(),
        "lexical_reasons": route_payload.get("lexical_reasons", {}) if isinstance(route_payload, dict) else {},
        "semantic_reasons": route_payload.get("semantic_reasons", {}) if isinstance(route_payload, dict) else {},
        "execution_gate": execution_gate,
        "closeout_gate": closeout_gate,
        "required_closeout": list(execution_gate.get("required_closeout", [])) if isinstance(execution_gate, dict) else [],
        "checkpoint": checkpoint,
        "supported_states": list(SUPPORTED_ROUTE_STATES),
    }
