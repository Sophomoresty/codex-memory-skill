#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LIB_DIR = Path(__file__).resolve().parent / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import session_archive as sa


SCRIPT_EXTENSIONS = {
    ".py",
    ".sh",
    ".ps1",
    ".js",
    ".ts",
    ".mjs",
    ".cjs",
}
EXCLUDED_SCRIPT_DIRS = {"tests", "__pycache__"}
TASK_ASSET_FILENAMES = {"prd.md", "context.md", "plan.md", "summary.md"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build local Codex asset index.")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root. Default: current working directory.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output path. Default: <repo-root>/.codex/cache/asset-index.json",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Console output format. File output is always JSON.",
    )
    return parser.parse_args()


def extract_frontmatter(markdown: str) -> str:
    if not markdown.startswith("---\n"):
        return ""
    end = markdown.find("\n---", 4)
    if end == -1:
        return ""
    return markdown[4:end]


def parse_frontmatter_block(block: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_key: str | None = None

    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        stripped_line = line.lstrip()
        if stripped_line.startswith("- "):
            if current_key is None:
                continue
            item = stripped_line.split("- ", 1)[1].strip()
            data.setdefault(current_key, []).append(item)
            continue

        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key

        if not value:
            data[key] = []
            continue

        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                data[key] = []
            else:
                data[key] = [part.strip().strip("'\"") for part in inner.split(",")]
            continue

        data[key] = value.strip("'\"")

    return data


def relative_to_repo(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def extract_markdown_title(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return path.stem


def extract_markdown_summary(path: Path, *, max_length: int = 220) -> str:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped == "---":
            continue
        if stripped.startswith("#"):
            stripped = stripped.lstrip("#").strip()
        if ":" in stripped and len(stripped.split(":", 1)[0]) < 24 and stripped.split(":", 1)[0].replace("_", "").isalnum():
            continue
        lines.append(stripped)
        if len(" ".join(lines)) >= max_length:
            break
    summary = " ".join(lines)
    return summary[:max_length].strip()


def list_or_empty(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    return []


def route_style_memory_path(path: str) -> str:
    if path.startswith(".codex/memory/"):
        return "memory/" + path[len(".codex/memory/") :]
    return path


def discover_skills(repo_root: Path) -> list[dict[str, Any]]:
    skills_root = repo_root / ".codex" / "skills"
    if not skills_root.exists():
        return []

    entries: list[dict[str, Any]] = []
    for skill_file in sorted(skills_root.glob("*/SKILL.md")):
        skill_dir = skill_file.parent
        frontmatter = parse_frontmatter_block(
            extract_frontmatter(skill_file.read_text(encoding="utf-8"))
        )
        entries.append(
            {
                "name": frontmatter.get("name") or skill_dir.name,
                "path": relative_to_repo(repo_root, skill_file),
                "skill_dir": relative_to_repo(repo_root, skill_dir),
                "description": frontmatter.get("description") or "",
                "paths": list_or_empty(frontmatter.get("paths")),
                "scripts": list_or_empty(frontmatter.get("scripts")),
                "references": list_or_empty(frontmatter.get("references")),
            }
        )
    return entries


def discover_scripts(repo_root: Path) -> list[dict[str, Any]]:
    scripts_root = repo_root / ".codex" / "scripts"
    if not scripts_root.exists():
        return []

    entries: list[dict[str, Any]] = []
    for path in sorted(scripts_root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_SCRIPT_DIRS for part in path.relative_to(scripts_root).parts):
            continue
        if path.suffix == ".pyc":
            continue
        if path.suffix not in SCRIPT_EXTENSIONS:
            continue
        entries.append(
            {
                "name": path.stem,
                "path": relative_to_repo(repo_root, path),
                "language": path.suffix.lstrip("."),
            }
        )
    return entries


def discover_memory_docs(repo_root: Path, category: str) -> list[dict[str, Any]]:
    root = repo_root / ".codex" / "memory" / category
    if not root.exists():
        return []

    entries: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.md")):
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter_block(extract_frontmatter(text))
        entries.append(
            {
                "name": path.stem,
                "path": relative_to_repo(repo_root, path),
                "title": extract_markdown_title(path),
                "keywords": list_or_empty(frontmatter.get("keywords")),
                "triggers": list_or_empty(frontmatter.get("triggers")),
                "aliases": list_or_empty(frontmatter.get("aliases")),
                "summary": extract_markdown_summary(path),
            }
        )
    return entries




def extract_python_comment_frontmatter(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    in_block = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "# ---":
            if in_block:
                break
            in_block = True
            continue
        if not in_block:
            continue
        if not stripped.startswith("#"):
            break
        c = stripped.lstrip("#").strip()
        if not c:
            continue
        if c.startswith("- "):
            item = c.split("- ", 1)[1].strip()
            if data:
                lk = list(data.keys())[-1]
                if isinstance(data[lk], list):
                    data[lk].append(item)
            continue
        if ":" not in c:
            continue
        key, value = c.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not value:
            data[key] = []
            continue
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            data[key] = [part.strip().strip("'\"") for part in inner.split(",")] if inner else []
            continue
        data[key] = value.strip("'\"")
    return data


def extract_python_docstring_summary(path: Path, max_length: int = 220) -> str:
    import ast
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module)):
                doc = ast.get_docstring(node)
                if doc:
                    return doc[:max_length].replace("\n", " ").strip()
    except SyntaxError:
        pass
    return ""


def discover_executables(repo_root: Path) -> list[dict[str, Any]]:
    root = repo_root / ".codex" / "memory" / "executables"
    if not root.exists():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(root.glob("*")):
        if not path.is_file() or path.name.startswith("_"):
            continue
        if path.suffix not in (".py", ".sh", ".js", ".ts"):
            continue
        fm = extract_python_comment_frontmatter(path)
        entries.append({
            "name": path.stem,
            "path": relative_to_repo(repo_root, path),
            "title": str(fm.get("title", path.stem)),
            "keywords": list_or_empty(fm.get("keywords")),
            "triggers": list_or_empty(fm.get("triggers")),
            "aliases": list_or_empty(fm.get("aliases")),
            "summary": str(fm.get("summary", extract_python_docstring_summary(path))),
            "language": path.suffix.lstrip("."),
        })
    return entries


def discover_task_assets(repo_root: Path) -> list[dict[str, Any]]:
    tasks_root = repo_root / ".codex" / "tasks"
    if not tasks_root.exists():
        return []

    entries: list[dict[str, Any]] = []
    task_docs: dict[str, list[str]] = {}
    for path in sorted(tasks_root.glob("*/*")):
        if not path.is_file():
            continue
        if path.name not in TASK_ASSET_FILENAMES:
            continue
        task_docs.setdefault(path.parent.name, []).append(path.stem)

    for path in sorted(tasks_root.glob("*/*")):
        if not path.is_file():
            continue
        if path.name not in TASK_ASSET_FILENAMES:
            continue
        task_id = path.parent.name
        related_docs = [name for name in task_docs.get(task_id, []) if name != path.stem]
        related_docs_text = ", ".join(sorted(related_docs))
        description = f"task {path.stem} for {task_id}; {extract_markdown_summary(path)}"
        if related_docs_text:
            description += f" related task docs: {related_docs_text}"
        entries.append(
            {
                "name": f"{task_id}/{path.name}",
                "path": relative_to_repo(repo_root, path),
                "task_id": task_id,
                "asset_kind": path.suffix.lstrip(".") or path.name,
                "description": description,
            }
        )
    return entries


def discover_context_insights(repo_root: Path) -> list[dict[str, Any]]:
    context_path = repo_root / ".codex" / "memory" / "context.md"
    if not context_path.exists():
        return []

    text = context_path.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter_block(extract_frontmatter(text))
    common_tasks = list_or_empty(frontmatter.get("common_tasks"))
    entrypoints = list_or_empty(frontmatter.get("entrypoints"))
    must_read = list_or_empty(frontmatter.get("must_read"))
    project_summary = str(frontmatter.get("project_summary", "")).strip()

    insights: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_path in must_read:
        normalized = raw_path.strip().lstrip("./")
        if not normalized:
            continue
        pointer = route_style_memory_path(f".codex/memory/{normalized}")
        if pointer in seen:
            continue
        seen.add(pointer)
        title = normalized.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        insights.append(
            {
                "pointer": pointer,
                "kind": "memory",
                "title": title,
                "aliases": [],
                "triggers": common_tasks,
                "keywords": [*entrypoints, *common_tasks],
                "summary": project_summary,
                "source": "context.must_read",
            }
        )
    return insights


def discover_memory_insights(repo_root: Path) -> list[dict[str, Any]]:
    insights: list[dict[str, Any]] = []
    memory_root = repo_root / ".codex" / "memory"
    for category in ["runbooks", "patterns", "decisions"]:
        root = memory_root / category
        if not root.exists():
            continue
        for path in sorted(root.glob("*.md")):
            if path.name.startswith("_"):
                continue
            text = path.read_text(encoding="utf-8")
            frontmatter = parse_frontmatter_block(extract_frontmatter(text))
            if str(frontmatter.get("status", "")).strip() != "active":
                continue
            if str(frontmatter.get("canonical", "")).strip().lower() not in {"true", "yes", "1"}:
                continue
            insights.append(
                {
                    "pointer": route_style_memory_path(relative_to_repo(repo_root, path)),
                    "kind": "memory",
                    "title": frontmatter.get("title") or extract_markdown_title(path),
                    "aliases": list_or_empty(frontmatter.get("aliases")),
                    "triggers": list_or_empty(frontmatter.get("triggers")),
                    "keywords": list_or_empty(frontmatter.get("keywords")),
                    "summary": extract_markdown_summary(path),
                    "source": f"memory.{category[:-1]}",
                }
            )
    return insights


def build_insight_entries(
    *,
    context_insights: list[dict[str, Any]],
    memory_insights: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    by_pointer: dict[str, dict[str, Any]] = {}

    def add(entry: dict[str, Any]) -> None:
        pointer = str(entry.get("pointer", "")).strip()
        if not pointer:
            return
        existing = by_pointer.get(pointer)
        if existing is None:
            by_pointer[pointer] = {
                "pointer": pointer,
                "kind": str(entry.get("kind", "")).strip(),
                "title": str(entry.get("title", "")).strip(),
                "aliases": list(dict.fromkeys(list_or_empty(entry.get("aliases")))),
                "triggers": list(dict.fromkeys(list_or_empty(entry.get("triggers")))),
                "keywords": list(dict.fromkeys(list_or_empty(entry.get("keywords")))),
                "summary": str(entry.get("summary", "")).strip(),
                "source": str(entry.get("source", "")).strip(),
            }
            return
        for field in ["aliases", "triggers", "keywords"]:
            existing[field] = list(
                dict.fromkeys(list_or_empty(existing.get(field)) + list_or_empty(entry.get(field)))
            )
        if not str(existing.get("title", "")).strip():
            existing["title"] = str(entry.get("title", "")).strip()
        if len(str(entry.get("summary", "")).strip()) > len(str(existing.get("summary", "")).strip()):
            existing["summary"] = str(entry.get("summary", "")).strip()
        if not str(existing.get("source", "")).strip():
            existing["source"] = str(entry.get("source", "")).strip()

    for item in context_insights:
        add(item)
    for item in memory_insights:
        add(item)

    for pointer in sorted(by_pointer):
        entries.append(by_pointer[pointer])
    return entries


def build_asset_index(repo_root: Path, summary_limit: int = 5) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    skills = discover_skills(repo_root)
    scripts = discover_scripts(repo_root)
    runbooks = discover_memory_docs(repo_root, "runbooks")
    patterns = discover_memory_docs(repo_root, "patterns")
    executables = discover_executables(repo_root)
    task_assets = discover_task_assets(repo_root)
    session_assets = sa.discover_session_assets(repo_root)
    context_insights = discover_context_insights(repo_root)
    memory_insights = discover_memory_insights(repo_root)
    insight_entries = build_insight_entries(
        context_insights=context_insights,
        memory_insights=memory_insights,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "counts": {
            "skills": len(skills),
            "scripts": len(scripts),
            "task_assets": len(task_assets),
            "session_assets": len(session_assets),
            "runbooks": len(runbooks),
            "patterns": len(patterns),
            "executables": len(executables),
            "insight_entries": len(insight_entries),
        },
        "skills": skills,
        "scripts": scripts,
        "task_assets": task_assets,
        "session_assets": session_assets,
        "summary": {
            "skills": [entry["name"] for entry in skills[:summary_limit]],
            "scripts": [entry["name"] for entry in scripts[:summary_limit]],
            "runbooks": [entry["name"] for entry in runbooks[:summary_limit]],
            "patterns": [entry["name"] for entry in patterns[:summary_limit]],
            "executables": [entry["name"] for entry in executables[:summary_limit]],
            "task_assets": [entry["name"] for entry in task_assets[:summary_limit]],
            "session_assets": [entry["name"] for entry in session_assets[:summary_limit]],
            "insight_entries": [entry["pointer"] for entry in insight_entries[:summary_limit]],
        },
        "memory": {
            "runbooks": runbooks,
            "patterns": patterns,
            "executables": executables,
        },
        "insight_entries": insight_entries,
    }


def asset_index_path(repo_root: Path) -> Path:
    return repo_root.resolve() / ".codex" / "cache" / "asset-index.json"


def read_asset_index(repo_root: Path) -> dict[str, Any] | None:
    path = asset_index_path(repo_root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def write_asset_index(repo_root: Path, output_path: Path | None = None) -> Path:
    repo_root = repo_root.resolve()
    if output_path is None:
        output_path = asset_index_path(repo_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_asset_index(repo_root)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    insight_output = output_path.parent / "insight-index.json"
    insight_output.write_text(
        json.dumps(
            {
                "generated_at": payload["generated_at"],
                "repo_root": payload["repo_root"],
                "count": payload["counts"]["insight_entries"],
                "entries": payload["insight_entries"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output_path


def render_text(payload: dict[str, Any], output_path: Path) -> str:
    counts = payload["counts"]
    lines = [
        f"output: {output_path}",
        f"skills: {counts['skills']}",
        f"scripts: {counts['scripts']}",
        f"task_assets: {counts['task_assets']}",
        f"runbooks: {counts['runbooks']}",
        f"patterns: {counts['patterns']}",
        f"insight_entries: {counts['insight_entries']}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root)
    if not repo_root.exists():
        print(f"Repository root does not exist: {repo_root}", file=sys.stderr)
        return 2

    output_path = Path(args.output) if args.output else None
    written = write_asset_index(repo_root, output_path)
    payload = json.loads(written.read_text(encoding="utf-8"))

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(payload, written), end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
