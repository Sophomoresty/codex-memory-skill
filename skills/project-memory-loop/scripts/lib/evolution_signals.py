from __future__ import annotations

import hashlib
import re
from typing import Iterable


_SIGNAL_PATTERN = re.compile(r'[^a-z0-9]+')


def normalize_signal(value: str) -> str:
    cleaned = _SIGNAL_PATTERN.sub('_', str(value or '').strip().lower()).strip('_')
    if not cleaned:
        raise ValueError('signal must not be empty after normalization')
    return cleaned


def normalize_signals(values: Iterable[str]) -> list[str]:
    unique = sorted({normalize_signal(value) for value in values if str(value or '').strip()})
    if not unique:
        raise ValueError('at least one signal is required')
    return unique


def parse_csv_signals(raw: str) -> list[str]:
    return normalize_signals(part for part in str(raw or '').split(','))


def make_signal_signature(signals: Iterable[str]) -> str:
    return '|'.join(normalize_signals(signals))


def make_task_fingerprint(task_summary: str, signals: Iterable[str], strategy_gene_id: str | None = None) -> str:
    payload = '||'.join([
        str(task_summary or '').strip(),
        make_signal_signature(signals),
        str(strategy_gene_id or '').strip(),
    ])
    return 'sha256:' + hashlib.sha256(payload.encode('utf-8')).hexdigest()


def parse_bool(raw: str | bool | None, default: bool = False) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    lowered = str(raw).strip().lower()
    if lowered in {'1', 'true', 'yes', 'y', 'on'}:
        return True
    if lowered in {'0', 'false', 'no', 'n', 'off'}:
        return False
    raise ValueError(f'invalid boolean value: {raw}')
