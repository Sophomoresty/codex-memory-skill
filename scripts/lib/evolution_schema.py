from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from typing import Any


EVENT_STATUS = {'success', 'failed', 'partial'}
CAPSULE_STATUS = {'candidate', 'active', 'shadowed', 'retired'}
GENE_STATUS = {'active', 'inactive'}


class SchemaError(ValueError):
    pass


def _require_mapping(name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaError(f'{name} must be a mapping')
    return deepcopy(value)


def _require_string(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f'{name} must be a non-empty string')
    return value.strip()


def _require_bool(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise SchemaError(f'{name} must be a boolean')
    return value


def _require_number(name: str, value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise SchemaError(f'{name} must be a number')
    value = float(value)
    if value < 0.0 or value > 1.0:
        raise SchemaError(f'{name} must be between 0.0 and 1.0')
    return value


def _require_iso_datetime(name: str, value: Any) -> str:
    raw = _require_string(name, value)
    try:
        datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError as exc:
        raise SchemaError(f'{name} must be an ISO-8601 datetime string') from exc
    return raw


def _require_iso_date(name: str, value: Any) -> str:
    raw = _require_string(name, value)
    try:
        date.fromisoformat(raw)
    except ValueError as exc:
        raise SchemaError(f'{name} must be an ISO date string') from exc
    return raw


def _normalize_string_list(name: str, value: Any) -> list[str]:
    if not isinstance(value, list):
        raise SchemaError(f'{name} must be a list of strings')
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise SchemaError(f'{name} must contain only non-empty strings')
        cleaned = item.strip()
        if cleaned not in normalized:
            normalized.append(cleaned)
    if not normalized:
        raise SchemaError(f'{name} must not be empty')
    return normalized


def validate_event(value: Any) -> dict[str, Any]:
    event = _require_mapping('event', value)
    event['id'] = _require_string('event.id', event.get('id'))
    event['task_summary'] = _require_string('event.task_summary', event.get('task_summary'))
    event['task_fingerprint'] = _require_string('event.task_fingerprint', event.get('task_fingerprint'))
    event['signals'] = _normalize_string_list('event.signals', event.get('signals'))
    event['status'] = _require_string('event.status', event.get('status'))
    if event['status'] not in EVENT_STATUS:
        raise SchemaError(f'event.status must be one of {sorted(EVENT_STATUS)}')
    event['score'] = _require_number('event.score', event.get('score'))
    event['created_at'] = _require_iso_datetime('event.created_at', event.get('created_at'))

    if 'strategy_gene_id' in event and event['strategy_gene_id'] is not None:
        event['strategy_gene_id'] = _require_string('event.strategy_gene_id', event.get('strategy_gene_id'))

    if 'session_fingerprint' in event and event['session_fingerprint'] is not None:
        event['session_fingerprint'] = _require_string('event.session_fingerprint', event.get('session_fingerprint'))

    evidence = event.get('evidence', {})
    if evidence is None:
        evidence = {}
    evidence = _require_mapping('event.evidence', evidence)
    for key in ('tests_passed', 'user_confirmed'):
        if key in evidence:
            evidence[key] = _require_bool(f'event.evidence.{key}', evidence[key])
    if 'files_changed' in evidence:
        if not isinstance(evidence['files_changed'], int) or evidence['files_changed'] < 0:
            raise SchemaError('event.evidence.files_changed must be a non-negative integer')
    if 'validation_mode' in evidence and evidence['validation_mode'] is not None:
        evidence['validation_mode'] = _require_string('event.evidence.validation_mode', evidence['validation_mode'])
    event['evidence'] = evidence

    artifacts = event.get('artifacts', {})
    if artifacts is None:
        artifacts = {}
    artifacts = _require_mapping('event.artifacts', artifacts)
    if 'notes' in artifacts and artifacts['notes'] is not None:
        artifacts['notes'] = _require_string('event.artifacts.notes', artifacts['notes'])
    if 'paths' in artifacts:
        artifacts['paths'] = _normalize_string_list('event.artifacts.paths', artifacts['paths'])
    event['artifacts'] = artifacts
    return event


def validate_gene(value: Any) -> dict[str, Any]:
    gene = _require_mapping('gene', value)
    gene['id'] = _require_string('gene.id', gene.get('id'))
    gene['title'] = _require_string('gene.title', gene.get('title'))
    gene['match_signals'] = _normalize_string_list('gene.match_signals', gene.get('match_signals'))
    gene['instruction_template'] = _require_string('gene.instruction_template', gene.get('instruction_template'))
    gene['guards'] = _normalize_string_list('gene.guards', gene.get('guards', [])) if gene.get('guards') else []
    gene['status'] = gene.get('status', 'active')
    gene['status'] = _require_string('gene.status', gene['status'])
    if gene['status'] not in GENE_STATUS:
        raise SchemaError(f'gene.status must be one of {sorted(GENE_STATUS)}')
    return gene


def validate_capsule(value: Any) -> dict[str, Any]:
    capsule = _require_mapping('capsule', value)
    capsule['id'] = _require_string('capsule.id', capsule.get('id'))
    capsule['source_gene_id'] = _require_string('capsule.source_gene_id', capsule.get('source_gene_id'))
    capsule['signal_signature'] = _require_string('capsule.signal_signature', capsule.get('signal_signature'))
    capsule['rule'] = _require_string('capsule.rule', capsule.get('rule'))
    promotion = _require_mapping('capsule.promotion_evidence', capsule.get('promotion_evidence'))
    for key in ('success_count', 'failure_count', 'distinct_sessions'):
        value = promotion.get(key)
        if not isinstance(value, int) or value < 0:
            raise SchemaError(f'capsule.promotion_evidence.{key} must be a non-negative integer')
    capsule['promotion_evidence'] = promotion
    capsule['status'] = _require_string('capsule.status', capsule.get('status', 'candidate'))
    if capsule['status'] not in CAPSULE_STATUS:
        raise SchemaError(f'capsule.status must be one of {sorted(CAPSULE_STATUS)}')
    capsule['created_at'] = _require_iso_datetime('capsule.created_at', capsule.get('created_at'))
    capsule['last_verified'] = _require_iso_date('capsule.last_verified', capsule.get('last_verified'))
    return capsule


def validate_promotion_state(value: Any) -> dict[str, Any]:
    state = _require_mapping('promotion_state', value)
    version = state.get('version', 1)
    if not isinstance(version, int) or version <= 0:
        raise SchemaError('promotion_state.version must be a positive integer')
    state['version'] = version
    clusters = state.get('clusters', {})
    if not isinstance(clusters, dict):
        raise SchemaError('promotion_state.clusters must be a mapping')
    normalized_clusters: dict[str, dict[str, Any]] = {}
    for key, cluster in clusters.items():
        cluster_key = _require_string('promotion_state.cluster_key', key)
        cluster_value = _require_mapping(f'promotion_state.clusters[{cluster_key}]', cluster)
        for field in ('success_count', 'failure_count', 'partial_count', 'distinct_sessions'):
            if field in cluster_value:
                count = cluster_value[field]
                if not isinstance(count, int) or count < 0:
                    raise SchemaError(f'{field} must be a non-negative integer')
        if 'status' in cluster_value and cluster_value['status'] is not None:
            cluster_value['status'] = _require_string('promotion_state.cluster.status', cluster_value['status'])
        normalized_clusters[cluster_key] = cluster_value
    state['clusters'] = normalized_clusters
    return state
