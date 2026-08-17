"""One fixed-prompt, token-accounted Evolver Agent session."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

from config import EvolverConfig
from context import EvolutionContext
from process import ProcessResult, run_bounded
from report import validate_evolution_output
from usage import ClaudeUsageObserver


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
        "evidence": "input/evidence",
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


def build_claude_command(config: EvolverConfig, prompt: str) -> list[str]:
    """Build the single supported non-interactive Claude CLI invocation."""
    command = [
        config.agent_executable,
        "--print",
        "--verbose",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--session-id",
        str(uuid.uuid4()),
        "--effort",
        config.reasoning_effort,
    ]
    if config.model:
        command += ["--model", config.model]
    if config.session_settings:
        command += ["--settings", config.session_settings]
    command.append(prompt)
    return command


def _write_trace(
    context: EvolutionContext,
    observer: ClaudeUsageObserver,
    process: ProcessResult,
    prompt: str,
) -> None:
    """Retain the unredacted Session input and raw captured Provider streams."""
    if (
        context.scratch_root.is_symlink()
        or not context.scratch_root.is_dir()
        or context.scratch_root.resolve() != context.session_trace_path.parent
    ):
        raise ValueError("Evolution scratch changed after launch validation")
    if context.session_trace_path.exists() or context.session_trace_path.is_symlink():
        raise ValueError("Session trace path must not be created by the Coding Agent")
    context.session_trace_path.mkdir(mode=0o700)
    atomic_text(context.session_trace_path / "input/prompt.md", prompt)
    atomic_text(
        context.session_trace_path / "provider/stdout.stream-json",
        process.stdout,
    )
    atomic_text(
        context.session_trace_path / "provider/stderr.log",
        process.stderr,
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
        for event in observer.events
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
            "backend": "claude",
            "returncode": process.returncode,
            "timed_out": process.timed_out,
            "output_overflow": process.output_overflow,
            "raw_provider_capture_complete": not process.output_overflow,
            "externally_terminated": process.externally_terminated,
            "budget_exhausted": observer.exhausted,
        },
    )


def execute(context: EvolutionContext, config: EvolverConfig) -> int:
    """Run one Agent, validate its annotation, and always publish provider usage."""
    observer = ClaudeUsageObserver(context.token_budget)
    process: ProcessResult | None = None
    session_started = False
    try:
        prompt = render_prompt(context, config)
        environment = os.environ.copy()
        environment.update(
            {
                "IS_SANDBOX": "1",
                "ATREX_EVOLUTION_INPUT": str(context.manifest_path),
                "ATREX_EVOLUTION_CANDIDATE": str(context.candidate_root),
                "ATREX_EVOLUTION_OUTPUT": str(context.output_path),
                "ATREX_TOKEN_BUDGET": str(context.token_budget),
                "ATREX_TOKEN_USAGE_REPORT": str(context.token_usage_path),
            }
        )
        if environment.get("ANTHROPIC_AUTH_TOKEN"):
            environment.pop("ANTHROPIC_API_KEY", None)
        session_started = True
        process = run_bounded(
            build_claude_command(config, prompt),
            cwd=context.workspace,
            environment=environment,
            timeout_seconds=config.agent_timeout_seconds,
            max_stdout_chars=config.max_stdout_chars,
            max_stderr_chars=config.max_stderr_chars,
            stdout_observer=observer.observe,
        )
        _write_trace(context, observer, process, prompt)
        if observer.exhausted:
            return 125
        if process.timed_out:
            return 124
        if process.externally_terminated:
            return 143
        if process.output_overflow:
            print("[evolver] Agent diagnostic output exceeded its bound", file=sys.stderr)
            return 1
        if process.returncode != 0:
            return process.returncode
        validate_evolution_output(
            context.output_path,
            expected_parent_revision_id=context.parent_revision_id,
            max_bytes=config.max_output_manifest_bytes,
        )
        return 0
    finally:
        atomic_json(
            context.token_usage_path,
            observer.report(session_started=session_started),
        )


def safe_error(error: BaseException) -> dict[str, Any]:
    """Return bounded non-secret error metadata for the outer process diagnostic."""
    return {"error_type": type(error).__name__}
