from __future__ import annotations

import json
import shutil
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SESSION_CACHE_PATH = Path(".codex/cache/session-assets.json")
ACTIVE_SESSION_ROOT = Path(".codex/sessions")
ARCHIVED_SESSION_ROOT = Path(".codex/archived_sessions")
ACTIVE_SESSION_LIMIT = 24
ARCHIVED_SESSION_LIMIT = 8
SESSION_LIMIT = ACTIVE_SESSION_LIMIT + ARCHIVED_SESSION_LIMIT
MAX_USER_SNIPPETS = 4
MAX_SNIPPET_LENGTH = 160
LONG_MARKDOWN_THRESHOLD = 2000
SNIPPET_HEAD_LIMIT = 2
SNIPPET_TAIL_LIMIT = 2
EXTRACTION_CONFIG_VERSION = 1
SKIP_MARKERS = (
    "AGENTS.md instructions",
    "<INSTRUCTIONS>",
    "<skill>",
    "<permissions instructions>",
    "<collaboration_mode>",
    "<skills_instructions>",
)


def cache_path(repo_root: Path) -> Path:
    return repo_root / SESSION_CACHE_PATH


def archived_root(repo_root: Path) -> Path:
    return repo_root / ARCHIVED_SESSION_ROOT


def active_root(repo_root: Path) -> Path:
    return repo_root / ACTIVE_SESSION_ROOT


def _session_root(repo_root: Path, relative_root: Path) -> Path | None:
    root = repo_root / relative_root
    return root if root.exists() else None


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def invalidate_cache(repo_root: Path) -> None:
    path = cache_path(repo_root)
    if path.exists():
        path.unlink()


def _extraction_config() -> dict[str, Any]:
    return {
        "version": EXTRACTION_CONFIG_VERSION,
        "max_user_snippets": MAX_USER_SNIPPETS,
        "max_snippet_length": MAX_SNIPPET_LENGTH,
        "long_markdown_threshold": LONG_MARKDOWN_THRESHOLD,
        "snippet_head_limit": SNIPPET_HEAD_LIMIT,
        "snippet_tail_limit": SNIPPET_TAIL_LIMIT,
        "skip_markers": list(SKIP_MARKERS),
    }


def _cache_matches(
    cache: dict[str, Any],
    *,
    signatures: list[dict[str, Any]],
    active_limit: int,
    archived_limit: int,
) -> bool:
    if cache.get("version") != 2:
        return False
    if cache.get("active_limit") != active_limit:
        return False
    if cache.get("archived_limit") != archived_limit:
        return False
    if cache.get("extraction_config") != _extraction_config():
        return False
    return cache.get("signatures") == signatures


def _sorted_session_files(root: Path, limit: int) -> list[Path]:
    files = [path for path in root.rglob("*.jsonl") if path.is_file()]
    files.sort(key=lambda item: item.relative_to(root).as_posix(), reverse=True)
    return files[:limit]


def _session_files(
    repo_root: Path,
    active_limit: int = ACTIVE_SESSION_LIMIT,
    archived_limit: int = ARCHIVED_SESSION_LIMIT,
) -> list[Path]:
    files: list[Path] = []
    active_root = _session_root(repo_root, ACTIVE_SESSION_ROOT)
    archived_root = _session_root(repo_root, ARCHIVED_SESSION_ROOT)
    if active_root is not None:
        files.extend(_sorted_session_files(active_root, active_limit))
    if archived_root is not None:
        files.extend(_sorted_session_files(archived_root, archived_limit))
    return files


def latest_active_session_file(repo_root: Path) -> Path | None:
    root = _session_root(repo_root, ACTIVE_SESSION_ROOT)
    if root is None:
        return None
    files = [path for path in root.rglob("*.jsonl") if path.is_file()]
    if not files:
        return None
    files.sort(key=lambda item: item.stat().st_mtime_ns, reverse=True)
    return files[0]


def find_session_file(repo_root: Path, session_id: str, *, include_active: bool = True) -> Path | None:
    normalized = session_id.strip()
    if not normalized:
        return None
    roots = [archived_root(repo_root)]
    if include_active:
        roots.append(active_root(repo_root))
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob(f"{normalized}.jsonl"):
            if path.is_file():
                return path
    return None


def _signature_for(path: Path, repo_root: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": path.relative_to(repo_root).as_posix(),
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }


def _skip_user_text(text: str) -> bool:
    if not text:
        return True
    if any(marker in text for marker in SKIP_MARKERS):
        return True
    if len(text) > LONG_MARKDOWN_THRESHOLD and "##" in text:
        return True
    return False


def _normalize_snippet(text: str) -> str:
    compact = " ".join(text.split())
    return compact[:MAX_SNIPPET_LENGTH].strip()


def _extract_user_snippets(path: Path) -> list[str]:
    head_snippets: list[str] = []
    tail_snippets: deque[str] = deque(maxlen=SNIPPET_TAIL_LIMIT)
    seen: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            try:
                event = json.loads(raw_line)
            except Exception:
                continue
            if event.get("type") != "response_item":
                continue
            payload = event.get("payload", {})
            if payload.get("type") != "message" or payload.get("role") != "user":
                continue
            parts: list[str] = []
            for item in payload.get("content", []):
                if item.get("type") == "input_text":
                    parts.append(str(item.get("text", "")))
            text = "\n".join(parts).strip()
            if _skip_user_text(text):
                continue
            snippet = _normalize_snippet(text)
            if not snippet or snippet in seen:
                continue
            seen.add(snippet)
            if len(head_snippets) < SNIPPET_HEAD_LIMIT:
                head_snippets.append(snippet)
                continue
            tail_snippets.append(snippet)
    snippets: list[str] = []
    for snippet in [*head_snippets, *tail_snippets]:
        if snippet not in snippets:
            snippets.append(snippet)
    return snippets[:MAX_USER_SNIPPETS]


def _extract_message_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in payload.get("content", []):
        item_type = str(item.get("type", "")).strip()
        if item_type in {"input_text", "output_text", "text"}:
            text = str(item.get("text", "")).strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def replay_messages(path: Path, *, max_items: int = 6) -> list[dict[str, str]]:
    entries: deque[dict[str, str]] = deque(maxlen=max_items)
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            try:
                event = json.loads(raw_line)
            except Exception:
                continue
            if event.get("type") != "response_item":
                continue
            payload = event.get("payload", {})
            if payload.get("type") != "message":
                continue
            role = str(payload.get("role", "")).strip()
            if role not in {"user", "assistant"}:
                continue
            text = _extract_message_text(payload)
            if not text:
                continue
            entries.append({"role": role, "text": _normalize_snippet(text)})
    return list(entries)


def _build_asset(repo_root: Path, path: Path) -> dict[str, Any] | None:
    snippets = _extract_user_snippets(path)
    if not snippets:
        return None
    rel_path = path.relative_to(repo_root).as_posix()
    title = snippets[0]
    asset_type = "archived_session" if rel_path.startswith(ARCHIVED_SESSION_ROOT.as_posix()) else "session"
    supporting = "; ".join(snippets[1:])
    description = f"task: {title}"
    if supporting:
        description += f"; supporting: {supporting}"
    return {
        "name": title,
        "path": rel_path,
        "asset_kind": asset_type,
        "asset_type": asset_type,
        "description": description,
        "session_id": path.stem,
    }


def discover_session_assets(
    repo_root: Path,
    active_limit: int = ACTIVE_SESSION_LIMIT,
    archived_limit: int = ARCHIVED_SESSION_LIMIT,
) -> list[dict[str, Any]]:
    repo_root = repo_root.resolve()
    files = _session_files(
        repo_root,
        active_limit=active_limit,
        archived_limit=archived_limit,
    )
    signatures = [_signature_for(path, repo_root) for path in files]
    cache = _read_json(cache_path(repo_root))
    if cache and _cache_matches(
        cache,
        signatures=signatures,
        active_limit=active_limit,
        archived_limit=archived_limit,
    ):
        cached_assets = cache.get("session_assets", [])
        if isinstance(cached_assets, list):
            return cached_assets

    assets = [item for item in (_build_asset(repo_root, path) for path in files) if item is not None]
    payload = {
        "version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "active_limit": active_limit,
        "archived_limit": archived_limit,
        "extraction_config": _extraction_config(),
        "signatures": signatures,
        "session_assets": assets,
    }
    _write_json(cache_path(repo_root), payload)
    return assets


def archive_session(
    repo_root: Path,
    *,
    source_path: Path,
    task: str = "",
    reason: str = "manual",
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    candidate = source_path if source_path.is_absolute() else (repo_root / source_path)
    candidate = candidate.resolve()
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(f"Session file not found: {candidate}")
    if candidate.suffix != ".jsonl":
        raise ValueError("session archive only accepts .jsonl files")
    try:
        candidate.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("session archive source must stay inside repo_root") from exc

    archived_root_path = archived_root(repo_root)
    if candidate.is_relative_to(archived_root_path):
        asset = _build_asset(repo_root, candidate)
        return {
            "archived": False,
            "already_archived": True,
            "task": task.strip(),
            "reason": reason.strip() or "manual",
            "source_path": candidate.relative_to(repo_root).as_posix(),
            "archived_path": candidate.relative_to(repo_root).as_posix(),
            "session_id": candidate.stem,
            "session_asset": asset,
            "replay": replay_session(repo_root, candidate),
        }

    now = datetime.now(timezone.utc)
    target_dir = archived_root_path / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / candidate.name
    if target_path.resolve() != candidate:
        shutil.copy2(candidate, target_path)
    invalidate_cache(repo_root)
    asset = _build_asset(repo_root, target_path)
    return {
        "archived": True,
        "already_archived": False,
        "task": task.strip(),
        "reason": reason.strip() or "manual",
        "source_path": candidate.relative_to(repo_root).as_posix(),
        "archived_path": target_path.relative_to(repo_root).as_posix(),
        "session_id": target_path.stem,
        "session_asset": asset,
        "replay": replay_session(repo_root, target_path),
    }


def replay_session(repo_root: Path, session_path: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    candidate = session_path if session_path.is_absolute() else (repo_root / session_path)
    candidate = candidate.resolve()
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(f"Session file not found: {candidate}")
    messages = replay_messages(candidate)
    return {
        "session_id": candidate.stem,
        "path": candidate.relative_to(repo_root).as_posix(),
        "archived": candidate.is_relative_to(archived_root(repo_root)),
        "snippets": _extract_user_snippets(candidate),
        "messages": messages,
    }
