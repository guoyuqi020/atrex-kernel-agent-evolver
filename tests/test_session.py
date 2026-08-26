from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from backends.process import ProcessObserver
from config import EvolverConfig
from context import LAUNCH_SENTINEL, EvolutionContext
from session import execute, render_prompt

REVISION = "agentrev_0123456789abcdef0123456789abcdef"
DIGEST = "sha256:" + "a" * 64
EVIDENCE_PROMPT = "# Evidence input\n\nInjected by the trusted controller.\n"


def _context(tmp_path: Path) -> EvolutionContext:
    workspace = tmp_path / "run"
    for relative in (
        "input/agents/active/source",
        "input/agents/active/runtime-state/trajectories",
        "input/historical",
        "input/evidence/active/sessions",
        "input/evolution-reports",
        "candidate/source",
        "candidate/runtime-state/skills",
        "candidate/runtime-state/tools",
        "scratch",
    ):
        (workspace / relative).mkdir(parents=True, exist_ok=True)
    (workspace / "candidate/runtime-state/tools/README.md").write_text("# Tools\n")
    (workspace / "input/evidence/active/optimization-summary.json").write_text("{}")
    (workspace / "input/agents/active/source/atrex-bundle.json").write_text("{}")
    (workspace / "candidate/source/atrex-bundle.json").write_text("{}")
    manifest = {
        "schema_version": 10,
        "parent_revision_id": REVISION,
        "evidence_checkpoint": DIGEST,
        "idempotency_key": "epoch:test:challenger",
        "dsl": "triton",
        "optimizer_digest": DIGEST,
        "visible_agents": [
            {
                "revision_id": REVISION,
                "version": None,
                "optimizer_digest": DIGEST,
                "path": "input/agents/active/source",
                "optimization_summary_path": "input/evidence/active/optimization-summary.json",
                "sessions_path": "input/evidence/active/sessions",
                "runtime_state_path": "input/agents/active/runtime-state",
                "parent": True,
                "relationship": "active",
                "challenger_ordinal": None,
                "parent_revision_id": None,
                "created_by": "bootstrap",
            }
        ],
        "paths": {
            "agents": "input/agents",
            "historical": "input/historical",
            "evidence": "input/evidence",
            "candidate": "candidate",
            "scratch": "scratch",
            "output": "scratch/evolution-report.json",
        },
    }
    return EvolutionContext.load(
        {
            "ATREX_EVOLUTION_INPUT_JSON": json.dumps(manifest),
            "ATREX_EVOLUTION_WORKSPACE": str(workspace),
            "ATREX_EVOLUTION_CANDIDATE": str(workspace / "candidate"),
            "ATREX_EVOLUTION_OUTPUT": str(workspace / "scratch/evolution-report.json"),
            "ATREX_EVIDENCE_PROMPT": EVIDENCE_PROMPT,
            "ATREX_TOKEN_USAGE_REPORT": str(workspace / "scratch/token-usage.json"),
        }
    )


def _fake_claude(tmp_path: Path) -> Path:
    script = tmp_path / "fake-claude"
    script.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

assert not any(key.startswith("ATREX_") for key in os.environ)
assert "EVOLUTION_REPORT_CONTEXT_JSON" in os.environ
candidate = Path("candidate/source")
(candidate / "prompts").mkdir(exist_ok=True)
(candidate / "prompts/evolve-result.md").write_text("new policy\\n")
Path("scratch/evolution-report.json").write_text(json.dumps({
    "proposal_type": "evolved",
    "kernel_agent_revision_id": "agentrev_0123456789abcdef0123456789abcdef",
    "hypothesis": "Use a narrower evidence-driven search policy.",
    "expected_effect": "Reduce repeated failed optimization directions.",
    "changed_paths": ["prompts/evolve-result.md"],
    "unimplemented_capabilities": [],
}))
print(json.dumps({
    "type": "system",
    "subtype": "thinking_tokens",
    "estimated_tokens": 18479,
}), flush=True)
print(json.dumps({
    "type": "assistant",
    "provider_credential": "Bearer raw-provider-secret",
    "message": {
        "id": "message-1",
        "content": [
            {"type": "thinking", "thinking": "raw hidden reasoning"},
            {"type": "tool_use", "input": {"token": "raw-tool-secret"}},
            {"type": "tool_result", "content": "raw tool result"},
        ],
        "usage": {
            "input_tokens": 20,
            "output_tokens": 5,
            "cache_read_input_tokens": 2,
            "cache_creation_input_tokens": 1,
        },
    },
}), flush=True)
print("raw stderr credential", file=sys.stderr, flush=True)
print(json.dumps({
    "type": "result",
    "usage": {
        "input_tokens": 20,
        "output_tokens": 5,
        "cache_read_input_tokens": 2,
        "cache_creation_input_tokens": 1,
    },
}), flush=True)
""",
        encoding="utf-8",
    )
    os.chmod(script, 0o700)
    return script


def _budget_exhausting_claude(tmp_path: Path) -> Path:
    script = tmp_path / "budget-claude"
    script.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

candidate = Path("candidate/source")
(candidate / "prompts").mkdir(exist_ok=True)
(candidate / "prompts/evolve-result.md").write_text("unbounded policy\\n")
Path("scratch/evolution-report.json").write_text(json.dumps({
    "proposal_type": "evolved",
    "kernel_agent_revision_id": "agentrev_0123456789abcdef0123456789abcdef",
    "hypothesis": "Continue until the evolution direction is complete.",
    "expected_effect": "Avoid terminating evolution due to provider token count.",
    "changed_paths": ["prompts/evolve-result.md"],
    "unimplemented_capabilities": [],
}))

print(json.dumps({
    "type": "assistant",
    "message": {
        "id": "message-over-budget",
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 1,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
    },
}), flush=True)
""",
        encoding="utf-8",
    )
    os.chmod(script, 0o700)
    return script


def _blocking_claude(tmp_path: Path) -> tuple[Path, Path, Path]:
    script = tmp_path / "blocking-claude"
    ready = tmp_path / "provider-ready"
    release = tmp_path / "provider-release"
    script.write_text(
        f"""#!/usr/bin/env python3
import json
import os
import time
from pathlib import Path

print(json.dumps({{"type": "assistant", "live": "first provider event"}}), flush=True)
Path({str(ready)!r}).write_text("ready")
while not Path({str(release)!r}).exists():
    time.sleep(0.01)
candidate = Path("candidate/source")
(candidate / "prompts").mkdir(exist_ok=True)
(candidate / "prompts/evolve-result.md").write_text("live policy\\n")
Path("scratch/evolution-report.json").write_text(json.dumps({{
    "proposal_type": "evolved",
    "kernel_agent_revision_id": "agentrev_0123456789abcdef0123456789abcdef",
    "hypothesis": "Stream the Evolver trace while it runs.",
    "expected_effect": "Make active evolution sessions inspectable.",
    "changed_paths": ["prompts/evolve-result.md"],
    "unimplemented_capabilities": [],
}}))
print(json.dumps({{"type": "result", "usage": {{
    "input_tokens": 1,
    "output_tokens": 1,
    "cache_read_input_tokens": 0,
    "cache_creation_input_tokens": 0,
}}}}), flush=True)
""",
        encoding="utf-8",
    )
    os.chmod(script, 0o700)
    return script, ready, release


def _config(tmp_path: Path, executable: Path) -> EvolverConfig:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Fixed evolution instructions.\n")
    return EvolverConfig(
        agent_backend="claude",
        agent_executable=str(executable),
        reasoning_effort="max",
        session_settings="",
        prompt_path=prompt,
        agent_timeout_seconds=10,
        max_stderr_chars=8192,
        max_output_manifest_bytes=4096,
        runtime_bound=True,
        model="lineage-model",
    )


def test_session_mutates_candidate_and_emits_runtime_reports(tmp_path: Path) -> None:
    context = _context(tmp_path)
    config = _config(tmp_path, _fake_claude(tmp_path))

    assert execute(context, config) == 0

    assert (context.candidate_root / "source/prompts/evolve-result.md").is_file()
    usage = json.loads(context.token_usage_path.read_text())
    assert usage["usage_unit"] == "provider_tokens"
    assert usage["consumed"] == 28
    assert usage["usage_complete"] is True
    assert (context.session_trace_path / "events.jsonl").is_file()
    assert (context.session_trace_path / "session.json").is_file()
    prompt = (context.session_trace_path / "input/prompt.md").read_text()
    assert "Fixed evolution instructions." in prompt
    assert '"dsl": "triton"' in prompt
    assert '"evolution_number": 1' in prompt
    provider_stdout = (context.session_trace_path / "provider/stdout.stream-json").read_text()
    assert "raw hidden reasoning" in provider_stdout
    assert "raw-tool-secret" in provider_stdout
    assert "raw tool result" in provider_stdout
    assert "Bearer raw-provider-secret" in provider_stdout
    assert "thinking_tokens" not in provider_stdout
    conversation = [
        json.loads(line)
        for line in (context.session_trace_path / "conversation.jsonl").read_text().splitlines()
    ]
    assert conversation[0]["type"] == "session_start"
    assert conversation[0]["provider_system_prompt"]["captured"] is False
    assert conversation[1]["role"] == "user"
    assert "Fixed evolution instructions." in conversation[1]["content"][0]["text"]
    assert any(
        row.get("event", {}).get("provider_credential") == "Bearer raw-provider-secret"
        for row in conversation
    )
    assert conversation[-1]["type"] == "session_end"
    assert all(row.get("subtype") != "thinking_tokens" for row in conversation)
    assert (
        "raw stderr credential" in (context.session_trace_path / "provider/stderr.log").read_text()
    )
    session = json.loads((context.session_trace_path / "session.json").read_text())
    assert session["backend"] == "claude"
    assert session["reasoning_effort"] == "max"
    assert session["model"] == "lineage-model"
    assert session["runtime_bound"] is True
    assert session["raw_provider_capture_complete"] is True
    assert session["conversation_capture_complete"] is True
    assert session["provider_system_prompt_capture"] == "provider_managed_unavailable"
    assert session["provider_event_filters"] == ["system/thinking_tokens"]
    normalized = (context.session_trace_path / "events.jsonl").read_text().splitlines()
    assert json.loads(normalized[0]) == {
        "id": "epoch:test:challenger",
        "type": "session",
        "version": 0,
    }
    assert all(json.loads(line)["ignorable"] is True for line in normalized[1:])


def test_session_trace_is_visible_while_evolver_is_running(tmp_path: Path) -> None:
    context = _context(tmp_path)
    executable, ready, release = _blocking_claude(tmp_path)
    result: list[int] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            result.append(execute(context, _config(tmp_path, executable)))
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    deadline = time.monotonic() + 5
    while not ready.is_file() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ready.is_file()
    trace = context.session_trace_path
    assert (trace / ".runtime-live-session").read_text() == "unsealed\n"
    running = json.loads((trace / "session.json").read_text())
    assert running["state"] == "running"
    assert running["conversation_capture_complete"] is False
    assert "first provider event" in (trace / "provider/stdout.stream-json").read_text()
    assert "first provider event" in (trace / "conversation.jsonl").read_text()

    release.write_text("continue")
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert errors == []
    assert result == [0]
    assert not (trace / ".runtime-live-session").exists()
    finished = json.loads((trace / "session.json").read_text())
    assert finished["state"] == "finished"
    assert finished["conversation_capture_complete"] is True


def test_session_trace_retains_partial_output_after_runner_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)

    def fail_runner(
        command: list[str],
        cwd: Path,
        timeout: int | None,
        env: dict[str, str] | None = None,
        observer: ProcessObserver | None = None,
        **_kwargs: object,
    ) -> object:
        del command, cwd, timeout, env
        assert observer is not None
        observer.on_stdout_line('{"type":"assistant","partial":true}\n')
        raise RuntimeError("provider transport failed")

    monkeypatch.setattr("session.backends.run_bounded", fail_runner)
    with pytest.raises(RuntimeError, match="provider transport failed"):
        execute(context, _config(tmp_path, Path("/bin/false")))

    trace = context.session_trace_path
    assert (trace / ".runtime-live-session").is_file()
    assert '"partial":true' in (trace / "provider/stdout.stream-json").read_text()
    session = json.loads((trace / "session.json").read_text())
    assert session["state"] == "interrupted"
    assert session["error_type"] == "RuntimeError"
    assert session["conversation_capture_complete"] is False
    conversation = (trace / "conversation.jsonl").read_text()
    assert '"partial": true' in conversation
    assert '"state": "interrupted"' in conversation


def test_rendered_prompt_exposes_no_runtime_authority(tmp_path: Path) -> None:
    context = _context(tmp_path)
    repository_prompt = Path(__file__).resolve().parents[1] / "prompts/evolve.md"
    config = replace(
        _config(tmp_path, Path("/bin/false")),
        prompt_path=repository_prompt,
    )
    prompt = render_prompt(context, config)

    assert "# Boundaries" in prompt
    assert "`dsl` is immutable" in prompt
    assert "Do not redirect the Optimizer to another DSL" in prompt
    assert "add, replace, reorganize, or delete any Agent-owned Source" in prompt
    assert "Runtime evaluates the Candidate in the next Epoch" in prompt
    assert EVIDENCE_PROMPT.rstrip() in prompt
    assert '"dsl": "triton"' in prompt
    assert "gateway" not in prompt.lower().split("# session context", 1)[1]
    assert "wiki" not in prompt.lower().split("# session context", 1)[1]
    assert '"source_path": "input/agents/active/source"' in prompt
    assert '"relationship": "active"' in prompt
    assert '"source_parent_revision_id": null' in prompt
    assert '"optimization_summary_path": "input/evidence/active/' in prompt
    assert '"sessions_path": "input/evidence/active/sessions"' in prompt
    assert '"runtime_state_path": "input/agents/active/runtime-state"' in prompt
    assert '"evolution_reports": "input/evolution-reports"' in prompt
    assert "Compare each prior report's" in prompt
    assert "identify its actual Source change" in prompt
    assert "intentionally\n   omit Revision IDs" not in prompt
    assert '"optimizer_digest"' not in prompt.split("# Session context", 1)[1]
    assert '"created_by"' not in prompt.split("# Session context", 1)[1]
    assert "input/parent" not in prompt
    assert "input/reusable-agents" not in prompt
    assert "evolution-input.json" not in prompt
    assert "runtime-tools" not in prompt
    assert "candidate-reset" not in prompt
    assert "Do not place top-level `skills/` or `tools/`" in prompt
    assert "candidate/runtime-state/" in prompt
    assert "reusable `skills/` and `tools/` seed" in prompt
    assert "input/evolver/src/runtime_tools.py evolution-report" in prompt
    assert "scratch/evolution-report-draft.json" in prompt
    assert "never write `scratch/evolution-report.json` directly" in prompt
    assert "candidate" in prompt


def test_session_records_large_usage_without_a_token_limit(tmp_path: Path) -> None:
    context = _context(tmp_path)
    config = _config(tmp_path, _budget_exhausting_claude(tmp_path))

    assert execute(context, config) == 0

    usage = json.loads(context.token_usage_path.read_text())
    assert usage["consumed"] == 1001
    assert usage["budget"] is None
    assert usage["budget_exhausted"] is False
    session = json.loads((context.session_trace_path / "session.json").read_text())
    assert session["budget_exhausted"] is False


def test_session_rejects_agent_created_trace_path(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.session_trace_path.mkdir()

    with pytest.raises(ValueError, match="must not be created"):
        execute(context, _config(tmp_path, _fake_claude(tmp_path)))

    assert context.token_usage_path.is_file()


def test_repository_entrypoint_runs_the_fixed_bundle_contract(tmp_path: Path) -> None:
    context = _context(tmp_path)
    fake = _fake_claude(tmp_path)
    executable = tmp_path / "claude"
    fake.rename(executable)
    repository = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{tmp_path}{os.pathsep}{environment.get('PATH', '')}",
            "ATREX_EVOLUTION_INPUT_JSON": json.dumps(context.manifest),
            "ATREX_EVOLUTION_WORKSPACE": str(context.workspace),
            "ATREX_EVOLUTION_CANDIDATE": str(context.candidate_root),
            "ATREX_EVOLUTION_OUTPUT": str(context.output_path),
            "ATREX_EVIDENCE_PROMPT": context.evidence_prompt,
            "ATREX_TOKEN_USAGE_REPORT": str(context.token_usage_path),
        }
    )

    result = subprocess.run(
        [str(repository / "src/main.py")],
        cwd=context.workspace,
        env=environment,
        input=LAUNCH_SENTINEL + "\n",
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert context.output_path.is_file()
    assert context.token_usage_path.is_file()
