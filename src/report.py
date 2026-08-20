"""Bounded EvolutionOutputV3 validation at the Evolver process boundary."""

from __future__ import annotations

import json
import stat
from pathlib import Path, PurePosixPath
from typing import Any


def _text(value: object, label: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"{label} must be non-blank and at most {max_length} characters")
    return value


def _revision(value: object, label: str, visible_revision_ids: frozenset[str]) -> str:
    revision = _text(value, label, max_length=64)
    if revision not in visible_revision_ids:
        raise ValueError(f"{label} is outside the frozen visible Agent revisions")
    return revision


def _changed_paths(value: object) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= 512:
        raise ValueError("changed_paths must contain between 1 and 512 paths")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("changed_paths entries must be strings")
        relative = PurePosixPath(item)
        if relative.is_absolute() or relative.as_posix() == "." or ".." in relative.parts:
            raise ValueError("changed_paths contains an unsafe path")
        normalized.append(relative.as_posix())
    if len(set(normalized)) != len(normalized):
        raise ValueError("changed_paths cannot contain duplicates")
    if normalized != sorted(normalized):
        raise ValueError("changed_paths must be sorted")
    return normalized


def validate_evolution_output(
    path: Path,
    *,
    active_revision_id: str,
    visible_revision_ids: frozenset[str],
    historical_revision_ids: frozenset[str],
    max_bytes: int,
) -> dict[str, Any]:
    """Validate the Agent-authored tagged proposal before Runtime revalidates it."""
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise ValueError("Agent did not produce EvolutionOutputV3") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("Evolution output must be a regular file")
    if metadata.st_size > max_bytes:
        raise ValueError("Evolution output exceeds its byte limit")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("Evolution output must be a JSON object")
    if value.get("schema_version") != 3:
        raise ValueError("Evolution output schema_version must be 3")
    proposal_type = value.get("proposal_type")
    common = {"schema_version", "proposal_type", "hypothesis", "expected_effect"}
    _text(value.get("hypothesis"), "hypothesis", max_length=4000)
    _text(value.get("expected_effect"), "expected_effect", max_length=4000)
    if proposal_type == "reuse":
        if set(value) != common | {"candidate_revision_id"}:
            raise ValueError("reuse output fields are invalid")
        candidate = _revision(
            value["candidate_revision_id"], "candidate_revision_id", visible_revision_ids
        )
        if candidate == active_revision_id:
            raise ValueError("reuse cannot select the current Active revision")
        if candidate not in historical_revision_ids:
            raise ValueError("reuse must select completed Lineage history")
    elif proposal_type in {"evolved", "evolve_from_history"}:
        if set(value) != common | {"base_revision_id", "changed_paths"}:
            raise ValueError(f"{proposal_type} output fields are invalid")
        base = _revision(value["base_revision_id"], "base_revision_id", visible_revision_ids)
        if proposal_type == "evolved" and base != active_revision_id:
            raise ValueError("evolved must use the current Active revision as its base")
        if proposal_type == "evolve_from_history" and base == active_revision_id:
            raise ValueError("evolve_from_history must use a historical revision as its base")
        if proposal_type == "evolve_from_history" and base not in historical_revision_ids:
            raise ValueError("evolve_from_history must select completed Lineage history")
        _changed_paths(value["changed_paths"])
    else:
        raise ValueError("proposal_type must be evolved, reuse, or evolve_from_history")
    return value
