"""Strict Runtime-authored context for one fresh Evolution session."""

from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_MANIFEST_BYTES = 256 * 1024
MAX_OPTIMIZATION_SUMMARY_BYTES = 16 * 1024 * 1024
MAX_EVIDENCE_PROMPT_BYTES = 32 * 1024
MAX_LAUNCH_INPUT_BYTES = 4096
LAUNCH_SENTINEL = "Run the versioned Evolver Bundle once."
_REVISION_ID = re.compile(r"^agentrev_[0-9a-f]{32}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_TRAJECTORY_DIRECTORY = re.compile(r"^trajectory-([0-9]{8})$")
_EVOLUTION_REPORT_FILE = re.compile(r"^evo-([1-9][0-9]*)\.json$")
RUNTIME_STATE_DIRECTORIES = ("prompts", "insights", "skills", "tools")
REVIEW_FILES = (
    "evolution-change-audit.json",
    "trajectory-comparison.json",
    "workflow-friction.json",
)


@dataclass(frozen=True)
class VisibleAgent:
    """One Runtime-validated read-only Optimizer design."""

    revision_id: str
    version: str
    optimizer_digest: str
    path: str
    root: Path
    optimization_summary_path: str
    optimization_summary_root: Path
    sessions_path: str | None
    sessions_root: Path | None
    reports_path: str | None
    reports_root: Path | None
    resources_path: str
    resources_root: Path
    runtime_state_trajectory_ordinals: tuple[int, ...]
    parent: bool
    relationship: str
    challenger_ordinal: int | None
    parent_revision_id: str | None
    created_by: str


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _text(value: object, label: str, *, max_length: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"{label} must be non-blank and at most {max_length} characters")
    if "\x00" in value:
        raise ValueError(f"{label} cannot contain NUL")
    return value


def _bounded_json_file(path: Path, label: str, max_bytes: int) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise ValueError(f"{label} is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} must be a regular file")
    if metadata.st_size > max_bytes:
        raise ValueError(f"{label} exceeds its byte limit")
    return _object(json.loads(path.read_text(encoding="utf-8")), label)


def _real_directory(path: Path, label: str) -> Path:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise ValueError(f"{label} is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"{label} must be a real directory")
    return path.resolve()


def validate_adaptive_directories(root: Path, label: str) -> None:
    _real_directory(root, label)
    if not set(RUNTIME_STATE_DIRECTORIES) <= {child.name for child in root.iterdir()}:
        raise ValueError(
            f"{label} must contain prompts/, insights/, skills/, tools/"
        )
    for name in RUNTIME_STATE_DIRECTORIES:
        tree = _real_directory(root / name, f"{label} {name}")
        for entry in tree.rglob("*"):
            mode = entry.lstat().st_mode
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError(f"{label} {name} contains an invalid entry")
        readme = tree / "README.md"
        if readme.is_symlink() or not readme.is_file():
            raise ValueError(f"{label} {name}/README.md must be a regular file")


def _validate_runtime_state(root: Path, revision_id: str) -> tuple[int, ...]:
    """Validate one Runtime-authored, read-only Agent-state Evidence projection."""
    if {child.name for child in root.iterdir()} != {"trajectories"}:
        raise ValueError(f"Agent {revision_id} runtime-state layout is invalid")
    trajectories = _real_directory(
        root / "trajectories",
        f"Agent {revision_id} runtime-state trajectories",
    )
    ordinals: list[int] = []
    for trajectory in sorted(trajectories.iterdir()):
        match = _TRAJECTORY_DIRECTORY.fullmatch(trajectory.name)
        if match is None:
            raise ValueError(f"Agent {revision_id} runtime-state trajectory name is invalid")
        ordinal = int(match.group(1))
        if ordinal <= 0:
            raise ValueError(f"Agent {revision_id} runtime-state trajectory ordinal is invalid")
        root = _real_directory(
            trajectory,
            f"Agent {revision_id} runtime-state trajectory {ordinal}",
        )
        validate_adaptive_directories(
            root, f"Agent {revision_id} runtime-state trajectory {ordinal}"
        )
        ordinals.append(ordinal)
    return tuple(ordinals)


def _strict_environment(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name)
    if value is None or not value.strip() or "\x00" in value:
        raise ValueError(f"{name} is required and cannot be blank")
    return value


def _expected_path(workspace: Path, relative: str, label: str) -> Path:
    parts = Path(relative)
    if parts.is_absolute() or parts == Path(".") or ".." in parts.parts:
        raise ValueError(f"{label} must be a safe workspace-relative path")
    value = workspace.joinpath(*parts.parts)
    resolved = value.resolve(strict=False)
    if not resolved.is_relative_to(workspace):
        raise ValueError(f"{label} escapes the Evolution workspace")
    return resolved


@dataclass(frozen=True)
class EvolutionContext:
    """Validated paths and identity visible to the Evolver implementation."""

    workspace: Path
    visible_agents: tuple[VisibleAgent, ...]
    evidence_root: Path
    evolution_reports_root: Path
    evolution_number: int
    candidate_root: Path
    scratch_root: Path
    output_path: Path
    token_usage_path: Path
    session_trace_path: Path
    parent_revision_id: str
    evidence_checkpoint: str
    optimizer_digest: str
    idempotency_key: str
    dsl: str
    evidence_prompt: str
    manifest: Mapping[str, Any]

    @classmethod
    def load(cls, environment: Mapping[str, str] | None = None) -> EvolutionContext:
        env = os.environ if environment is None else environment
        raw_manifest = _strict_environment(env, "ATREX_EVOLUTION_INPUT_JSON")
        if len(raw_manifest.encode("utf-8")) > MAX_MANIFEST_BYTES:
            raise ValueError("Evolution input manifest exceeds its byte limit")
        manifest = _object(json.loads(raw_manifest), "Evolution input manifest")
        workspace_input = Path(_strict_environment(env, "ATREX_EVOLUTION_WORKSPACE"))
        if workspace_input.is_symlink():
            raise ValueError("ATREX_EVOLUTION_WORKSPACE cannot be a symbolic link")
        workspace = _real_directory(workspace_input.resolve(), "Evolution workspace")
        expected_fields = {
            "schema_version",
            "parent_revision_id",
            "evidence_checkpoint",
            "idempotency_key",
            "dsl",
            "optimizer_digest",
            "visible_agents",
            "paths",
        }
        if set(manifest) != expected_fields:
            raise ValueError(
                "Evolution input fields disagree with schema: "
                f"{sorted(set(manifest) ^ expected_fields)}"
            )
        if manifest["schema_version"] != 11:
            raise ValueError("unsupported Evolution input schema_version")
        parent_revision_id = _text(manifest["parent_revision_id"], "parent_revision_id")
        if _REVISION_ID.fullmatch(parent_revision_id) is None:
            raise ValueError("parent_revision_id is invalid")
        evidence_checkpoint = _text(manifest["evidence_checkpoint"], "evidence_checkpoint")
        optimizer_digest = _text(manifest["optimizer_digest"], "optimizer_digest")
        if (
            _DIGEST.fullmatch(evidence_checkpoint) is None
            or _DIGEST.fullmatch(optimizer_digest) is None
        ):
            raise ValueError("Evolution artifact digest is invalid")
        idempotency_key = _text(manifest["idempotency_key"], "idempotency_key", max_length=300)
        dsl = _text(manifest["dsl"], "dsl", max_length=32)
        if dsl not in {"cuda", "triton", "cutedsl"}:
            raise ValueError("unsupported Evolution DSL")
        paths = _object(manifest["paths"], "Evolution paths")
        expected_paths = {
            "agents": "input/agents",
            "evidence": "input/evidence",
            "candidate": "candidate",
            "scratch": "scratch",
            "output": "scratch/evolution-report.json",
        }
        if paths != expected_paths:
            raise ValueError("Evolution paths disagree with protocol v11")

        agents_root = _real_directory(
            _expected_path(workspace, expected_paths["agents"], "agents path"),
            "Visible Agent repositories",
        )
        evidence_root = _real_directory(
            _expected_path(workspace, expected_paths["evidence"], "evidence path"),
            "Evidence view",
        )
        evolution_reports_root = _real_directory(
            _expected_path(workspace, "input/evolution-reports", "Evolution reports path"),
            "Evolution reports",
        )
        evolution_numbers: set[int] = set()
        for report in evolution_reports_root.iterdir():
            match = _EVOLUTION_REPORT_FILE.fullmatch(report.name)
            if match is None or report.is_symlink() or not report.is_file():
                raise ValueError("Evolution reports layout is invalid")
            evolution_number = int(match.group(1))
            value = _bounded_json_file(report, report.name, MAX_OPTIMIZATION_SUMMARY_BYTES)
            if value.get("evolution_number") != evolution_number:
                raise ValueError("Evolution report number disagrees with its filename")
            evolution_numbers.add(evolution_number)
        current_evolution_number = max(evolution_numbers, default=0) + 1
        raw_visible_agents = manifest["visible_agents"]
        if (
            not isinstance(raw_visible_agents, list)
            or not raw_visible_agents
            or len(raw_visible_agents) > 512
        ):
            raise ValueError("visible_agents must be a non-empty bounded list")
        visible_agents: list[VisibleAgent] = []
        seen_revisions: set[str] = set()
        for index, raw_visible in enumerate(raw_visible_agents):
            visible = _object(raw_visible, f"visible_agents[{index}]")
            if set(visible) != {
                "revision_id",
                "version",
                "optimizer_digest",
                "path",
                "optimization_summary_path",
                "sessions_path",
                "reports_path",
                "resources_path",
                "parent",
                "relationship",
                "challenger_ordinal",
                "parent_revision_id",
                "created_by",
            }:
                raise ValueError("visible Agent fields disagree with protocol v11")
            revision_id = _text(visible["revision_id"], "visible Agent revision_id")
            version = _text(visible["version"], "visible Agent version", max_length=64)
            digest = _text(visible["optimizer_digest"], "visible Agent optimizer_digest")
            relative = _text(visible["path"], "visible Agent path")
            optimization_summary_relative = _text(
                visible["optimization_summary_path"],
                "visible Agent optimization summary path",
            )
            sessions_relative = visible["sessions_path"]
            reports_relative = visible["reports_path"]
            runtime_state_relative = _text(
                visible["resources_path"],
                "visible Agent runtime-state path",
            )
            parent = visible["parent"]
            relationship = _text(
                visible["relationship"],
                "visible Agent relationship",
                max_length=64,
            )
            challenger_ordinal = visible["challenger_ordinal"]
            visible_parent_revision_id = visible["parent_revision_id"]
            created_by = _text(
                visible["created_by"],
                "visible Agent created_by",
                max_length=200,
            )
            if (
                _REVISION_ID.fullmatch(revision_id) is None
                or re.fullmatch(r"agent-v[0-9]+", version) is None
                or _DIGEST.fullmatch(digest) is None
                or not isinstance(parent, bool)
                or relationship
                not in {"active", "challenger", "current_epoch_challenger", "lineage_history"}
                or (parent and relationship not in {"active", "challenger"})
                or (
                    relationship in {"challenger", "current_epoch_challenger"}
                    and (
                        not isinstance(challenger_ordinal, int)
                        or isinstance(challenger_ordinal, bool)
                        or challenger_ordinal <= 0
                    )
                )
                or (
                    relationship not in {"challenger", "current_epoch_challenger"}
                    and challenger_ordinal is not None
                )
                or (
                    visible_parent_revision_id is not None
                    and (
                        not isinstance(visible_parent_revision_id, str)
                        or _REVISION_ID.fullmatch(visible_parent_revision_id) is None
                    )
                )
                or revision_id in seen_revisions
            ):
                raise ValueError("visible Agent entry is invalid")
            competed = relationship in {"active", "challenger"}
            expected_relative = f"input/agents/{version}"
            expected_runtime_state = f"input/evidence/{version}/resources"
            expected_summary = f"input/evidence/{version}/optimization-summary.json"
            expected_sessions = f"input/evidence/{version}/sessions" if competed else None
            expected_reports = f"input/evidence/{version}/reports" if competed else None
            if (
                relative != expected_relative
                or optimization_summary_relative != expected_summary
                or sessions_relative != expected_sessions
                or reports_relative != expected_reports
                or runtime_state_relative != expected_runtime_state
            ):
                raise ValueError("visible Agent paths disagree with its version")
            root = _real_directory(
                _expected_path(workspace, relative, "visible Agent path"),
                f"Visible Agent {revision_id}",
            )
            optimization_summary_root = _expected_path(
                workspace,
                optimization_summary_relative,
                "visible Agent optimization summary path",
            )
            _bounded_json_file(
                optimization_summary_root,
                f"Visible Agent {revision_id} optimization summary",
                MAX_OPTIMIZATION_SUMMARY_BYTES,
            )
            sessions_root = (
                None
                if expected_sessions is None
                else _real_directory(
                    _expected_path(workspace, expected_sessions, "visible Agent Sessions"),
                    f"Visible Agent {revision_id} Sessions",
                )
            )
            reports_root = (
                None
                if expected_reports is None
                else _real_directory(
                    _expected_path(workspace, expected_reports, "visible Agent Attempt reports"),
                    f"Visible Agent {revision_id} Attempt reports",
                )
            )
            resources_root = _real_directory(
                _expected_path(
                    workspace,
                    runtime_state_relative,
                    "visible Agent runtime-state path",
                ),
                f"Visible Agent {revision_id} runtime state",
            )
            runtime_state_trajectory_ordinals = _validate_runtime_state(
                resources_root,
                revision_id,
            )
            visible_agents.append(
                VisibleAgent(
                    revision_id,
                    version,
                    digest,
                    relative,
                    root,
                    optimization_summary_relative,
                    optimization_summary_root,
                    expected_sessions,
                    sessions_root,
                    expected_reports,
                    reports_root,
                    runtime_state_relative,
                    resources_root,
                    runtime_state_trajectory_ordinals,
                    parent,
                    relationship,
                    challenger_ordinal,
                    visible_parent_revision_id,
                    created_by,
                )
            )
            seen_revisions.add(revision_id)
        visible_versions = {item.version for item in visible_agents}
        if len(visible_versions) != len(visible_agents):
            raise ValueError("visible Agent versions are duplicated")
        if {child.name for child in agents_root.iterdir()} != visible_versions:
            raise ValueError("visible Agent directories disagree with the manifest")
        if {child.name for child in evidence_root.iterdir()} != (
            visible_versions | {"latest-epoch-facts.json", "journal", "review"}
        ):
            raise ValueError("visible Evidence directories disagree with the manifest")
        journal_root = _real_directory(evidence_root / "journal", "Evolver Journal")
        for category in ("directions", "experiments"):
            category_root = _real_directory(journal_root / category, f"Evolver {category}")
            index = category_root / "index.json"
            if index.is_symlink() or not index.is_file():
                raise ValueError(f"Evolver {category} index is unavailable")
        latest_facts = _bounded_json_file(
            evidence_root / "latest-epoch-facts.json",
            "latest Epoch facts",
            MAX_OPTIMIZATION_SUMMARY_BYTES,
        )
        review_root = _real_directory(evidence_root / "review", "Evolver review indexes")
        if {child.name for child in review_root.iterdir()} != set(REVIEW_FILES):
            raise ValueError("Evolver review index layout is invalid")
        for name in REVIEW_FILES:
            _bounded_json_file(
                review_root / name,
                f"Evolver review index {name}",
                MAX_OPTIMIZATION_SUMMARY_BYTES,
            )
        if set(latest_facts) != {
            "epoch_number",
            "selection_reason",
            "winner_kernel_agent_revision_id",
            "attempts",
            "branch_workflows",
        }:
            raise ValueError("latest Epoch facts fields are invalid")
        if not isinstance(latest_facts["attempts"], list) or not isinstance(
            latest_facts["branch_workflows"], list
        ):
            raise ValueError("latest Epoch facts Attempts or Branch Workflows are invalid")
        parents = [item for item in visible_agents if item.parent]
        if (
            len(parents) != 1
            or parents[0].revision_id != parent_revision_id
            or parents[0].optimizer_digest != optimizer_digest
        ):
            raise ValueError("visible Agent pool does not identify the exact Parent")
        candidate_root = _real_directory(
            _expected_path(workspace, expected_paths["candidate"], "candidate path"),
            "Candidate repository",
        )
        validate_adaptive_directories(candidate_root, "Candidate Bundle")
        scratch_root = _real_directory(
            _expected_path(workspace, expected_paths["scratch"], "scratch path"),
            "Evolution scratch",
        )
        active_root = next(item.root for item in visible_agents if item.parent)
        if active_root == candidate_root:
            raise ValueError("Active and Candidate repositories must be distinct")
        evidence_prompt = _strict_environment(env, "ATREX_EVIDENCE_PROMPT")
        if len(evidence_prompt.encode("utf-8")) > MAX_EVIDENCE_PROMPT_BYTES:
            raise ValueError("Evidence Prompt Fragment exceeds its byte limit")
        output_path = _expected_path(workspace, expected_paths["output"], "output path")
        supplied_candidate_input = Path(_strict_environment(env, "ATREX_EVOLUTION_CANDIDATE"))
        supplied_output_input = Path(_strict_environment(env, "ATREX_EVOLUTION_OUTPUT"))
        if supplied_candidate_input.is_symlink() or supplied_output_input.is_symlink():
            raise ValueError("Evolution environment paths cannot be symbolic links")
        supplied_candidate = supplied_candidate_input.resolve()
        supplied_output = supplied_output_input.resolve(strict=False)
        if supplied_candidate != candidate_root or supplied_output != output_path:
            raise ValueError("Evolution environment paths disagree with the signed manifest")
        if output_path.exists():
            raise ValueError("Evolution output must not exist before the Agent session")

        token_usage_path = Path(_strict_environment(env, "ATREX_TOKEN_USAGE_REPORT")).resolve(
            strict=False
        )
        expected_usage_path = scratch_root / "token-usage.json"
        if token_usage_path != expected_usage_path:
            raise ValueError("ATREX_TOKEN_USAGE_REPORT must be scratch/token-usage.json")
        if token_usage_path.exists() and token_usage_path.is_symlink():
            raise ValueError("Token usage report cannot be a symbolic link")
        session_trace_path = scratch_root / "evolver-session"
        if session_trace_path.exists() and session_trace_path.is_symlink():
            raise ValueError("Session trace path cannot be a symbolic link")
        return cls(
            workspace=workspace,
            visible_agents=tuple(visible_agents),
            evidence_root=evidence_root,
            evolution_reports_root=evolution_reports_root,
            evolution_number=current_evolution_number,
            candidate_root=candidate_root,
            scratch_root=scratch_root,
            output_path=output_path,
            token_usage_path=token_usage_path,
            session_trace_path=session_trace_path,
            parent_revision_id=parent_revision_id,
            evidence_checkpoint=evidence_checkpoint,
            optimizer_digest=optimizer_digest,
            idempotency_key=idempotency_key,
            dsl=dsl,
            evidence_prompt=evidence_prompt,
            manifest=manifest,
        )


def validate_launch_input(payload: str) -> None:
    """Require the Runtime transport to carry only a fixed non-instruction sentinel."""
    if len(payload.encode()) > MAX_LAUNCH_INPUT_BYTES:
        raise ValueError("Evolver launch input exceeds its byte limit")
    if payload.strip() != LAUNCH_SENTINEL:
        raise ValueError("Evolver launch input does not match the fixed Bundle sentinel")
