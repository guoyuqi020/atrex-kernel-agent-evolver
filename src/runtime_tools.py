#!/usr/bin/env python3
"""Agent-facing local tools for one Evolver session."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from context import validate_adaptive_directories
from report import (
    EVOLUTION_OUTPUT_FIELDS,
    EvolutionOutputContractError,
    validate_contribution_sources,
    validate_evolution_output,
)

_CONTEXT_ENV = "EVOLUTION_REPORT_CONTEXT_JSON"
_IGNORED_DIRECTORIES = frozenset({".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__"})
_IGNORED_FILES = frozenset({".coverage", ".DS_Store"})
_IGNORED_SUFFIXES = frozenset({".pyc", ".pyo"})
_REPORT_FIELDS = EVOLUTION_OUTPUT_FIELDS


class EvolutionReportIssue(ValueError):
    """One or more correctable terminal-report problems."""

    def __init__(self, detail: str, issues: list[dict[str, Any]]) -> None:
        super().__init__(detail)
        self.issues = issues


def _text_schema(*, max_length: int) -> dict[str, Any]:
    return {"type": "string", "minLength": 1, "maxLength": max_length}


def _id_array_schema(prefix: str) -> dict[str, Any]:
    return {
        "type": "array",
        "maxItems": 32,
        "uniqueItems": True,
        "items": {"type": "string", "pattern": rf"^{prefix}_[0-9a-f]{{32}}$"},
    }


def request_schema() -> dict[str, Any]:
    """Return the exact Agent-authored Evolution report contract."""
    capability = {
        "type": "object",
        "additionalProperties": False,
        "required": ["capability", "expected_benefit", "reason_unimplemented"],
        "properties": {
            "capability": _text_schema(max_length=2000),
            "expected_benefit": _text_schema(max_length=2000),
            "reason_unimplemented": _text_schema(max_length=2000),
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_REPORT_FIELDS),
        "properties": {
            "proposal_type": {
                "enum": ["evolved", "evolve_from_history", "reuse", "no_change"],
            },
            "kernel_agent_revision_id": {
                "type": "string",
                "pattern": r"^agentrev_[0-9a-f]{32}$",
            },
            "hypothesis": _text_schema(max_length=4000),
            "expected_effect": _text_schema(max_length=4000),
            "changed_paths": {
                "type": "array",
                "maxItems": 512,
                "uniqueItems": True,
                "items": {"type": "string", "minLength": 1},
            },
            "contributing_paths": {
                "type": "array",
                "maxItems": 64,
                "uniqueItems": True,
                "items": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 1000,
                    "description": (
                        "Canonical workspace-relative path under an eligible Agent Bundle "
                        "or input/evidence/agent-vN/resources; files or directories are allowed."
                    ),
                },
            },
            "unimplemented_capabilities": {
                "type": "array",
                "maxItems": 64,
                "items": capability,
            },
            "suggested_directions": {
                "type": "array",
                "maxItems": 8,
                "description": (
                    "Optional untested lineage Directions, persisted with suggested status "
                    "independently of Agent promotion."
                ),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "name", "hypothesis", "rationale", "plan", "success_criteria",
                        "stop_conditions",
                    ],
                    "properties": {
                        "name": _text_schema(max_length=200),
                        "hypothesis": _text_schema(max_length=2000),
                        "rationale": _text_schema(max_length=2000),
                        "plan": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 8,
                            "items": _text_schema(max_length=1000),
                        },
                        "success_criteria": _text_schema(max_length=1000),
                        "stop_conditions": _text_schema(max_length=1000),
                        "relationship": {
                            "anyOf": [
                                {"enum": [
                                    "retry", "refinement", "reimplementation", "correction",
                                    "port", "combination", "adoption",
                                ]},
                                {"type": "null"},
                            ]
                        },
                        "derived_from_direction_ids": _id_array_schema("direction"),
                        "derived_from_experiment_ids": _id_array_schema("experiment"),
                        "supersedes_direction_id": {
                            "anyOf": [
                                {"type": "string", "pattern": r"^direction_[0-9a-f]{32}$"},
                                {"type": "null"},
                            ]
                        },
                    },
                },
            },
        },
    }


def _safe_workspace_path(workspace: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty workspace-relative path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or relative.as_posix() == "." or ".." in relative.parts:
        raise ValueError(f"{label} must be a safe workspace-relative path")
    result = workspace.joinpath(*relative.parts).resolve(strict=False)
    if not result.is_relative_to(workspace):
        raise ValueError(f"{label} escapes the Evolution workspace")
    return result


def _context(workspace: Path) -> dict[str, Any]:
    raw = os.environ.get(_CONTEXT_ENV)
    if raw is None or not raw or len(raw.encode()) > 256 * 1024:
        raise ValueError(f"{_CONTEXT_ENV} is missing or exceeds its byte limit")
    value: object = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {
        "active_revision_id",
        "visible_agents",
        "candidate",
        "report_path",
        "max_report_bytes",
    }:
        raise ValueError("Evolution report context fields are invalid")
    agents = value.get("visible_agents")
    if not isinstance(agents, list) or not agents:
        raise ValueError("Evolution report context visible_agents is invalid")
    seen: set[str] = set()
    for index, item in enumerate(agents):
        if not isinstance(item, dict) or set(item) != {
            "revision_id",
            "relationship",
            "parent",
            "path",
            "resources_path",
        }:
            raise ValueError(f"visible_agents[{index}] fields are invalid")
        revision_id = item.get("revision_id")
        relationship = item.get("relationship")
        if (
            not isinstance(revision_id, str)
            or revision_id in seen
            or not isinstance(item.get("parent"), bool)
            or relationship
            not in {"active", "challenger", "current_epoch_challenger", "lineage_history"}
        ):
            raise ValueError(f"visible_agents[{index}] identity is invalid")
        _safe_workspace_path(workspace, item.get("path"), "visible Agent path")
        _safe_workspace_path(workspace, item.get("resources_path"), "visible Agent resources_path")
        seen.add(revision_id)
    active = value.get("active_revision_id")
    if not isinstance(active, str) or active not in seen:
        raise ValueError("Evolution report context Active revision is invalid")
    max_bytes = value.get("max_report_bytes")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
        raise ValueError("Evolution report byte limit is invalid")
    for field in ("candidate", "report_path"):
        _safe_workspace_path(workspace, value.get(field), field)
    return value


def _ignored(relative: PurePosixPath) -> bool:
    return (
        any(part in _IGNORED_DIRECTORIES for part in relative.parts[:-1])
        or relative.name in _IGNORED_FILES
        or relative.suffix in _IGNORED_SUFFIXES
    )


def _snapshot(root: Path) -> dict[str, str]:
    metadata = root.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("Evolution comparison root must be a real directory")
    values: dict[str, str] = {}
    for path in root.rglob("*"):
        mode = path.lstat().st_mode
        relative = PurePosixPath(*path.relative_to(root).parts)
        if stat.S_ISDIR(mode):
            continue
        if _ignored(relative):
            continue
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise ValueError("Evolution Candidate contains a link or special file")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        values[relative.as_posix()] = digest.hexdigest()
    return values


def _changed_paths(before: Path, after: Path) -> list[str]:
    left = _snapshot(before)
    right = _snapshot(after)
    return sorted(path for path in left.keys() | right.keys() if left.get(path) != right.get(path))


def _structural_issue(error: str) -> dict[str, Any]:
    path = "report"
    for field in sorted(_REPORT_FIELDS, key=len, reverse=True):
        if field in error:
            path = field
            break
    return {"path": path, "code": "invalid", "message": error}


def _atomic_create_json(path: Path, value: dict[str, Any], *, max_bytes: int) -> None:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    if len(payload) > max_bytes:
        raise EvolutionReportIssue(
            "Evolution report exceeds its byte limit",
            [
                {
                    "path": "report",
                    "code": "byte_limit_exceeded",
                    "message": f"Report is {len(payload)} bytes; maximum is {max_bytes}",
                }
            ],
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o600)
        os.link(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def evolution_report(workspace: Path, request_path: Path) -> dict[str, Any]:
    """Validate one draft against the live Candidate and publish it exactly once."""
    context = _context(workspace)
    scratch = workspace / "scratch"
    request_input = request_path if request_path.is_absolute() else workspace / request_path
    request = request_input if request_input.is_symlink() else request_input.resolve()
    if request_input.is_symlink() or not request.is_relative_to(scratch):
        raise EvolutionReportIssue(
            "Evolution report request must be a regular file under scratch/",
            [
                {
                    "path": "request",
                    "code": "unsafe_path",
                    "message": "Use a regular draft file under scratch/",
                }
            ],
        )
    max_bytes = int(context["max_report_bytes"])
    agents = context["visible_agents"]
    assert isinstance(agents, list)
    visible = {str(item["revision_id"]): item for item in agents if isinstance(item, dict)}
    active = str(context["active_revision_id"])
    historical = frozenset(
        revision_id
        for revision_id, item in visible.items()
        if item.get("parent") is not True and item.get("relationship") != "current_epoch_challenger"
    )
    try:
        report = validate_evolution_output(
            request,
            active_revision_id=active,
            visible_revision_ids=frozenset(visible),
            historical_revision_ids=historical,
            max_bytes=max_bytes,
        )
    except EvolutionOutputContractError as error:
        raise EvolutionReportIssue(str(error), [_structural_issue(str(error))]) from error

    try:
        validate_contribution_sources(workspace, report["contributing_paths"], agents)
    except ValueError as error:
        raise EvolutionReportIssue(str(error), [_structural_issue(str(error))]) from error

    selected_id = str(report["kernel_agent_revision_id"])
    selected = visible[selected_id]
    candidate_bundle = _safe_workspace_path(workspace, context["candidate"], "candidate")
    try:
        validate_adaptive_directories(candidate_bundle, "Candidate Bundle")
    except ValueError as error:
        raise EvolutionReportIssue(
            str(error),
            [
                {
                    "path": "candidate",
                    "code": "invalid_runtime_state",
                    "message": str(error),
                    "hint": "Keep prompts/, insights/, skills/, tools/ "
                    "and a current README.md in each; "
                    "use only regular files/directories, repair the State, "
                    "then retry evolution-report.",
                }
            ],
        ) from error
    active_bundle = _safe_workspace_path(
        workspace,
        visible[active]["path"],
        "active path",
    )
    bundle_base = _safe_workspace_path(
        workspace,
        selected["path"],
        "selected path",
    )
    proposal_type = str(report["proposal_type"])
    actual_paths = _changed_paths(
        active_bundle if proposal_type in {"reuse", "no_change"} else bundle_base,
        candidate_bundle,
    )
    reported_paths = report["changed_paths"]
    assert isinstance(reported_paths, list)

    issues: list[dict[str, Any]] = []
    if reported_paths != actual_paths:
        issues.append(
            {
                "path": "changed_paths",
                "code": "bundle_diff_mismatch",
                "message": "changed_paths must equal the exact sorted Agent Bundle diff",
                "expected": actual_paths,
                "actual": reported_paths,
            }
        )
    if proposal_type in {"reuse", "no_change"} and actual_paths:
        issues.append(
            {
                "path": "proposal_type",
                "code": "unchanged_candidate_modified",
                "message": f"{proposal_type} requires Candidate Bundle to remain unchanged",
                "changed_paths": actual_paths,
            }
        )
    if proposal_type not in {"reuse", "no_change"} and not actual_paths:
        issues.append(
            {
                "path": "candidate",
                "code": "no_changes",
                "message": "A new Agent revision requires a Bundle change",
            }
        )
    if issues:
        raise EvolutionReportIssue("Evolution report disagrees with the Candidate", issues)

    report_path = _safe_workspace_path(workspace, context["report_path"], "report_path")
    if report_path.exists() or report_path.is_symlink():
        raise EvolutionReportIssue(
            "Evolution report is already published",
            [
                {
                    "path": "report",
                    "code": "already_published",
                    "message": "Do not call evolution-report after a successful response",
                }
            ],
        )
    _atomic_create_json(report_path, report, max_bytes=max_bytes)
    return {
        "status": "published",
        "report": report_path.relative_to(workspace).as_posix(),
        "proposal_type": proposal_type,
        "kernel_agent_revision_id": selected_id,
        "changed_count": len(actual_paths),
    }


def _error_response(error: BaseException) -> dict[str, Any]:
    if isinstance(error, EvolutionReportIssue):
        issues = error.issues
        detail = str(error)
    else:
        detail = str(error) or type(error).__name__
        issues = [{"path": "request", "code": "invalid", "message": detail}]
    return {
        "status": "error",
        "command": "evolution-report",
        "error": "invalid_request",
        "detail": detail,
        "issues": issues,
        "request_schema": request_schema(),
        "recovery": [
            {
                "instruction": (
                    "A failed evolution-report publishes nothing. Correct the same draft using "
                    "issues and request_schema, then retry. Do not retry after success."
                )
            },
            {
                "instruction": (
                    "changed_paths contains only exact sorted paths relative to candidate; "
                    "include changes in prompts/, insights/, skills/, and tools/."
                )
            },
            {
                "instruction": (
                    "contributing_paths lists existing files or directories actually incorporated "
                    "from input/agents/agent-vN or input/evidence/agent-vN/resources. "
                    "Parent Trajectory resources are allowed; unevaluated Challengers, links, "
                    "path traversal, mere reading, and automatic inheritance are not. "
                    "Use sorted unique paths, at most 64; reuse and no_change require []."
                )
            },
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("evolution-report")
    report.add_argument("--request", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        workspace = Path.cwd().resolve()
        result = evolution_report(workspace, args.request)
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps(_error_response(error), ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
