from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


STORE_PATH = Path(".codex/cache/memory-state.db")
LEGACY_SEMANTIC_INDEX_PATH = Path(".codex/cache/semantic-index.json")
LEGACY_SEMANTIC_META_PATH = Path(".codex/cache/semantic-index.meta.json")
LEGACY_CHECKPOINTS_PATH = Path(".codex/tasks/runtime-checkpoints.json")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def store_path(repo_root: Path) -> Path:
    return repo_root / STORE_PATH


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return payload


def _normalize_payload(payload: Any, default: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    return dict(default)


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS semantic_entries (
            path TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS semantic_meta (
            singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS checkpoints (
            task_fingerprint TEXT PRIMARY KEY,
            task TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS promotions (
            promotion_id TEXT PRIMARY KEY,
            task_fingerprint TEXT NOT NULL,
            task TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_semantic_entries_updated_at ON semantic_entries(updated_at);
        CREATE INDEX IF NOT EXISTS idx_checkpoints_task ON checkpoints(task);
        CREATE INDEX IF NOT EXISTS idx_checkpoints_updated_at ON checkpoints(updated_at);
        CREATE INDEX IF NOT EXISTS idx_promotions_task_fingerprint ON promotions(task_fingerprint);
        CREATE INDEX IF NOT EXISTS idx_promotions_task ON promotions(task);
        CREATE INDEX IF NOT EXISTS idx_promotions_updated_at ON promotions(updated_at);
        """
    )


def _checkpoint_count(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT COUNT(*) AS count FROM checkpoints").fetchone()
    return int(row[0]) if row else 0


def _semantic_entry_count(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT COUNT(*) AS count FROM semantic_entries").fetchone()
    return int(row[0]) if row else 0


def _migrate_legacy_semantic_index(connection: sqlite3.Connection, repo_root: Path) -> None:
    if _semantic_entry_count(connection) > 0:
        return
    legacy_payload = _normalize_payload(
        _read_json(repo_root / LEGACY_SEMANTIC_INDEX_PATH, {"schema_version": 1, "entries": []}),
        {"schema_version": 1, "entries": []},
    )
    entries = [entry for entry in legacy_payload.get("entries", []) if isinstance(entry, dict)]
    if not entries:
        return
    legacy_meta = _normalize_payload(
        _read_json(repo_root / LEGACY_SEMANTIC_META_PATH, {"mode": "missing"}),
        {"mode": "missing"},
    )
    timestamp = _utcnow()
    for entry in entries:
        path = str(entry.get("path", "")).strip()
        if not path:
            continue
        connection.execute(
            "INSERT OR REPLACE INTO semantic_entries(path, payload_json, updated_at) VALUES (?, ?, ?)",
            (path, json.dumps(entry, ensure_ascii=False), timestamp),
        )
    connection.execute(
        "INSERT OR REPLACE INTO semantic_meta(singleton_id, payload_json, updated_at) VALUES (1, ?, ?)",
        (json.dumps(legacy_meta, ensure_ascii=False), timestamp),
    )


def _migrate_legacy_checkpoints(connection: sqlite3.Connection, repo_root: Path) -> None:
    if _checkpoint_count(connection) > 0:
        return
    legacy_payload = _normalize_payload(
        _read_json(repo_root / LEGACY_CHECKPOINTS_PATH, {"version": 1, "checkpoints": {}}),
        {"version": 1, "checkpoints": {}},
    )
    checkpoints = legacy_payload.get("checkpoints", {})
    if not isinstance(checkpoints, dict) or not checkpoints:
        return
    timestamp = _utcnow()
    for fingerprint, record in checkpoints.items():
        if not isinstance(record, dict):
            continue
        task = str(record.get("task", "")).strip()
        task_fingerprint = str(record.get("task_fingerprint", "")).strip() or str(fingerprint).strip()
        if not task or not task_fingerprint:
            continue
        connection.execute(
            "INSERT OR REPLACE INTO checkpoints(task_fingerprint, task, payload_json, updated_at) VALUES (?, ?, ?, ?)",
            (task_fingerprint, task, json.dumps(record, ensure_ascii=False), timestamp),
        )


@contextmanager
def open_store(repo_root: Path) -> Iterator[sqlite3.Connection]:
    path = store_path(repo_root.resolve())
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30.0)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        _ensure_schema(connection)
        with connection:
            _migrate_legacy_semantic_index(connection, repo_root.resolve())
            _migrate_legacy_checkpoints(connection, repo_root.resolve())
        yield connection
    finally:
        connection.close()


def replace_semantic_index(repo_root: Path, *, entries: list[dict[str, Any]], meta: dict[str, Any]) -> None:
    timestamp = _utcnow()
    valid_paths = {str(entry.get("path", "")).strip() for entry in entries if str(entry.get("path", "")).strip()}
    with open_store(repo_root) as connection, connection:
        connection.execute("DELETE FROM semantic_entries")
        for entry in entries:
            path = str(entry.get("path", "")).strip()
            if not path:
                continue
            connection.execute(
                "INSERT OR REPLACE INTO semantic_entries(path, payload_json, updated_at) VALUES (?, ?, ?)",
                (path, json.dumps(entry, ensure_ascii=False), timestamp),
            )
        if not valid_paths:
            connection.execute("DELETE FROM semantic_entries")
        connection.execute(
            "INSERT OR REPLACE INTO semantic_meta(singleton_id, payload_json, updated_at) VALUES (1, ?, ?)",
            (json.dumps(meta, ensure_ascii=False), timestamp),
        )


def remove_semantic_entry(repo_root: Path, *, path: str) -> bool:
    target_path = str(path).strip()
    if not target_path:
        return False
    entries, meta = read_semantic_index(repo_root)
    filtered_entries = [entry for entry in entries if str(entry.get("path", "")).strip() != target_path]
    if len(filtered_entries) == len(entries):
        return False
    next_meta = dict(meta)
    next_meta["entry_count"] = len(filtered_entries)
    next_meta["generated_at"] = _utcnow()
    next_meta["storage_backend"] = "sqlite"
    replace_semantic_index(repo_root, entries=filtered_entries, meta=next_meta)
    return True


def read_semantic_index(repo_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with open_store(repo_root) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM semantic_entries ORDER BY path ASC"
        ).fetchall()
        meta_row = connection.execute(
            "SELECT payload_json FROM semantic_meta WHERE singleton_id = 1"
        ).fetchone()
    entries = []
    for row in rows:
        try:
            payload = json.loads(str(row["payload_json"]))
        except Exception:
            continue
        if isinstance(payload, dict):
            entries.append(payload)
    if meta_row is None:
        return entries, {"mode": "missing"}
    try:
        meta = json.loads(str(meta_row["payload_json"]))
    except Exception:
        meta = {"mode": "missing"}
    if not isinstance(meta, dict):
        meta = {"mode": "missing"}
    return entries, meta


def read_checkpoint_store(repo_root: Path) -> dict[str, Any]:
    with open_store(repo_root) as connection:
        rows = connection.execute(
            "SELECT task_fingerprint, payload_json FROM checkpoints ORDER BY updated_at ASC"
        ).fetchall()
    checkpoints: dict[str, Any] = {}
    for row in rows:
        try:
            payload = json.loads(str(row["payload_json"]))
        except Exception:
            continue
        if isinstance(payload, dict):
            checkpoints[str(row["task_fingerprint"])] = payload
    return {"version": 2, "backend": "sqlite", "checkpoints": checkpoints}


def read_checkpoint_record(repo_root: Path, fingerprint: str) -> dict[str, Any] | None:
    with open_store(repo_root) as connection:
        row = connection.execute(
            "SELECT payload_json FROM checkpoints WHERE task_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(str(row["payload_json"]))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def upsert_checkpoint_record(repo_root: Path, *, fingerprint: str, task: str, record: dict[str, Any]) -> None:
    timestamp = _utcnow()
    with open_store(repo_root) as connection, connection:
        connection.execute(
            "INSERT OR REPLACE INTO checkpoints(task_fingerprint, task, payload_json, updated_at) VALUES (?, ?, ?, ?)",
            (fingerprint, task, json.dumps(record, ensure_ascii=False), timestamp),
        )


def latest_checkpoint_record(repo_root: Path) -> dict[str, Any] | None:
    with open_store(repo_root) as connection:
        row = connection.execute(
            "SELECT payload_json FROM checkpoints ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(str(row["payload_json"]))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def read_promotion_records(repo_root: Path, *, task_fingerprint: str = "", task: str = "") -> list[dict[str, Any]]:
    query = "SELECT payload_json FROM promotions"
    params: list[str] = []
    where: list[str] = []
    if task_fingerprint.strip():
        where.append("task_fingerprint = ?")
        params.append(task_fingerprint.strip())
    if task.strip():
        where.append("task = ?")
        params.append(task.strip())
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY updated_at ASC"
    with open_store(repo_root) as connection:
        rows = connection.execute(query, tuple(params)).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(str(row["payload_json"]))
        except Exception:
            continue
        if isinstance(payload, dict):
            results.append(payload)
    return results


def read_promotion_record(repo_root: Path, promotion_id: str) -> dict[str, Any] | None:
    with open_store(repo_root) as connection:
        row = connection.execute(
            "SELECT payload_json FROM promotions WHERE promotion_id = ?",
            (promotion_id.strip(),),
        ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(str(row["payload_json"]))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def upsert_promotion_record(
    repo_root: Path,
    *,
    promotion_id: str,
    task_fingerprint: str,
    task: str,
    record: dict[str, Any],
) -> None:
    timestamp = _utcnow()
    with open_store(repo_root) as connection, connection:
        connection.execute(
            "INSERT OR REPLACE INTO promotions(promotion_id, task_fingerprint, task, payload_json, updated_at) VALUES (?, ?, ?, ?, ?)",
            (
                promotion_id.strip(),
                task_fingerprint.strip(),
                task.strip(),
                json.dumps(record, ensure_ascii=False),
                timestamp,
            ),
        )
