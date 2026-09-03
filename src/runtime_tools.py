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
                "enum": ["evolved", "evolve_from_history", "reuse"],
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
            "contributing_revision_ids": {
                "type": "array",
                "maxItems": 64,
                "uniqueItems": True,
                "items": {
                    "type": "string",
                    "pattern": r"^agentrev_[0-9a-f]{32}$",
                },
            },
            "unimplemented_capabilities": {
                "type": "array",
                "maxItems": 64,
                "items": capability,
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
        "candidate_source",
        "candidate_runtime_state",
        "runtime_state_base",
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
            "source_path",
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
        _safe_workspace_path(workspace, item.get("source_path"), "visible Agent source_path")
        seen.add(revision_id)
    active = value.get("active_revision_id")
    if not isinstance(active, str) or active not in seen:
        raise ValueError("Evolution report context Active revision is invalid")
    max_bytes = value.get("max_report_bytes")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
        raise ValueError("Evolution report byte limit is invalid")
    for field in (
        "candidate_source",
        "candidate_runtime_state",
        "runtime_state_base",
        "report_path",
    ):
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

    selected_id = str(report["kernel_agent_revision_id"])
    selected = visible[selected_id]
    candidate_source = _safe_workspace_path(
        workspace,
        context["candidate_source"],
        "candidate_source",
    )
    candidate_state = _safe_workspace_path(
        workspace,
        context["candidate_runtime_state"],
        "candidate_runtime_state",
    )
    try:
        validate_adaptive_directories(candidate_state, "Candidate runtime-state")
    except ValueError as error:
        raise EvolutionReportIssue(
            str(error),
            [
                {
                    "path": "candidate/runtime-state",
                    "code": "invalid_runtime_state",
                    "message": str(error),
                    "hint": "Keep memory/, docs/, skills/, tools/ and a current README.md in each; "
                    "use only regular files/directories, repair the State, "
                    "then retry evolution-report.",
                }
            ],
        ) from error
    state_base = _safe_workspace_path(
        workspace,
        context["runtime_state_base"],
        "runtime_state_base",
    )
    active_source = _safe_workspace_path(
        workspace,
        visible[active]["source_path"],
        "active source_path",
    )
    source_base = _safe_workspace_path(
        workspace,
        selected["source_path"],
        "selected source_path",
    )
    proposal_type = str(report["proposal_type"])
    actual_source_paths = _changed_paths(
        active_source if proposal_type == "reuse" else source_base,
        candidate_source,
    )
    runtime_state_paths = _changed_paths(state_base, candidate_state)
    reported_source_paths = report["changed_paths"]
    assert isinstance(reported_source_paths, list)

    issues: list[dict[str, Any]] = []
    if reported_source_paths != actual_source_paths:
        issues.append(
            {
                "path": "changed_paths",
                "code": "source_diff_mismatch",
                "message": "changed_paths must equal the exact sorted Agent Source diff",
                "expected": actual_source_paths,
                "actual": reported_source_paths,
            }
        )
    if proposal_type == "reuse" and (actual_source_paths or runtime_state_paths):
        issues.append(
            {
                "path": "proposal_type",
                "code": "reuse_candidate_modified",
                "message": "reuse requires Candidate Source and Runtime State to remain unchanged",
                "source_changed_paths": actual_source_paths,
                "runtime_state_changed": bool(runtime_state_paths),
            }
        )
    if proposal_type != "reuse" and not actual_source_paths and not runtime_state_paths:
        issues.append(
            {
                "path": "candidate",
                "code": "no_changes",
                "message": "A new Agent revision requires a Source or Runtime State change",
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
        "source_changed_count": len(actual_source_paths),
        "runtime_state_changed": bool(runtime_state_paths),
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
                    "changed_paths contains only exact sorted paths relative to candidate/source; "
                    "never include Runtime State paths."
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
