from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


LIB_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = LIB_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import memory_tool as mt
import memory_viewer_governance as mvg
import memory_viewer_route as mvr


DEFAULT_SNAPSHOT_PATH = Path(".codex/cache/memory-viewer-snapshot.json")
DEFAULT_STALE_DAYS = 45
def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return default
    return json.loads(raw)


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


def _parse_date(raw: str) -> date | None:
    cleaned = str(raw).strip()
    if not cleaned:
        return None
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date()
    except ValueError:
        return None


def _short_text(raw: str, limit: int = 180) -> str:
    compact = " ".join(str(raw).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _list_field(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def snapshot_output_path(repo_root: Path) -> Path:
    return repo_root / DEFAULT_SNAPSHOT_PATH


def build_overview_section(
    repo_root: Path,
    *,
    memory_section: dict[str, Any],
    tasks_section: dict[str, Any],
    evolution_section: dict[str, Any],
) -> dict[str, Any]:
    project = mt.command_overview(repo_root, max_must_read=6)
    return {
        "repo_name": project["repo_name"],
        "project_summary": project["project_summary"],
        "must_read": project["must_read"],
        "key_dirs": project["key_dirs"],
        "recent_memory": memory_section["notes"][:5],
        "recent_tasks": tasks_section["tasks"][:5],
        "recent_evolution": evolution_section["recent_events"][:5],
    }


def build_memory_section(repo_root: Path) -> dict[str, Any]:
    notes = mt.scan_memory_notes(repo_root)
    today = date.today()
    items: list[dict[str, Any]] = []
    stale_signals: list[dict[str, Any]] = []
    doc_types: set[str] = set()
    statuses: set[str] = set()
    tags: set[str] = set()

    for note in notes:
        fm = note.frontmatter
        doc_type = str(fm.get("doc_type", "")).strip()
        status = str(fm.get("status", "")).strip()
        aliases = _list_field(fm.get("aliases"))
        note_tags = _list_field(fm.get("tags"))
        tags.update(note_tags)
        if doc_type:
            doc_types.add(doc_type)
        if status:
            statuses.add(status)

        item = {
            "path": note.rel_path,
            "doc_id": str(fm.get("doc_id", "")).strip(),
            "title": str(fm.get("title", "")).strip() or note.path.stem,
            "doc_type": doc_type,
            "status": status,
            "canonical": bool(fm.get("canonical", False)),
            "aliases": aliases,
            "tags": note_tags,
            "triggers": _list_field(fm.get("triggers")),
            "keywords": _list_field(fm.get("keywords")),
            "last_verified": str(fm.get("last_verified", "")).strip(),
            "excerpt": _short_text(note.body),
        }
        items.append(item)

        last_verified = _parse_date(item["last_verified"])
        if status == "active" and last_verified is not None:
            age_days = (today - last_verified).days
            if age_days > DEFAULT_STALE_DAYS:
                stale_signals.append(
                    {
                        "path": item["path"],
                        "title": item["title"],
                        "age_days": age_days,
                    }
                )

    groupings = {
        "by_doc_type": dict(sorted(Counter(item["doc_type"] for item in items if item["doc_type"]).items())),
        "by_status": dict(sorted(Counter(item["status"] for item in items if item["status"]).items())),
    }
    filters = {
        "doc_types": sorted(doc_types),
        "statuses": sorted(statuses),
        "tags": sorted(tags),
    }
    return {
        "notes": items,
        "filters": filters,
        "groupings": groupings,
        "stale_signals": stale_signals,
    }


def _read_task_payload(path: Path) -> dict[str, Any]:
    payload = _read_json(path, {})
    return payload if isinstance(payload, dict) else {}


def _issue_counts(issues: list[dict[str, Any]]) -> dict[str, int]:
    counts = {state: 0 for state in ["todo", "in_progress", "blocked", "done", "skipped"]}
    for issue in issues:
        state = str(issue.get("state", "")).strip()
        if state in counts:
            counts[state] += 1
    counts["total"] = len(issues)
    return counts


def _verify_result(issue: dict[str, Any]) -> str:
    verify = issue.get("verify", {})
    if isinstance(verify, dict):
        return str(verify.get("result", "")).strip()
    return ""


def _gate_status(issues: list[dict[str, Any]]) -> str:
    gate_issues = [issue for issue in issues if str(issue.get("type", "")).strip() == "gate"]
    if not gate_issues:
        return "none"
    if any(_verify_result(issue) in {"failed", "blocked"} for issue in gate_issues):
        return "failed"
    if all(_verify_result(issue) == "passed" for issue in gate_issues):
        return "passed"
    return "incomplete"


def _verify_status(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "none"
    results = [_verify_result(issue) for issue in issues]
    non_empty = [result for result in results if result]
    if not non_empty:
        return "pending"
    if any(result in {"failed", "blocked"} for result in non_empty):
        return "failed"
    if len(non_empty) == len(issues) and all(result == "passed" for result in non_empty):
        return "passed"
    return "partial"


def _current_issue_id(issues: list[dict[str, Any]]) -> str:
    preferred_states = ("in_progress", "blocked", "todo")
    for state in preferred_states:
        for issue in issues:
            if str(issue.get("state", "")).strip() == state:
                return str(issue.get("id", "")).strip()
    for issue in issues:
        issue_id = str(issue.get("id", "")).strip()
        if issue_id:
            return issue_id
    return ""


def build_tasks_section(repo_root: Path) -> dict[str, Any]:
    tasks_root = repo_root / ".codex" / "tasks"
    task_items: list[dict[str, Any]] = []
    for task_root in sorted(tasks_root.iterdir()) if tasks_root.exists() else []:
        if not task_root.is_dir():
            continue
        task_payload = _read_task_payload(task_root / "task.json")
        if not task_payload:
            continue
        issues = task_payload.get("issues", [])
        if not isinstance(issues, list):
            issues = []
        task_items.append(
            {
                "task_id": task_root.name,
                "path": f".codex/tasks/{task_root.name}",
                "status": str(task_payload.get("status", "")).strip(),
                "summary": str(task_payload.get("summary", "")).strip(),
                "issue_counts": _issue_counts(issues),
                "gate_status": _gate_status(issues),
                "verify_status": _verify_status(issues),
                "current_issue_id": _current_issue_id(issues),
            }
        )

    gate_status = "passed"
    if any(item["gate_status"] == "failed" for item in task_items):
        gate_status = "failed"
    elif any(item["gate_status"] == "incomplete" for item in task_items):
        gate_status = "incomplete"

    verify_status = "passed"
    if any(item["verify_status"] == "failed" for item in task_items):
        verify_status = "failed"
    elif any(item["verify_status"] in {"pending", "partial"} for item in task_items):
        verify_status = "partial"

    return {
        "tasks": task_items,
        "issue_counts": {
            "total_tasks": len(task_items),
            "open_tasks": sum(1 for item in task_items if item["status"] != "done"),
        },
        "gate_status": gate_status,
        "verify_status": verify_status,
    }


def build_evolution_section(repo_root: Path) -> dict[str, Any]:
    evolution_root = repo_root / ".codex" / "evolution"
    capsules = _read_jsonl(evolution_root / "capsules.jsonl")
    events = _read_jsonl(evolution_root / "events.jsonl")
    promotion_state = _read_json(evolution_root / "promotion_state.json", {"clusters": {}})
    clusters = promotion_state.get("clusters", {}) if isinstance(promotion_state, dict) else {}
    promotion_states = [
        {"signal_signature": signal_signature, **payload}
        for signal_signature, payload in clusters.items()
        if isinstance(payload, dict)
    ]
    return {
        "capsules": capsules[:50],
        "promotion_states": promotion_states[:50],
        "recent_events": events[:50],
    }


def build_global_search_section(
    memory_section: dict[str, Any],
    tasks_section: dict[str, Any],
    evolution_section: dict[str, Any],
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for item in memory_section["notes"]:
        results.append(
            {
                "title": item["title"],
                "summary": item["excerpt"],
                "target_kind": "memory",
                "target_path": item["path"],
            }
        )
    for item in tasks_section["tasks"]:
        results.append(
            {
                "title": item["task_id"],
                "summary": item["summary"],
                "target_kind": "task",
                "target_path": item["path"],
            }
        )
    for item in evolution_section["capsules"]:
        results.append(
            {
                "title": str(item.get("id", "")).strip(),
                "summary": _short_text(json.dumps(item, ensure_ascii=False)),
                "target_kind": "evolution",
                "target_path": f".codex/evolution/capsules.jsonl#{item.get('id', '')}",
            }
        )
    return {
        "query": "",
        "filters": {"target_kinds": ["memory", "task", "evolution"]},
        "results": results,
        "target_kind": "",
        "target_path": "",
    }


def build_snapshot(repo_root: Path) -> dict[str, Any]:
    memory_section = build_memory_section(repo_root)
    tasks_section = build_tasks_section(repo_root)
    evolution_section = build_evolution_section(repo_root)
    route_inspector = mvr.build_route_inspector(repo_root)
    governance = mvg.build_governance_panel(repo_root)
    global_search = build_global_search_section(memory_section, tasks_section, evolution_section)
    overview = build_overview_section(
        repo_root,
        memory_section=memory_section,
        tasks_section=tasks_section,
        evolution_section=evolution_section,
    )
    return {
        "generated_at": _now_iso(),
        "repo_root": str(repo_root),
        "overview": overview,
        "memory": memory_section,
        "tasks": tasks_section,
        "evolution": evolution_section,
        "route_inspector": route_inspector,
        "governance": governance,
        "global_search": global_search,
    }


def write_snapshot(repo_root: Path, output_path: Path | None = None) -> dict[str, Any]:
    snapshot = build_snapshot(repo_root)
    destination = output_path or snapshot_output_path(repo_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "output_path": str(destination),
        "snapshot": snapshot,
    }
