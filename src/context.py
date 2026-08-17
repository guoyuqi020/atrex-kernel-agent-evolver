"""Strict Runtime-authored context for one fresh Evolution session."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_MANIFEST_BYTES = 256 * 1024
MAX_EVIDENCE_PROMPT_BYTES = 32 * 1024
MAX_LAUNCH_INPUT_BYTES = 4096
LAUNCH_SENTINEL = "Run the versioned Evolver Bundle once."
_REVISION_ID = re.compile(r"^agentrev_[0-9a-f]{32}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


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


def _bounded_text_file(path: Path, label: str, max_bytes: int) -> tuple[str, bytes]:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise ValueError(f"{label} is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} must be a regular file")
    if metadata.st_size <= 0 or metadata.st_size > max_bytes:
        raise ValueError(f"{label} is empty or exceeds its byte limit")
    payload = path.read_bytes()
    try:
        return payload.decode("utf-8"), payload
    except UnicodeDecodeError as error:
        raise ValueError(f"{label} must be UTF-8") from error


def _real_directory(path: Path, label: str) -> Path:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise ValueError(f"{label} is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"{label} must be a real directory")
    return path.resolve()


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
    """Validated paths, identity, and quota visible to the Evolver implementation."""

    workspace: Path
    manifest_path: Path
    parent_root: Path
    evidence_root: Path
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
    token_budget: int
    evidence_prompt: str
    manifest: Mapping[str, Any]

    @classmethod
    def load(cls, environment: Mapping[str, str] | None = None) -> EvolutionContext:
        env = os.environ if environment is None else environment
        manifest_input = Path(_strict_environment(env, "ATREX_EVOLUTION_INPUT"))
        if manifest_input.is_symlink():
            raise ValueError("ATREX_EVOLUTION_INPUT cannot be a symbolic link")
        manifest_path = manifest_input.resolve()
        workspace = _real_directory(manifest_path.parent, "Evolution workspace")
        manifest = _bounded_json_file(
            manifest_path,
            "Evolution input manifest",
            MAX_MANIFEST_BYTES,
        )
        expected_fields = {
            "schema_version",
            "parent_revision_id",
            "evidence_checkpoint",
            "idempotency_key",
            "dsl",
            "optimizer_digest",
            "paths",
        }
        if set(manifest) != expected_fields:
            raise ValueError(
                "Evolution input fields disagree with schema: "
                f"{sorted(set(manifest) ^ expected_fields)}"
            )
        if manifest["schema_version"] != 2:
            raise ValueError("unsupported Evolution input schema_version")
        parent_revision_id = _text(manifest["parent_revision_id"], "parent_revision_id")
        if _REVISION_ID.fullmatch(parent_revision_id) is None:
            raise ValueError("parent_revision_id is invalid")
        evidence_checkpoint = _text(manifest["evidence_checkpoint"], "evidence_checkpoint")
        optimizer_digest = _text(manifest["optimizer_digest"], "optimizer_digest")
        if _DIGEST.fullmatch(evidence_checkpoint) is None or _DIGEST.fullmatch(
            optimizer_digest
        ) is None:
            raise ValueError("Evolution artifact digest is invalid")
        idempotency_key = _text(manifest["idempotency_key"], "idempotency_key", max_length=300)
        dsl = _text(manifest["dsl"], "dsl", max_length=32)
        if dsl not in {"cuda", "triton", "cutedsl"}:
            raise ValueError("unsupported Evolution DSL")
        paths = _object(manifest["paths"], "Evolution paths")
        expected_paths = {
            "parent": "input/parent",
            "evidence": "input/evidence",
            "candidate": "candidate",
            "scratch": "scratch",
            "output": "scratch/evolution-output.json",
        }
        if paths != expected_paths:
            raise ValueError("Evolution paths disagree with protocol v2")

        parent_root = _real_directory(
            _expected_path(workspace, expected_paths["parent"], "parent path"),
            "Parent repository",
        )
        evidence_root = _real_directory(
            _expected_path(workspace, expected_paths["evidence"], "evidence path"),
            "Evidence view",
        )
        candidate_root = _real_directory(
            _expected_path(workspace, expected_paths["candidate"], "candidate path"),
            "Candidate repository",
        )
        scratch_root = _real_directory(
            _expected_path(workspace, expected_paths["scratch"], "scratch path"),
            "Evolution scratch",
        )
        if parent_root == candidate_root:
            raise ValueError("Parent and Candidate repositories must be distinct")
        evidence_manifest = _bounded_json_file(
            evidence_root / "manifest.json",
            "Evidence view manifest",
            MAX_MANIFEST_BYTES,
        )
        expected_evidence_fields = {
            "schema_version",
            "role",
            "lineage_checkpoint",
            "prompt_fragment_sha256",
            "through_completed_epoch",
            "current_epoch",
            "visibility",
        }
        visibility = _object(evidence_manifest.get("visibility"), "Evidence visibility")
        if (
            set(evidence_manifest) != expected_evidence_fields
            or evidence_manifest.get("schema_version") != 1
            or evidence_manifest.get("role") != "evolver"
            or evidence_manifest.get("lineage_checkpoint") != evidence_checkpoint
            or not isinstance(evidence_manifest.get("through_completed_epoch"), int)
            or isinstance(evidence_manifest.get("through_completed_epoch"), bool)
            or int(evidence_manifest["through_completed_epoch"]) < 0
            or evidence_manifest.get("current_epoch") is not None
            or visibility
            != {
                "completed_epochs": "promoted_lineage",
                "current_attempts_before": None,
            }
        ):
            raise ValueError("Evidence view disagrees with the Evolution manifest")
        prompt_input = Path(_strict_environment(env, "ATREX_EVIDENCE_PROMPT_PATH"))
        if prompt_input.is_symlink():
            raise ValueError("ATREX_EVIDENCE_PROMPT_PATH cannot be a symbolic link")
        prompt_path = prompt_input.resolve()
        if prompt_path != evidence_root / "instructions.md":
            raise ValueError("Evidence Prompt Fragment path disagrees with the Evidence view")
        evidence_prompt, prompt_bytes = _bounded_text_file(
            prompt_path,
            "Evidence Prompt Fragment",
            MAX_EVIDENCE_PROMPT_BYTES,
        )
        if hashlib.sha256(prompt_bytes).hexdigest() != evidence_manifest.get(
            "prompt_fragment_sha256"
        ):
            raise ValueError("Evidence Prompt Fragment digest disagrees with the manifest")
        for required in ("bootstrap", "epochs"):
            _real_directory(evidence_root / required, f"Evidence {required}")
        output_path = _expected_path(workspace, expected_paths["output"], "output path")
        supplied_candidate_input = Path(
            _strict_environment(env, "ATREX_EVOLUTION_CANDIDATE")
        )
        supplied_output_input = Path(_strict_environment(env, "ATREX_EVOLUTION_OUTPUT"))
        if supplied_candidate_input.is_symlink() or supplied_output_input.is_symlink():
            raise ValueError("Evolution environment paths cannot be symbolic links")
        supplied_candidate = supplied_candidate_input.resolve()
        supplied_output = supplied_output_input.resolve(strict=False)
        if supplied_candidate != candidate_root or supplied_output != output_path:
            raise ValueError("Evolution environment paths disagree with the signed manifest")
        if output_path.exists():
            raise ValueError("Evolution output must not exist before the Agent session")

        token_usage_path = Path(
            _strict_environment(env, "ATREX_TOKEN_USAGE_REPORT")
        ).resolve(strict=False)
        expected_usage_path = scratch_root / "token-usage.json"
        if token_usage_path != expected_usage_path:
            raise ValueError("ATREX_TOKEN_USAGE_REPORT must be scratch/token-usage.json")
        if token_usage_path.exists() and token_usage_path.is_symlink():
            raise ValueError("Token usage report cannot be a symbolic link")
        session_trace_path = scratch_root / "evolver-session"
        if session_trace_path.exists() and session_trace_path.is_symlink():
            raise ValueError("Session trace path cannot be a symbolic link")
        raw_budget = _strict_environment(env, "ATREX_TOKEN_BUDGET")
        try:
            token_budget = int(raw_budget)
        except ValueError as error:
            raise ValueError("ATREX_TOKEN_BUDGET must be an integer") from error
        if token_budget <= 0 or str(token_budget) != raw_budget:
            raise ValueError("ATREX_TOKEN_BUDGET must be a canonical positive integer")
        return cls(
            workspace=workspace,
            manifest_path=manifest_path,
            parent_root=parent_root,
            evidence_root=evidence_root,
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
            token_budget=token_budget,
            evidence_prompt=evidence_prompt,
            manifest=manifest,
        )


def validate_launch_input(payload: str) -> None:
    """Require the Runtime transport to carry only a fixed non-instruction sentinel."""
    if len(payload.encode()) > MAX_LAUNCH_INPUT_BYTES:
        raise ValueError("Evolver launch input exceeds its byte limit")
    if payload.strip() != LAUNCH_SENTINEL:
        raise ValueError("Evolver launch input does not match the fixed Bundle sentinel")
