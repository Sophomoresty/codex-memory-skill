from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

LIB_DIR = Path(__file__).resolve().parent
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import evolution_schema as schema


class EvolutionStore:
    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root)
        self.codex_dir = self.repo_root / '.codex'
        self.evolution_dir = self.codex_dir / 'evolution'
        self.genes_path = self.evolution_dir / 'genes.json'
        self.events_path = self.evolution_dir / 'events.jsonl'
        self.capsules_path = self.evolution_dir / 'capsules.jsonl'
        self.promotion_state_path = self.evolution_dir / 'promotion_state.json'

    def ensure_layout(self) -> None:
        self.evolution_dir.mkdir(parents=True, exist_ok=True)
        if not self.genes_path.exists():
            self.write_genes([])
        if not self.events_path.exists():
            self.events_path.write_text('', encoding='utf-8')
        if not self.capsules_path.exists():
            self.capsules_path.write_text('', encoding='utf-8')
        if not self.promotion_state_path.exists():
            self.write_promotion_state({'version': 1, 'clusters': {}})

    def _atomic_write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_text(content, encoding='utf-8')
        tmp.replace(path)

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        raw = path.read_text(encoding='utf-8').strip()
        if not raw:
            return default
        return json.loads(raw)

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            entries.append(json.loads(line))
        return entries

    def read_genes(self) -> list[dict[str, Any]]:
        payload = self._read_json(self.genes_path, {'version': 1, 'genes': []})
        genes = payload.get('genes', [])
        return [schema.validate_gene(item) for item in genes]

    def write_genes(self, genes: list[dict[str, Any]]) -> None:
        payload = {'version': 1, 'genes': [schema.validate_gene(item) for item in genes]}
        self._atomic_write_text(self.genes_path, json.dumps(payload, indent=2, ensure_ascii=False) + '\n')

    def read_events(self) -> list[dict[str, Any]]:
        return [schema.validate_event(item) for item in self._read_jsonl(self.events_path)]

    def append_event(self, event: dict[str, Any]) -> dict[str, Any]:
        self.ensure_layout()
        validated = schema.validate_event(event)
        with self.events_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(validated, ensure_ascii=False) + '\n')
        return validated

    def read_capsules(self) -> list[dict[str, Any]]:
        return [schema.validate_capsule(item) for item in self._read_jsonl(self.capsules_path)]

    def write_capsules(self, capsules: list[dict[str, Any]]) -> None:
        lines = [json.dumps(schema.validate_capsule(item), ensure_ascii=False) for item in capsules]
        content = ('\n'.join(lines) + '\n') if lines else ''
        self._atomic_write_text(self.capsules_path, content)

    def read_promotion_state(self) -> dict[str, Any]:
        payload = self._read_json(self.promotion_state_path, {'version': 1, 'clusters': {}})
        return schema.validate_promotion_state(payload)

    def write_promotion_state(self, state: dict[str, Any]) -> None:
        validated = schema.validate_promotion_state(state)
        self._atomic_write_text(self.promotion_state_path, json.dumps(validated, indent=2, ensure_ascii=False) + '\n')
