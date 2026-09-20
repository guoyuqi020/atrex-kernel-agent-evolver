from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from backends.process import ProcessObserver
from config import EvolverConfig
from context import LAUNCH_SENTINEL, EvolutionContext
from session import execute, render_prompt

REVISION = "agentrev_0123456789abcdef0123456789abcdef"
RIVAL = "agentrev_fedcba9876543210fedcba9876543210"
DIGEST = "sha256:" + "a" * 64
EVIDENCE_PROMPT = "# Evidence input\n\nInjected by the trusted controller.\n"


@pytest.fixture(autouse=True)
def isolated_claude_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-config"))


def _with_native_ledger(script: str) -> str:
    return script.replace(
        "from pathlib import Path\n",
        """from pathlib import Path
import builtins
import sys

session_id = sys.argv[sys.argv.index("--session-id") + 1]
native = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects/test" / (session_id + ".jsonl")
native.parent.mkdir(parents=True, exist_ok=True)
def print(value, **kwargs):
    if "file" not in kwargs:
        with native.open("a") as output:
            output.write(value + "\\n")
    builtins.print(value, **kwargs)
""",
    )


def _context(tmp_path: Path, *, with_challenger: bool = False) -> EvolutionContext:
    workspace = tmp_path / "run"
    for relative in (
        "input/agents/agent-v0",
        "input/evidence/agent-v0/resources/trajectories",
        "input/evidence/agent-v0/sessions",
        "input/evidence/agent-v0/reports",
        "input/evidence/journal/directions",
        "input/evidence/journal/experiments",
        "input/evidence/review",
        "input/evolution-reports",
        "candidate",
        "candidate/skills",
        "candidate/tools",
        "scratch",
    ):
        (workspace / relative).mkdir(parents=True, exist_ok=True)
    for name in ("prompts", "insights", "skills", "tools"):
        directory = workspace / "candidate" / name
        directory.mkdir(exist_ok=True)
        (directory / "README.md").write_text(f"# {name}\n")
    (workspace / "input/evidence/agent-v0/optimization-summary.json").write_text("{}")
    for category in ("directions", "experiments"):
        (workspace / f"input/evidence/journal/{category}/index.json").write_text("[]")
    (workspace / "input/evidence/latest-epoch-facts.json").write_text(json.dumps({
        "epoch_number": None,
        "selection_reason": None,
        "winner_kernel_agent_revision_id": None,
        "attempts": [],
        "branch_workflows": [],
    }))
    for name in (
        "evolution-change-audit.json",
        "trajectory-comparison.json",
        "workflow-friction.json",
    ):
        (workspace / "input/evidence/review" / name).write_text("{}")
    (workspace / "input/agents/agent-v0/atrex-bundle.json").write_text("{}")
    (workspace / "candidate/atrex-bundle.json").write_text("{}")
    visible_agents: list[dict[str, Any]] = [
        {
            "revision_id": REVISION,
            "version": "agent-v0",
            "optimizer_digest": DIGEST,
            "path": "input/agents/agent-v0",
            "optimization_summary_path": "input/evidence/agent-v0/optimization-summary.json",
            "sessions_path": "input/evidence/agent-v0/sessions",
            "reports_path": "input/evidence/agent-v0/reports",
            "resources_path": "input/evidence/agent-v0/resources",
            "parent": True,
            "relationship": "active",
            "challenger_ordinal": None,
            "parent_revision_id": None,
            "created_by": "bootstrap",
        }
    ]
    manifest = {
        "schema_version": 11,
        "parent_revision_id": REVISION,
        "evidence_checkpoint": DIGEST,
        "idempotency_key": "epoch:test:challenger",
        "dsl": "triton",
        "optimizer_digest": DIGEST,
        "visible_agents": visible_agents,
        "paths": {
            "agents": "input/agents",
            "evidence": "input/evidence",
            "candidate": "candidate",
            "scratch": "scratch",
            "output": "scratch/evolution-report.json",
        },
    }
    if with_challenger:
        for relative in (
            "input/agents/agent-v1",
            "input/evidence/agent-v1/resources/trajectories",
            "input/evidence/agent-v1/sessions",
            "input/evidence/agent-v1/reports",
        ):
            (workspace / relative).mkdir(parents=True)
        (workspace / "input/evidence/agent-v1/optimization-summary.json").write_text("{}")
        visible_agents.append(
            {
                "revision_id": RIVAL,
                "version": "agent-v1",
                "optimizer_digest": DIGEST,
                "path": "input/agents/agent-v1",
                "optimization_summary_path": "input/evidence/agent-v1/optimization-summary.json",
                "sessions_path": "input/evidence/agent-v1/sessions",
                "reports_path": "input/evidence/agent-v1/reports",
                "resources_path": "input/evidence/agent-v1/resources",
                "parent": False,
                "relationship": "challenger",
                "challenger_ordinal": 1,
                "parent_revision_id": REVISION,
                "created_by": "evolver",
            }
        )
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
candidate = Path("candidate")
(candidate / "prompts").mkdir(exist_ok=True)
(candidate / "prompts/evolve-result.md").write_text("new policy\\n")
Path("scratch/evolution-report.json").write_text(json.dumps({
    "proposal_type": "evolved",
    "kernel_agent_revision_id": "agentrev_0123456789abcdef0123456789abcdef",
    "hypothesis": "Use a narrower evidence-driven search policy.",
    "expected_effect": "Reduce repeated failed optimization directions.",
    "changed_paths": ["prompts/evolve-result.md"],
    "contributing_paths": [],
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
    script.write_text(_with_native_ledger(script.read_text()))
    os.chmod(script, 0o700)
    return script


def _budget_exhausting_claude(tmp_path: Path) -> Path:
    script = tmp_path / "budget-claude"
    script.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

candidate = Path("candidate")
(candidate / "prompts").mkdir(exist_ok=True)
(candidate / "prompts/evolve-result.md").write_text("unbounded policy\\n")
Path("scratch/evolution-report.json").write_text(json.dumps({
    "proposal_type": "evolved",
    "kernel_agent_revision_id": "agentrev_0123456789abcdef0123456789abcdef",
    "hypothesis": "Continue until the evolution direction is complete.",
    "expected_effect": "Avoid terminating evolution due to provider token count.",
    "changed_paths": ["prompts/evolve-result.md"],
    "contributing_paths": [],
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
    script.write_text(_with_native_ledger(script.read_text()))
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
candidate = Path("candidate")
(candidate / "prompts").mkdir(exist_ok=True)
(candidate / "prompts/evolve-result.md").write_text("live policy\\n")
Path("scratch/evolution-report.json").write_text(json.dumps({{
    "proposal_type": "evolved",
    "kernel_agent_revision_id": "agentrev_0123456789abcdef0123456789abcdef",
    "hypothesis": "Stream the Evolver trace while it runs.",
    "expected_effect": "Make active evolution sessions inspectable.",
    "changed_paths": ["prompts/evolve-result.md"],
    "contributing_paths": [],
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
    script.write_text(_with_native_ledger(script.read_text()))
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

    assert (context.candidate_root / "prompts/evolve-result.md").is_file()
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
    assistants = [row for row in conversation if row.get("event", {}).get("type") == "assistant"]
    assert len(assistants) == 1
    assert assistants[0]["path"] == "provider/claude-session.raw-jsonl"
    assert (
        context.session_trace_path / "provider/claude-session.raw-jsonl"
    ).read_text() == provider_stdout
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


def test_rendered_prompt_identifies_each_challenger_by_ordinal(tmp_path: Path) -> None:
    context = _context(tmp_path, with_challenger=True)
    config = _config(tmp_path, _fake_claude(tmp_path))

    prompt = render_prompt(context, config)
    entries = json.loads(prompt.split("# Session context\n\n```json\n", 1)[1].split("\n```", 1)[0])
    by_version = {item["version"]: item for item in entries["visible_agent_repositories"]}

    assert by_version["agent-v0"]["relationship"] == "active"
    assert by_version["agent-v0"]["challenger_ordinal"] is None
    assert by_version["agent-v1"]["relationship"] == "challenger"
    assert by_version["agent-v1"]["challenger_ordinal"] == 1
    assert '"challenger_ordinal": 1' in prompt


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
    assert "Runtime evaluates an accepted Challenger in the next Epoch" in prompt
    assert EVIDENCE_PROMPT.rstrip() in prompt
    assert '"dsl": "triton"' in prompt
    assert "gateway" not in prompt.lower().split("# session context", 1)[1]
    assert "wiki" not in prompt.lower().split("# session context", 1)[1]
    assert '"path": "input/agents/agent-v0"' in prompt
    assert '"relationship": "active"' in prompt
    assert '"challenger_ordinal": null' in prompt
    assert '"parent": true' in prompt
    assert '"parent_revision_id": null' in prompt
    assert '"optimization_summary_path": "input/evidence/agent-v0/' in prompt
    assert '"sessions_path": "input/evidence/agent-v0/sessions"' in prompt
    assert '"reports_path": "input/evidence/agent-v0/reports"' in prompt
    assert '"resources_path": "input/evidence/agent-v0/resources"' in prompt
    assert '"evolution_reports": "input/evolution-reports"' in prompt
    assert "`changed_paths`: exact sorted regular-file diff" in prompt
    assert "intentionally\n   omit Revision IDs" not in prompt
    assert '"optimizer_digest"' not in prompt.split("# Session context", 1)[1]
    assert '"created_by"' not in prompt.split("# Session context", 1)[1]
    assert "input/parent" not in prompt
    assert "input/reusable-agents" not in prompt
    assert "evolution-input.json" not in prompt
    assert "runtime-tools" not in prompt
    assert "candidate-reset" not in prompt
    assert "Each reusable directory has one effective copy" in prompt
    assert "candidate/runtime-state" not in prompt
    assert "candidate/source" not in prompt
    assert "`relationship` is not `current_epoch_challenger`" in prompt
    assert "when its `parent` is false" in prompt
    assert "`candidate/`" in prompt
    assert "All Candidate content can be edited" in prompt
    assert "only `tools/` is writable" in prompt
    assert "Curate Skills from actual evidence" in prompt
    assert "`skills/<name>/SKILL.md`" in prompt
    assert "one-off probes" in prompt
    assert "Runtime installs\nvalid Skills into the next Claude Optimizer" in prompt
    assert "python3 input/evolver/src/runtime_tools.py evolution-report" in prompt
    assert "scratch/evolution-report-draft.json" in prompt
    assert "never write `scratch/evolution-report.json` directly" in prompt
    assert "candidate" in prompt


def test_rendered_prompt_requires_a_complete_session_failure_audit(tmp_path: Path) -> None:
    context = _context(tmp_path)
    repository_prompt = Path(__file__).resolve().parents[1] / "prompts/evolve.md"
    config = replace(
        _config(tmp_path, _fake_claude(tmp_path)),
        prompt_path=repository_prompt,
    )
    prompt = render_prompt(context, config)
    normalized = " ".join(prompt.split())

    assert "# Session audit" in prompt
    assert "review `latest-epoch-facts.json`, the three `review/*.json` indexes" in normalized
    assert "do not rescan every long Session" in normalized
    assert "`attempt-NNNNNNNN.report.json`" in normalized
    assert "each Branch's optimization summary" in normalized
    assert "why each losing Branch lost" in normalized
    assert "`latest_epoch.selection_reason` semantics" in normalized
    assert "do not infer selection from raw latency or paths" in normalized
    assert "Find material problems even when a Session eventually succeeded" in normalized
    assert "a falsified Kernel hypothesis can be productive" in normalized
    assert "transient service failure is not automatically an Agent defect" in normalized
    for opportunity in (
        "invalid or repeated tool calls",
        "missing or late Journal updates",
        "excessive research or profiling",
        "poor recovery",
        "failure to terminate after sufficient evidence",
    ):
        assert opportunity in normalized
    assert "specific observed behavior" in normalized
    assert "causal Agent-level mechanism" in normalized
    assert "visible only to prevent duplicate proposals" in normalized
    assert "do not copy from it" in normalized


def test_rendered_prompt_enables_candidate_service_composition_without_new_authority(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    config = replace(
        _config(tmp_path, Path("/bin/false")),
        prompt_path=Path(__file__).resolve().parents[1] / "prompts/evolve.md",
    )
    prompt = render_prompt(context, config)
    normalized = " ".join(prompt.split())

    assert "# Extending Agent capabilities" in prompt
    assert "injected next-Optimizer service catalog" in normalized
    assert "composite helper in `candidate/tools/`" in normalized
    assert "change `candidate/src/` and its workflow" in normalized
    assert "trigger, exact invocation, inputs, and outputs" in normalized
    assert "only in later authorized Optimizer/Bootstrap sessions" in normalized
    assert "deduplication, validation, and terminal protocol" in normalized
    assert "not live Runtime service calls or GPU tests" in normalized
    assert "which existing services you considered" in normalized
    assert "not by itself a Runtime gap" in normalized
    assert "Do not modify Runtime, sandbox, credentials" in normalized


def test_rendered_prompt_reviews_previous_tool_changes_before_iterating(tmp_path: Path) -> None:
    context = _context(tmp_path)
    config = replace(
        _config(tmp_path, Path("/bin/false")),
        prompt_path=Path(__file__).resolve().parents[1] / "prompts/evolve.md",
    )
    prompt = render_prompt(context, config)
    normalized = " ".join(prompt.split())

    assert prompt.index("# Review the previous Evolution") < prompt.index("# Proposal mode")
    assert "previous evaluated changes, especially new or revised Tools" in normalized
    assert "`generated_agent.path`" in normalized
    assert "inspect its Active sessions instead" in normalized
    assert "Do not assume the highest report number has been evaluated" in normalized
    assert "effect cannot yet be assessed" in normalized
    assert "Agent discovered and invoked it" in normalized
    assert "whether it executed successfully" in normalized
    assert "used its output in a later decision, experiment, or handoff" in normalized
    assert "a file's presence or a mention is not proof of use" in normalized
    assert "no relevant trigger, missed discovery, execution failure" in normalized
    assert "installation, paths, invocation instructions, and workflow integration" in normalized
    assert "service and worker failures" in normalized
    assert "Winning an Epoch does not prove the change helped" in normalized
    assert "losing does not prove it failed" in normalized
    assert "retain, repair, simplify, consolidate, or remove" in normalized
    assert "do not create another audit file or report field" in normalized
    assert "do not run a live effectiveness test" in normalized
    assert "Complete the previous-Evolution review above before choosing a change" in normalized


def test_rendered_prompt_discovers_new_capabilities_from_optimizer_trajectories(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    config = replace(
        _config(tmp_path, Path("/bin/false")),
        prompt_path=Path(__file__).resolve().parents[1] / "prompts/evolve.md",
    )
    prompt = render_prompt(context, config)
    normalized = " ".join(prompt.split())

    assert prompt.index("# Discover improvements from Optimizer trajectories") < prompt.index(
        "# Proposal mode"
    )
    assert (
        "do not restrict Evolution to repairing tools that an earlier Evolver added" in normalized
    )
    assert "latest completed Active and Challenger Branches" in normalized
    assert "following relevant serial Attempts" in normalized
    assert "productive and stalled trajectories" in normalized
    assert "Look beyond the final Kernel latency" in normalized
    assert "typed binding or a reusable service-composition Tool" in normalized
    assert "reusable profiling/probe helper" in normalized
    assert "evidence-comparison helper" in normalized
    assert "adding or changing Candidate code would improve Kernel optimization" in normalized
    assert "observable next-Epoch effect" in normalized
    assert "previous change need not have failed" in normalized
    assert "do not invent a fixed Kernel search Direction" in normalized
    assert "`no_change` remains valid" in normalized
    assert "This analysis fits the existing report fields" in normalized
    assert "even when previous changes worked" in normalized


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
