"""Bounded EvolutionOutputV2 validation at the Evolver process boundary."""

from __future__ import annotations

import json
import stat
from pathlib import Path, PurePosixPath
from typing import Any


def _text(value: object, label: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"{label} must be non-blank and at most {max_length} characters")
    return value


def validate_evolution_output(
    path: Path,
    *,
    expected_parent_revision_id: str,
    max_bytes: int,
) -> dict[str, Any]:
    """Validate the Agent-authored annotation before Runtime independently revalidates it."""
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise ValueError("Agent did not produce EvolutionOutputV2") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("Evolution output must be a regular file")
    if metadata.st_size > max_bytes:
        raise ValueError("Evolution output exceeds its byte limit")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("Evolution output must be a JSON object")
    expected = {
        "schema_version",
        "parent_revision_id",
        "hypothesis",
        "expected_effect",
        "changed_paths",
    }
    if set(value) != expected or value["schema_version"] != 2:
        raise ValueError("Evolution output fields or schema_version are invalid")
    parent = _text(value["parent_revision_id"], "parent_revision_id", max_length=64)
    if parent != expected_parent_revision_id:
        raise ValueError("Evolution output names a different Parent revision")
    _text(value["hypothesis"], "hypothesis", max_length=4000)
    _text(value["expected_effect"], "expected_effect", max_length=4000)
    changed = value["changed_paths"]
    if not isinstance(changed, list) or not 1 <= len(changed) <= 512:
        raise ValueError("changed_paths must contain between 1 and 512 paths")
    normalized: list[str] = []
    for item in changed:
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
    return value
