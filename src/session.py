"""One fixed-prompt, token-accounted Evolver Agent session."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

import backends
from config import EvolverConfig
from context import EvolutionContext
from report import EvolutionOutputContractError, validate_evolution_output
from session_transcript import (
    FILTERED_PROVIDER_EVENTS,
    encode_records,
    filter_provider_stdout,
    initial_records,
    render_conversation,
)

_LIVE_TRACE_MARKER = ".runtime-live-session"


def atomic_bytes(path: Path, payload: bytes) -> None:
    """Atomically publish one private file with durable contents."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
        temporary = None
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def atomic_json(path: Path, value: object) -> None:
    """Atomically publish one private JSON report with durable file contents."""
    atomic_bytes(
        path,
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
    )


def atomic_text(path: Path, value: str) -> None:
    """Publish captured Session text exactly as received after UTF-8 decoding."""
    atomic_bytes(path, value.encode("utf-8"))


def render_prompt(context: EvolutionContext, config: EvolverConfig) -> str:
    """Append only the minimal Runtime-authored context to the fixed repository Prompt."""
    template = config.prompt_path.read_text(encoding="utf-8")
    visible = {
        "schema_version": 1,
        "dsl": context.dsl,
        "parent_revision_id": context.parent_revision_id,
        "parent_repository": "input/parent",
        "visible_agent_repositories": [
            {
                "revision_id": item.revision_id,
                "optimizer_digest": item.optimizer_digest,
                "path": item.path,
                "parent": item.parent,
                "relationship": item.relationship,
                "challenger_ordinal": item.challenger_ordinal,
                "parent_revision_id": item.parent_revision_id,
                "created_by": item.created_by,
            }
            for item in context.visible_agents
        ],
        "evidence": "input/evidence",
        "runtime_tools": {
            "command": [sys.executable, "runtime-tools/evolver_tools.py"],
            "scope": "frozen_evidence_and_candidate_control",
        },
        "candidate_repository": "candidate",
        "output": "scratch/evolution-output.json",
    }
    return (
        template.rstrip()
        + "\n\n"
        + context.evidence_prompt.rstrip()
        + "\n\n# Session context\n\n```json\n"
        + json.dumps(visible, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n```\n"
    )


def _usage_report(
    result: backends.AgentRunResult | None,
    *,
    session_started: bool,
) -> dict[str, Any]:
    """Normalize every Backend into Runtime's provider-native usage report."""
    usage = result.terminal_usage if result is not None else backends.TokenUsage.unavailable()
    components = (
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_read_tokens,
        usage.cache_write_tokens,
    )
    unit = (
        "credits" if result is not None and result.runtime_id == "qodercli" else "provider_tokens"
    )
    complete = (
        usage.credits is not None
        if unit == "credits"
        else all(value is not None for value in components)
    ) and usage.measurement == "exact"
    buckets = {
        "uncached_input_tokens": usage.input_tokens or 0,
        "output_tokens": usage.output_tokens or 0,
        "cache_read_tokens": usage.cache_read_tokens or 0,
        "cache_write_tokens": usage.cache_write_tokens or 0,
    }
    request_count = (
        sum(1 for event in result.events if event.kind == "usage_delta")
        if result is not None
        else 0
    )
    if result is not None and (
        result.terminal_usage.total_tokens is not None or result.terminal_usage.credits is not None
    ):
        request_count = max(request_count, 1)
    credits = usage.credits if unit == "credits" else None
    consumed = credits if credits is not None else float(sum(buckets.values()))
    return {
        "schema_version": 2,
        "usage_unit": unit,
        "budget": None,
        "consumed": consumed,
        "token_usage": buckets,
        "credits": credits,
        "budget_exhausted": False,
        "session_count": 1 if session_started else 0,
        "model_request_count": request_count,
        "usage_complete": complete,
    }


def _start_live_trace(
    context: EvolutionContext,
    prompt: str,
    *,
    runtime_id: str,
    session_id: str,
    config: EvolverConfig,
) -> None:
    """Create the inspectable Session projection before the Provider starts."""
    if (
        context.scratch_root.is_symlink()
        or not context.scratch_root.is_dir()
        or context.scratch_root.resolve() != context.session_trace_path.parent
    ):
        raise ValueError("Evolution scratch changed before launch validation")
    trace_root = context.session_trace_path
    if trace_root.exists() or trace_root.is_symlink():
        raise ValueError("Session trace path must not be created by the Coding Agent")
    trace_root.mkdir(mode=0o700)
    atomic_text(trace_root / _LIVE_TRACE_MARKER, "unsealed\n")
    atomic_text(trace_root / "input/prompt.md", prompt)
    atomic_text(
        trace_root / "conversation.jsonl",
        encode_records(
            initial_records(
                backend=runtime_id,
                session_id=session_id,
                prompt=prompt,
            )
        ),
    )
    atomic_text(trace_root / "provider/stdout.stream-json", "")
    atomic_text(trace_root / "provider/stderr.log", "")
    if runtime_id == "codex":
        atomic_bytes(trace_root / "provider/codex-rollout.raw-jsonl", b"")
    atomic_json(
        trace_root / "session.json",
        {
            "schema_version": 1,
            "backend": runtime_id,
            "session_id": session_id,
            "reasoning_effort": config.reasoning_effort,
            "model": config.model,
            "runtime_bound": config.runtime_bound,
            "session_settings_sha256": hashlib.sha256(
                config.session_settings.encode("utf-8")
            ).hexdigest(),
            "state": "running",
            "raw_provider_capture_complete": False,
            "conversation_capture_complete": False,
            "provider_system_prompt_capture": "provider_managed_unavailable",
            "provider_event_filters": list(FILTERED_PROVIDER_EVENTS),
        },
    )


def _mark_live_trace_interrupted(
    context: EvolutionContext,
    error: BaseException,
) -> None:
    """Seal the available partial projection after a catchable interruption."""
    trace_root = context.session_trace_path
    marker = trace_root / _LIVE_TRACE_MARKER
    if (
        trace_root.is_symlink()
        or not trace_root.is_dir()
        or marker.is_symlink()
        or not marker.is_file()
    ):
        return
    try:
        session_path = trace_root / "session.json"
        session = json.loads(session_path.read_text(encoding="utf-8"))
        if not isinstance(session, dict):
            session = {}
        session["state"] = "interrupted"
        session["error_type"] = type(error).__name__
        session["raw_provider_capture_complete"] = False
        session["conversation_capture_complete"] = False
        prompt = (trace_root / "input/prompt.md").read_text(encoding="utf-8")
        stdout = (trace_root / "provider/stdout.stream-json").read_text(encoding="utf-8")
        raw_provider_files = tuple(
            (path.relative_to(trace_root).as_posix(), path.read_bytes())
            for path in sorted((trace_root / "provider").rglob("*"))
            if path.is_file()
            and path.name not in {"stdout.stream-json", "stderr.log"}
            and not path.is_symlink()
        )
        atomic_text(
            trace_root / "conversation.jsonl",
            render_conversation(
                backend=str(session.get("backend", "unknown")),
                session_id=str(session.get("session_id", "unknown")),
                prompt=prompt,
                stdout=stdout,
                raw_provider_files=raw_provider_files,
                state="interrupted",
                exit_status=None,
                timed_out=None,
                raw_provider_capture_complete=False,
                error_type=type(error).__name__,
            ),
        )
        atomic_json(session_path, session)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return


def _write_trace(
    context: EvolutionContext,
    result: backends.AgentRunResult,
    prompt: str,
    config: EvolverConfig,
    *,
    replace_live: bool = False,
) -> None:
    """Retain the unredacted Session input and raw captured Provider streams."""
    if (
        context.scratch_root.is_symlink()
        or not context.scratch_root.is_dir()
        or context.scratch_root.resolve() != context.session_trace_path.parent
    ):
        raise ValueError("Evolution scratch changed after launch validation")
    trace_root = context.session_trace_path
    if trace_root.exists() or trace_root.is_symlink():
        marker = trace_root / _LIVE_TRACE_MARKER
        if (
            not replace_live
            or trace_root.is_symlink()
            or not trace_root.is_dir()
            or marker.is_symlink()
            or not marker.is_file()
        ):
            raise ValueError("Session trace path must not be created by the Coding Agent")
    raw_files: list[tuple[PurePosixPath, bytes]] = []
    raw_paths: set[str] = set()
    reserved = {"provider/stdout.stream-json", "provider/stderr.log"}
    for raw_file in result.raw_session_files:
        relative = PurePosixPath(raw_file.relative_path)
        normalized = relative.as_posix()
        if (
            relative.is_absolute()
            or normalized == "."
            or ".." in relative.parts
            or not relative.parts
            or relative.parts[0] != "provider"
            or normalized in reserved
            or normalized in raw_paths
        ):
            raise ValueError("Raw Provider Session file has an unsafe path")
        raw_paths.add(normalized)
        raw_files.append((relative, raw_file.payload))
    if trace_root.exists():
        shutil.rmtree(trace_root)
    trace_root.mkdir(mode=0o700)
    filtered_stdout = filter_provider_stdout(result.stdout)
    atomic_text(context.session_trace_path / "input/prompt.md", prompt)
    atomic_text(
        context.session_trace_path / "provider/stdout.stream-json",
        filtered_stdout,
    )
    atomic_text(
        context.session_trace_path / "provider/stderr.log",
        result.stderr,
    )
    for relative, payload in raw_files:
        atomic_bytes(context.session_trace_path.joinpath(*relative.parts), payload)
    atomic_text(
        context.session_trace_path / "conversation.jsonl",
        render_conversation(
            backend=result.runtime_id,
            session_id=result.session_id,
            prompt=prompt,
            stdout=filtered_stdout,
            raw_provider_files=((path.as_posix(), payload) for path, payload in raw_files),
            state="finished",
            exit_status=result.exit_status,
            timed_out=result.timed_out,
            raw_provider_capture_complete=result.raw_provider_capture_complete,
        ),
    )
    normalized_events: list[dict[str, Any]] = [
        {
            "type": "session",
            "version": 0,
            "id": context.idempotency_key,
        }
    ]
    normalized_events.extend(
        {
            "type": "provider/usage",
            "seq": event["sequence"],
            "time": event["sequence"],
            "data": event,
            "ignorable": True,
        }
        for event in (
            {
                "schema_version": 1,
                "sequence": item.sequence,
                "kind": item.kind,
                "usage": (
                    None
                    if item.usage is None
                    else {
                        "uncached_input_tokens": item.usage.input_tokens,
                        "output_tokens": item.usage.output_tokens,
                        "cache_read_tokens": item.usage.cache_read_tokens,
                        "cache_write_tokens": item.usage.cache_write_tokens,
                        "total_tokens": item.usage.total_tokens,
                        "credits": item.usage.credits,
                        "usage_unit": (
                            "credits" if item.usage.credits is not None else "provider_tokens"
                        ),
                        "measurement": item.usage.measurement,
                    }
                ),
            }
            for item in result.events
        )
    )
    atomic_text(
        context.session_trace_path / "events.jsonl",
        "".join(
            json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
            for event in normalized_events
        ),
    )
    atomic_json(
        context.session_trace_path / "session.json",
        {
            "schema_version": 1,
            "backend": result.runtime_id,
            "session_id": result.session_id,
            "reasoning_effort": config.reasoning_effort,
            "model": config.model,
            "runtime_bound": config.runtime_bound,
            "session_settings_sha256": hashlib.sha256(
                config.session_settings.encode("utf-8")
            ).hexdigest(),
            "state": "finished",
            "returncode": result.exit_status,
            "timed_out": result.timed_out,
            "raw_provider_capture_complete": result.raw_provider_capture_complete,
            "conversation_capture_complete": result.raw_provider_capture_complete,
            "provider_system_prompt_capture": "provider_managed_unavailable",
            "provider_event_filters": list(FILTERED_PROVIDER_EVENTS),
            "observation_errors": list(result.observation_errors),
            "policy_diagnostics": list(result.policy_diagnostics),
            "budget_exhausted": False,
        },
    )


def execute(context: EvolutionContext, config: EvolverConfig) -> int:
    """Run one Agent, validate its annotation, and always publish provider usage."""
    result: backends.AgentRunResult | None = None
    session_started = False
    live_trace = False
    try:
        prompt = render_prompt(context, config)

        def run_provider(
            command: list[str],
            cwd: Path,
            timeout: int | None,
            env: dict[str, str] | None = None,
            observer: backends.ProcessObserver | None = None,
        ) -> backends.ProcessResult:
            return backends.run_bounded(
                [config.agent_executable, *command[1:]],
                cwd,
                timeout,
                env,
                observer,
                max_stderr_chars=config.max_stderr_chars,
            )

        runtime = backends.build_agent_runtime(
            config.agent_backend,
            process_runner=run_provider,
        )
        session_id = str(uuid.uuid4())
        _start_live_trace(
            context,
            prompt,
            runtime_id=runtime.id,
            session_id=session_id,
            config=config,
        )
        live_trace = True
        session_started = True
        result = runtime.run(
            backends.AgentRunRequest(
                workspace=context.workspace,
                prompt=prompt,
                timeout_s=config.agent_timeout_seconds,
                reasoning_effort=config.reasoning_effort,
                session_id=session_id,
                session_settings=config.session_settings,
                model=config.model,
                usage_budget=None,
                live_trace_path=context.session_trace_path,
                environment=(
                    ("ATREX_EVOLUTION_INPUT", str(context.manifest_path)),
                    ("ATREX_EVOLUTION_CANDIDATE", str(context.candidate_root)),
                    ("ATREX_EVOLUTION_OUTPUT", str(context.output_path)),
                    ("ATREX_TOKEN_USAGE_REPORT", str(context.token_usage_path)),
                ),
            )
        )
        _write_trace(context, result, prompt, config, replace_live=live_trace)
        if not result.raw_provider_capture_complete:
            return 126
        if result.timed_out:
            return 124
        if result.exit_status != 0:
            return result.exit_status
        validate_evolution_output(
            context.output_path,
            active_revision_id=context.parent_revision_id,
            visible_revision_ids=frozenset(item.revision_id for item in context.visible_agents),
            historical_revision_ids=frozenset(
                item.revision_id
                for item in context.visible_agents
                if item.relationship == "lineage_history"
            ),
            max_bytes=config.max_output_manifest_bytes,
        )
        return 0
    except BaseException as error:
        if live_trace:
            _mark_live_trace_interrupted(context, error)
        raise
    finally:
        atomic_json(
            context.token_usage_path,
            _usage_report(result, session_started=session_started),
        )


def safe_error(error: BaseException) -> dict[str, Any]:
    """Return bounded non-secret error metadata for the outer process diagnostic."""
    detail: dict[str, Any] = {"error_type": type(error).__name__}
    if isinstance(error, EvolutionOutputContractError):
        detail["message"] = str(error)[:500]
    return detail
