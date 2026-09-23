#!/usr/bin/env python3
"""Agent-facing local tools for one Evolver session."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
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
_WORKFLOW_CHECK_CONTEXT_ENV = "EVOLUTION_WORKFLOW_CHECK_CONTEXT_JSON"
_AGENT_CONTRACT_CHECK_CONTEXT_ENV = "ATREX_AGENT_CONTRACT_CHECK_CONTEXT_JSON"
_IGNORED_DIRECTORIES = frozenset({".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__"})
_IGNORED_FILES = frozenset({".coverage", ".DS_Store"})
_IGNORED_SUFFIXES = frozenset({".pyc", ".pyo"})
_REPORT_FIELDS = EVOLUTION_OUTPUT_FIELDS
_TASK_EVIDENCE_PATTERNS = (
    re.compile(
        r"\b(?:agentrev|attempt|campaign|direction|epoch|experiment|gtrial|kernelrev|lineage)_"
        r"[0-9a-f]{8,}\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bsha256:[0-9a-f]{32,64}\b", re.IGNORECASE),
)


class EvolutionReportIssue(ValueError):
    """One or more correctable terminal-report problems."""

    def __init__(self, detail: str, issues: list[dict[str, Any]]) -> None:
        super().__init__(detail)
        self.issues = issues


def _object_file(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file")
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _agent_contract_check_available() -> bool:
    raw = os.environ.get(_AGENT_CONTRACT_CHECK_CONTEXT_ENV)
    if raw is None or not raw:
        return False
    value: object = json.loads(raw)
    return isinstance(value, dict) and value.get("contract") is not None


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
                        "or input/evidence/agent-vN/resources, or the corresponding "
                        "input/observer/active Source/Resources path; files or directories "
                        "are allowed."
                    ),
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


def _added_text(before: Path, after: Path) -> str:
    """Return only UTF-8 text introduced by one Candidate file change."""
    try:
        previous = before.read_text(encoding="utf-8").splitlines(keepends=True)
    except FileNotFoundError:
        previous = []
    except UnicodeDecodeError:
        return ""
    try:
        current = after.read_text(encoding="utf-8").splitlines(keepends=True)
    except (FileNotFoundError, UnicodeDecodeError):
        return ""
    introduced: list[str] = []
    matcher = difflib.SequenceMatcher(a=previous, b=current, autojunk=False)
    for operation, _left_start, _left_end, right_start, right_end in matcher.get_opcodes():
        if operation in {"insert", "replace"}:
            introduced.extend(current[right_start:right_end])
    return "".join(introduced)


def _task_specific_identity_issues(
    before: Path,
    after: Path,
    changed_paths: list[str],
) -> list[dict[str, Any]]:
    """Reject task Evidence identities copied into a reusable Agent Revision."""
    issues: list[dict[str, Any]] = []
    for relative in changed_paths:
        added = _added_text(before / relative, after / relative)
        matches = sorted(
            {
                match.group(0)
                for pattern in _TASK_EVIDENCE_PATTERNS
                for match in pattern.finditer(added)
            }
        )
        if not matches:
            continue
        issues.append(
            {
                "path": f"candidate/{relative}",
                "code": "task_specific_evidence",
                "message": (
                    "A reusable Agent Revision cannot embed task Evidence identities. "
                    "Keep the concrete Direction, Experiment, Kernel, Result, Attempt, "
                    "or Artifact facts in Runtime Journal/Reports and implement only the "
                    "task-independent behavior learned from them."
                ),
                "hint": (
                    "Remove concrete task identities from the Candidate. Cite them only in the "
                    "Evolution Report provenance and express the reusable correction without "
                    "choosing a Kernel direction; Runtime Journal retains the task evidence."
                ),
                "matches": matches[:16],
            }
        )
    return issues


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
        issue = _structural_issue(str(error))
        if error.field != "request":
            issue["path"] = error.field
        raise EvolutionReportIssue(str(error), [issue]) from error

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
                    "hint": "Keep prompts/, skills/, tools/ "
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
    if proposal_type not in {"reuse", "no_change"}:
        issues.extend(
            _task_specific_identity_issues(bundle_base, candidate_bundle, actual_paths)
        )
    if issues:
        raise EvolutionReportIssue("Evolution report disagrees with the Candidate", issues)
    if proposal_type not in {"reuse", "no_change"} and _agent_contract_check_available():
        try:
            agent_contract_check(workspace)
        except (OSError, RuntimeError, ValueError) as error:
            raise EvolutionReportIssue(
                "Candidate cannot consume the next Optimizer Session contract",
                [
                    {
                        "path": "candidate/src/runtime_tools.py",
                        "code": "incompatible_agent_contract",
                        "message": str(error) or type(error).__name__,
                        "hint": (
                            "Run agent-contract-check, repair dynamic contract discovery, and "
                            "retry evolution-report. Do not copy live schemas or limits into "
                            "Prompt text."
                        ),
                    }
                ],
            ) from error

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


def workflow_check(workspace: Path) -> dict[str, Any]:
    """Ask the installed trusted Runtime checker to dry-run the Candidate Workflow."""
    raw = os.environ.get(_WORKFLOW_CHECK_CONTEXT_ENV)
    if raw is None or not raw or len(raw.encode()) > 64 * 1024:
        raise ValueError(f"{_WORKFLOW_CHECK_CONTEXT_ENV} is missing or exceeds its byte limit")
    value: object = json.loads(raw)
    required = {
        "candidate",
        "dsl",
        "epoch_number",
        "max_challengers",
        "optimizer_attempt_budget",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("Runtime Workflow check context fields are invalid")
    candidate = _safe_workspace_path(workspace, value["candidate"], "candidate")
    dsl = value["dsl"]
    epoch_number = value["epoch_number"]
    max_challengers = value["max_challengers"]
    optimizer_attempt_budget = value["optimizer_attempt_budget"]
    if not isinstance(dsl, str) or not dsl:
        raise ValueError("Workflow check DSL is invalid")
    for name, item, minimum in (
        ("epoch_number", epoch_number, 1),
        ("max_challengers", max_challengers, 0),
        ("optimizer_attempt_budget", optimizer_attempt_budget, 1),
    ):
        if isinstance(item, bool) or not isinstance(item, int) or item < minimum:
            raise ValueError(f"Workflow check {name} is invalid")
    from atrex_runtime.kernel_agents.workflow_check import check_agent_workflow

    result = check_agent_workflow(
        candidate,
        dsl=dsl,
        epoch_number=epoch_number,
        max_challengers=max_challengers,
        optimizer_attempt_budget=optimizer_attempt_budget,
    )
    return {"command": "workflow-check", **result}


def agent_contract_check(workspace: Path) -> dict[str, Any]:
    """Verify that the Candidate can consume the next live Optimizer contract."""
    raw = os.environ.get(_AGENT_CONTRACT_CHECK_CONTEXT_ENV)
    if raw is None or not raw or len(raw.encode()) > 64 * 1024:
        raise ValueError(
            f"{_AGENT_CONTRACT_CHECK_CONTEXT_ENV} is missing or exceeds its byte limit"
        )
    value: object = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {"candidate", "contract"}:
        raise ValueError("Runtime Agent contract check context fields are invalid")
    if value["contract"] is None:
        raise ValueError("Next Optimizer Session contract is unavailable")
    candidate = _safe_workspace_path(workspace, value["candidate"], "candidate")
    contract = _safe_workspace_path(workspace, value["contract"], "contract")
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("Candidate Bundle is unavailable")
    if contract.is_symlink() or not contract.is_dir():
        raise ValueError("Next Optimizer Session contract is unavailable")
    entrypoint = candidate / "src/runtime_tools.py"
    if entrypoint.is_symlink() or not entrypoint.is_file():
        raise ValueError("Candidate has no src/runtime_tools.py contract adapter")

    output = workspace / "scratch/agent-contract-check.json"
    output.unlink(missing_ok=True)
    environment = dict(os.environ)
    environment.update(
        {
            "ATREX_RUNTIME_CONTRACT_PATH": str(contract),
            "ATREX_CORE_PHASE": "optimization_attempt",
        }
    )
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(entrypoint),
                "runtime-contract",
                "--output",
                "scratch/agent-contract-check.json",
            ],
            cwd=workspace,
            env=environment,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("Candidate contract adapter timed out") from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(
            "Candidate failed to consume the next Optimizer Session contract"
            + (f": {detail[:2000]}" if detail else "")
        )
    if output.is_symlink() or not output.is_file():
        raise ValueError("Candidate contract adapter did not write its projected contract")
    projected = _object_file(output, "Candidate projected contract")
    source = {
        name.removesuffix(".json"): _object_file(
            contract / name,
            f"Next Optimizer Session contract {name}",
        )
        for name in ("tools.json", "environment.json", "limits.json")
    }
    if projected.get("environment") != source["environment"]:
        raise ValueError("Candidate changed or omitted the Runtime environment contract")
    if projected.get("limits") != source["limits"]:
        raise ValueError("Candidate changed or omitted the Runtime limit contract")
    projected_tools = projected.get("tools")
    bindings = source["tools"].get("bindings")
    if not isinstance(projected_tools, dict) or not isinstance(bindings, dict):
        raise ValueError("Candidate projected tool contract is invalid")
    if set(projected_tools) != set(bindings):
        raise ValueError("Candidate tool bindings disagree with the Runtime contract")
    gateway = projected_tools.get("gateway-execute")
    expected_gateway = source["tools"].get("gateway")
    if (
        not isinstance(gateway, dict)
        or not isinstance(expected_gateway, dict)
        or gateway.get("operations") != expected_gateway.get("operations")
    ):
        raise ValueError("Candidate Gateway schemas disagree with the Runtime contract")
    return {
        "command": "agent-contract-check",
        "status": "valid",
        "checked": "candidate/src/runtime_tools.py",
        "contract": str(value["contract"]),
        "tool_count": len(projected_tools),
    }


def _error_response(error: BaseException, *, command: str) -> dict[str, Any]:
    if command in {"workflow-check", "agent-contract-check"}:
        scenario = getattr(error, "scenario", None)
        phase = getattr(error, "phase", None)
        response: dict[str, Any] = {
            "status": "error",
            "command": command,
            "error": (
                "invalid_workflow"
                if command == "workflow-check"
                else "incompatible_agent_contract"
            ),
            "detail": str(error) or type(error).__name__,
            "recovery": [
                {
                    "instruction": (
                        "Repair candidate/workflow, then rerun workflow-check. The check is "
                        "non-persistent and may be repeated until it passes."
                    )
                },
                {
                    "instruction": (
                        "Use only the bundled single-Epoch SDK, allocate the exact Optimizer "
                        "Attempt budget, handle evolve_agent returning null, and finish with "
                        "epoch.complete()."
                    )
                },
            ],
        }
        if command == "agent-contract-check":
            response["recovery"] = [
                {
                    "instruction": (
                        "Repair the Candidate's dynamic Runtime-contract adapter, then rerun "
                        "agent-contract-check. Do not copy the live schema or environment limits "
                        "into Prompts, Skills, or static configuration."
                    )
                }
            ]
        if isinstance(scenario, str):
            response["scenario"] = scenario
        if isinstance(phase, str):
            response["phase"] = phase
        return response
    if isinstance(error, EvolutionReportIssue):
        issues = error.issues
        detail = str(error)
    else:
        detail = str(error) or type(error).__name__
        field = error.field if isinstance(error, EvolutionOutputContractError) else "request"
        issues = [{"path": field, "code": "invalid", "message": detail}]
    return {
        "status": "error",
        "command": command,
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
                    "include changes in prompts/, skills/, and tools/."
                )
            },
            {
                "instruction": (
                    "contributing_paths lists existing files or directories actually incorporated "
                    "from input/agents/agent-vN, input/evidence/agent-vN/resources, or the "
                    "corresponding input/observer/active Source/Resources path. "
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
    commands.add_parser("workflow-check")
    commands.add_parser("agent-contract-check")
    args = parser.parse_args(argv)
    try:
        workspace = Path.cwd().resolve()
        if args.command == "workflow-check":
            result = workflow_check(workspace)
        elif args.command == "agent-contract-check":
            result = agent_contract_check(workspace)
        else:
            result = evolution_report(workspace, args.request)
    except (OSError, RuntimeError, ValueError) as error:
        print(
            json.dumps(
                _error_response(error, command=args.command),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
