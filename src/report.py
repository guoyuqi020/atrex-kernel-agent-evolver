"""Bounded EvolutionOutput validation at the Evolver process boundary."""

from __future__ import annotations

import json
import stat
from pathlib import Path, PurePosixPath
from typing import Any


class EvolutionOutputContractError(ValueError):
    """The Agent's evolution output violates the published contract.

    Every message is composed here from field names and indices alone, so the
    outer process may surface it verbatim without leaking Agent content.
    """


EVOLUTION_OUTPUT_FIELDS = frozenset(
    {
        "proposal_type",
        "kernel_agent_revision_id",
        "hypothesis",
        "expected_effect",
        "changed_paths",
        "contributing_revision_ids",
        "unimplemented_capabilities",
    }
)


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
    if not isinstance(value, list) or len(value) > 512:
        raise ValueError("changed_paths must be an array with at most 512 paths")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("changed_paths entries must be strings")
        relative = PurePosixPath(item)
        if relative.is_absolute() or relative.as_posix() == "." or ".." in relative.parts:
            raise ValueError("changed_paths contains an unsafe Source-root-relative path")
        normalized.append(relative.as_posix())
    if len(set(normalized)) != len(normalized):
        raise ValueError("changed_paths cannot contain duplicates")
    if normalized != sorted(normalized):
        raise ValueError("changed_paths must be sorted")
    return normalized


def _contributing_revision_ids(
    value: object,
    *,
    source_reference: str,
    active_revision_id: str,
    visible_revision_ids: frozenset[str],
    historical_revision_ids: frozenset[str],
) -> list[str]:
    if not isinstance(value, list) or len(value) > 64:
        raise ValueError("contributing_revision_ids must be an array with at most 64 entries")
    creditable = historical_revision_ids | {active_revision_id}
    normalized: list[str] = []
    for index, item in enumerate(value):
        revision = _revision(
            item,
            f"contributing_revision_ids[{index}]",
            visible_revision_ids,
        )
        if revision == source_reference:
            raise ValueError(
                f"contributing_revision_ids[{index}] repeats the selected Source base"
            )
        if revision not in creditable:
            raise ValueError(
                f"contributing_revision_ids[{index}] must name completed Lineage history"
            )
        normalized.append(revision)
    if len(set(normalized)) != len(normalized):
        raise ValueError("contributing_revision_ids cannot contain duplicates")
    if normalized != sorted(normalized):
        raise ValueError("contributing_revision_ids must be sorted")
    return normalized


def _unimplemented_capabilities(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 64:
        raise ValueError("unimplemented_capabilities must be an array with at most 64 entries")
    validated: list[dict[str, str]] = []
    fields = {"capability", "expected_benefit", "reason_unimplemented"}
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != fields:
            raise ValueError(f"unimplemented_capabilities[{index}] fields are invalid")
        validated.append(
            {
                "capability": _text(
                    item.get("capability"),
                    f"unimplemented_capabilities[{index}].capability",
                    max_length=2000,
                ),
                "expected_benefit": _text(
                    item.get("expected_benefit"),
                    f"unimplemented_capabilities[{index}].expected_benefit",
                    max_length=2000,
                ),
                "reason_unimplemented": _text(
                    item.get("reason_unimplemented"),
                    f"unimplemented_capabilities[{index}].reason_unimplemented",
                    max_length=2000,
                ),
            }
        )
    return validated


def _validated_output(
    path: Path,
    *,
    active_revision_id: str,
    visible_revision_ids: frozenset[str],
    historical_revision_ids: frozenset[str],
    max_bytes: int,
) -> dict[str, Any]:
    """Apply every EvolutionOutput rule, raising a bare ValueError per violation."""
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise ValueError("Agent did not produce EvolutionOutput") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("Evolution output must be a regular file")
    if metadata.st_size > max_bytes:
        raise ValueError("Evolution output exceeds its byte limit")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("Evolution output must be a JSON object")
    proposal_type = value.get("proposal_type")
    if set(value) != EVOLUTION_OUTPUT_FIELDS:
        raise ValueError("Evolution output fields are invalid")
    _text(value.get("hypothesis"), "hypothesis", max_length=4000)
    _text(value.get("expected_effect"), "expected_effect", max_length=4000)
    _unimplemented_capabilities(value["unimplemented_capabilities"])
    source_reference = _revision(
        value["kernel_agent_revision_id"],
        "kernel_agent_revision_id",
        visible_revision_ids,
    )
    changed_paths = _changed_paths(value["changed_paths"])
    contributing = _contributing_revision_ids(
        value["contributing_revision_ids"],
        source_reference=source_reference,
        active_revision_id=active_revision_id,
        visible_revision_ids=visible_revision_ids,
        historical_revision_ids=historical_revision_ids,
    )
    if proposal_type == "reuse":
        if source_reference == active_revision_id:
            raise ValueError("reuse cannot select the current Active revision")
        if source_reference not in historical_revision_ids:
            raise ValueError("reuse must select completed Lineage history")
        if changed_paths:
            raise ValueError("reuse requires changed_paths to be empty")
        if contributing:
            raise ValueError("reuse requires contributing_revision_ids to be empty")
    elif proposal_type in {"evolved", "evolve_from_history"}:
        if proposal_type == "evolved" and source_reference != active_revision_id:
            raise ValueError("evolved must use the current Active Source revision")
        if proposal_type == "evolve_from_history" and source_reference == active_revision_id:
            raise ValueError("evolve_from_history must use a historical Source revision")
        if (
            proposal_type == "evolve_from_history"
            and source_reference not in historical_revision_ids
        ):
            raise ValueError("evolve_from_history must select completed Lineage history")
    else:
        raise ValueError("proposal_type must be evolved, reuse, or evolve_from_history")
    return value


def validate_evolution_output(
    path: Path,
    *,
    active_revision_id: str,
    visible_revision_ids: frozenset[str],
    historical_revision_ids: frozenset[str],
    max_bytes: int,
) -> dict[str, Any]:
    """Validate the Agent-authored tagged proposal before Runtime revalidates it.

    Every violation carries the offending field so the outer process can tell the
    Agent what to correct instead of reporting only an exception type.
    """
    try:
        return _validated_output(
            path,
            active_revision_id=active_revision_id,
            visible_revision_ids=visible_revision_ids,
            historical_revision_ids=historical_revision_ids,
            max_bytes=max_bytes,
        )
    except EvolutionOutputContractError:
        raise
    except ValueError as error:
        raise EvolutionOutputContractError(str(error)) from error
