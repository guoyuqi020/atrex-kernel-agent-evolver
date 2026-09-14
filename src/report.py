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
        "contributing_paths",
        "unimplemented_capabilities",
    }
)
OPTIONAL_EVOLUTION_OUTPUT_FIELDS = frozenset({"suggested_directions"})


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
            raise ValueError("changed_paths contains an unsafe Bundle-root-relative path")
        normalized.append(relative.as_posix())
    if len(set(normalized)) != len(normalized):
        raise ValueError("changed_paths cannot contain duplicates")
    if normalized != sorted(normalized):
        raise ValueError("changed_paths must be sorted")
    return normalized


def _contributing_paths(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 64:
        raise ValueError("contributing_paths must be an array with at most 64 paths")
    paths: list[str] = []
    for index, item in enumerate(value):
        label = f"contributing_paths[{index}]"
        if not isinstance(item, str) or not item or len(item) > 1000:
            raise ValueError(f"{label} must be a nonempty path of at most 1000 characters")
        relative = PurePosixPath(item)
        parts = relative.parts
        if (
            relative.as_posix() != item
            or ".." in parts
            or "\\" in item
            or "\x00" in item
            or len(parts) < 3
            or parts[0] != "input"
            or parts[1] not in {"agents", "evidence"}
            or not parts[2].startswith("agent-v")
            or not parts[2][7:].isdigit()
            or (parts[1] == "evidence" and (len(parts) < 4 or parts[3] != "resources"))
        ):
            raise ValueError(
                f"{label} must be canonical and under input/agents/agent-vN "
                "or input/evidence/agent-vN/resources"
            )
        paths.append(item)
    if paths != sorted(set(paths)):
        raise ValueError("contributing_paths must be sorted and cannot contain duplicates")
    return paths


def validate_contribution_sources(
    workspace: Path,
    paths: list[str],
    visible_agents: list[dict[str, Any]],
) -> None:
    """Validate actual referenced files independently of the claimed base."""
    for index, relative in enumerate(paths):
        label = f"contributing_paths[{index}]"
        path = PurePosixPath(relative)
        owner = next(
            (
                item
                for item in visible_agents
                if any(
                    path.is_relative_to(PurePosixPath(str(item[key])))
                    for key in ("path", "resources_path")
                )
            ),
            None,
        )
        if owner is None or owner["relationship"] == "current_epoch_challenger":
            raise ValueError(
                f"{label} must reference eligible completed history or Parent resources"
            )
        current = workspace
        try:
            for part in path.parts:
                current = current / part
                mode = current.lstat().st_mode
                if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                    raise ValueError(f"{label} cannot traverse links or special files")
            for child in current.rglob("*") if current.is_dir() else ():
                mode = child.lstat().st_mode
                if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                    raise ValueError(f"{label} contains a link or special file")
        except OSError as error:
            raise ValueError(
                f"{label} does not exist or is not readable; use a visible path"
            ) from error


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


def _suggested_directions(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 8:
        raise ValueError("suggested_directions must be an array with at most 8 entries")
    required = {
        "name", "hypothesis", "rationale", "plan", "success_criteria",
        "stop_conditions",
    }
    optional = {
        "relationship", "derived_from_direction_ids", "derived_from_experiment_ids",
        "supersedes_direction_id",
    }
    for index, proposal in enumerate(value):
        label = f"suggested_directions[{index}]"
        if (
            not isinstance(proposal, dict)
            or not required <= set(proposal)
            or set(proposal) - required - optional
        ):
            raise ValueError(f"{label} fields are invalid")
        for field, maximum in (
            ("name", 200), ("hypothesis", 2000), ("rationale", 2000),
            ("success_criteria", 1000), ("stop_conditions", 1000),
        ):
            _text(proposal[field], f"{label}.{field}", max_length=maximum)
        plan = proposal["plan"]
        if not isinstance(plan, list) or not 1 <= len(plan) <= 8:
            raise ValueError(f"{label}.plan requires 1-8 steps")
        for step in plan:
            _text(step, f"{label}.plan step", max_length=1000)
        relationship = proposal.get("relationship")
        if relationship is not None and relationship not in {
            "retry", "refinement", "reimplementation", "correction", "port", "combination",
            "adoption",
        }:
            raise ValueError(f"{label}.relationship is invalid")
        for field, prefix in (
            ("derived_from_direction_ids", "direction_"),
            ("derived_from_experiment_ids", "experiment_"),
        ):
            ids = proposal.get(field, [])
            if not isinstance(ids, list) or len(ids) > 32 or any(
                not isinstance(item, str)
                or not item.startswith(prefix)
                or len(item) != len(prefix) + 32
                or any(char not in "0123456789abcdef" for char in item[len(prefix):])
                for item in ids
            ) or len(set(ids)) != len(ids):
                raise ValueError(f"{label}.{field} must contain unique valid IDs")
        supersedes = proposal.get("supersedes_direction_id")
        if supersedes is not None and (
            not isinstance(supersedes, str) or not supersedes.startswith("direction_")
            or len(supersedes) != 42
            or any(char not in "0123456789abcdef" for char in supersedes[10:])
        ):
            raise ValueError(f"{label}.supersedes_direction_id is invalid")
        parents = proposal.get("derived_from_direction_ids", [])
        experiments = proposal.get("derived_from_experiment_ids", [])
        if (relationship is None) != (not parents and not experiments):
            raise ValueError(f"{label}.relationship disagrees with ancestry")
        if relationship == "combination" and len(parents) + len(experiments) < 2:
            raise ValueError(f"{label}.combination requires at least two parents")
        if supersedes is not None and (relationship != "correction" or supersedes not in parents):
            raise ValueError(f"{label}.supersedes_direction_id requires a correction parent")
        if relationship == "adoption" and (len(parents) != 1 or experiments or supersedes):
            raise ValueError(f"{label}.adoption requires one suggested parent")
    return value


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
    if not set(value) >= EVOLUTION_OUTPUT_FIELDS or (
        set(value) - EVOLUTION_OUTPUT_FIELDS - OPTIONAL_EVOLUTION_OUTPUT_FIELDS
    ):
        raise ValueError("Evolution output fields are invalid")
    _text(value.get("hypothesis"), "hypothesis", max_length=4000)
    _text(value.get("expected_effect"), "expected_effect", max_length=4000)
    _unimplemented_capabilities(value["unimplemented_capabilities"])
    if "suggested_directions" in value:
        _suggested_directions(value["suggested_directions"])
    source_reference = _revision(
        value["kernel_agent_revision_id"],
        "kernel_agent_revision_id",
        visible_revision_ids,
    )
    changed_paths = _changed_paths(value["changed_paths"])
    contributing = _contributing_paths(value["contributing_paths"])
    if proposal_type == "no_change":
        if source_reference != active_revision_id:
            raise ValueError("no_change must name the current Active revision")
        if changed_paths or contributing:
            raise ValueError("no_change requires empty changed_paths and contributing_paths")
    elif proposal_type == "reuse":
        if source_reference == active_revision_id:
            raise ValueError("reuse cannot select the current Active revision")
        if source_reference not in historical_revision_ids:
            raise ValueError("reuse must select completed Lineage history")
        if changed_paths:
            raise ValueError("reuse requires changed_paths to be empty")
        if contributing:
            raise ValueError("reuse requires contributing_paths to be empty")
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
        raise ValueError(
            "proposal_type must be evolved, reuse, evolve_from_history, or no_change"
        )
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
