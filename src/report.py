"""Bounded EvolutionOutput validation at the Evolver process boundary."""

from __future__ import annotations

import json
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any


class EvolutionOutputContractError(ValueError):
    """The Agent's evolution output violates the published contract.

    Every message is composed here from field names and indices alone, so the
    outer process may surface it verbatim without leaking Agent content.
    """

    def __init__(self, detail: str, *, field: str = "request") -> None:
        super().__init__(detail)
        self.field = field


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
        standard_source = (
            len(parts) >= 3
            and parts[0] == "input"
            and parts[1] in {"agents", "evidence"}
            and parts[2].startswith("agent-v")
            and parts[2][7:].isdigit()
            and (parts[1] != "evidence" or (len(parts) >= 4 and parts[3] == "resources"))
        )
        reference_source = (
            len(parts) >= 6
            and parts[:2] == ("input", "references")
            and re.fullmatch(r"[a-z][a-z0-9-]{0,63}", parts[2]) is not None
            and parts[3] in {"agents", "evidence"}
            and parts[4].startswith("agent-v")
            and parts[4][7:].isdigit()
            and (
                (parts[3] == "agents" and parts[5] == "source")
                or (parts[3] == "evidence" and parts[5] == "resources")
            )
        )
        if (
            relative.as_posix() != item
            or ".." in parts
            or "\\" in item
            or "\x00" in item
            or not (standard_source or reference_source)
        ):
            raise ValueError(
                f"{label} must be canonical and under input/agents/agent-vN "
                "or input/evidence/agent-vN/resources, or under a manifest-declared "
                "input/references/NAME Source/Resources path"
            )
        paths.append(item)
    if paths != sorted(set(paths)):
        raise ValueError("contributing_paths must be sorted and cannot contain duplicates")
    return paths


def validate_contribution_sources(
    workspace: Path,
    paths: list[str],
    visible_agents: list[dict[str, Any]],
    references: list[dict[str, Any]],
) -> None:
    """Validate actual referenced files independently of the claimed base."""
    for index, relative in enumerate(paths):
        label = f"contributing_paths[{index}]"
        path = PurePosixPath(relative)
        reference = next(
            (
                item
                for item in references
                if path.is_relative_to(PurePosixPath(str(item.get("path", ""))))
            ),
            None,
        )
        if reference is not None:
            root = PurePosixPath(str(reference["path"]))
            relative_parts = path.relative_to(root).parts
            eligible = (
                len(relative_parts) >= 3
                and relative_parts[0] in {"agents", "evidence"}
                and relative_parts[1].startswith("agent-v")
                and relative_parts[1][7:].isdigit()
                and (
                    (relative_parts[0] == "agents" and relative_parts[2] == "source")
                    or (
                        relative_parts[0] == "evidence"
                        and relative_parts[2] == "resources"
                    )
                )
            )
            if not eligible:
                raise ValueError(f"{label} is outside eligible reference Source/Resources")
            current = workspace
            try:
                for part in path.parts:
                    current = current / part
                    metadata = current.lstat()
                    if stat.S_ISLNK(metadata.st_mode):
                        raise ValueError(f"{label} cannot traverse a symbolic link")
            except FileNotFoundError as error:
                raise ValueError(f"{label} does not exist") from error
            continue
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
    if "suggested_directions" in value:
        raise EvolutionOutputContractError(
            "suggested_directions is no longer supported. Remove this field; record "
            "task-independent Agent corrections in Candidate Prompts, Skills, Tools, "
            "implementation, or workflow; do not steer a future Kernel Direction",
            field="suggested_directions",
        )
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
