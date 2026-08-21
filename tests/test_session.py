from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from config import EvolverConfig
from context import LAUNCH_SENTINEL, EvolutionContext
from session import execute, render_prompt

REVISION = "agentrev_0123456789abcdef0123456789abcdef"
DIGEST = "sha256:" + "a" * 64
EVIDENCE_PROMPT = "# Evidence input\n\nInjected by the trusted controller.\n"
EVIDENCE_PROMPT_SHA256 = hashlib.sha256(EVIDENCE_PROMPT.encode()).hexdigest()


def _context(tmp_path: Path) -> EvolutionContext:
    workspace = tmp_path / "run"
    for relative in (
        "input/parent",
        f"input/agents/{REVISION}",
        "input/evidence",
        "runtime-tools/kernels",
        "candidate",
        "scratch",
    ):
        (workspace / relative).mkdir(parents=True, exist_ok=True)
    (workspace / "input/evidence/bootstrap").mkdir()
    (workspace / "input/evidence/epochs").mkdir()
    (workspace / "input/evidence/instructions.md").write_text(
        EVIDENCE_PROMPT,
        encoding="utf-8",
    )
    (workspace / "input/evidence/manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "role": "evolver",
                "lineage_checkpoint": DIGEST,
                "prompt_fragment_sha256": EVIDENCE_PROMPT_SHA256,
                "through_completed_epoch": 0,
                "current_epoch": None,
                "visibility": {
                    "completed_epochs": "all_completed_branches",
                    "current_attempts_before": None,
                },
            }
        ),
        encoding="utf-8",
    )
    (workspace / "runtime-tools/catalog.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "evidence_checkpoint": DIGEST,
                "agents": [],
                "kernels": [],
            }
        ),
        encoding="utf-8",
    )
    (workspace / "runtime-tools/evolver_tools.py").write_text("# tool\n")
    (workspace / "input/parent/atrex-bundle.json").write_text("{}")
    (workspace / "candidate/atrex-bundle.json").write_text("{}")
    manifest = {
        "schema_version": 4,
        "parent_revision_id": REVISION,
        "evidence_checkpoint": DIGEST,
        "idempotency_key": "epoch:test:challenger",
        "dsl": "triton",
        "optimizer_digest": DIGEST,
        "visible_agents": [
            {
                "revision_id": REVISION,
                "optimizer_digest": DIGEST,
                "path": f"input/agents/{REVISION}",
                "parent": True,
                "relationship": "active",
                "challenger_ordinal": None,
                "parent_revision_id": None,
                "created_by": "bootstrap",
            }
        ],
        "paths": {
            "parent": "input/parent",
            "agents": "input/agents",
            "evidence": "input/evidence",
            "runtime_tools": "runtime-tools",
            "candidate": "candidate",
            "scratch": "scratch",
            "output": "scratch/evolution-output.json",
        },
    }
    manifest_path = workspace / "evolution-input.json"
    manifest_path.write_text(json.dumps(manifest))
    return EvolutionContext.load(
        {
            "ATREX_EVOLUTION_INPUT": str(manifest_path),
            "ATREX_EVOLUTION_CANDIDATE": str(workspace / "candidate"),
            "ATREX_EVOLUTION_OUTPUT": str(workspace / "scratch/evolution-output.json"),
            "ATREX_EVIDENCE_PROMPT_PATH": str(workspace / "input/evidence/instructions.md"),
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

candidate = Path(os.environ["ATREX_EVOLUTION_CANDIDATE"])
(candidate / "prompts").mkdir(exist_ok=True)
(candidate / "prompts/evolve-result.md").write_text("new policy\\n")
Path(os.environ["ATREX_EVOLUTION_OUTPUT"]).write_text(json.dumps({
    "schema_version": 3,
    "proposal_type": "evolved",
    "base_revision_id": json.loads(
        Path(os.environ["ATREX_EVOLUTION_INPUT"]).read_text()
    )["parent_revision_id"],
    "hypothesis": "Use a narrower evidence-driven search policy.",
    "expected_effect": "Reduce repeated failed optimization directions.",
    "changed_paths": ["prompts/evolve-result.md"],
}))
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

candidate = Path(os.environ["ATREX_EVOLUTION_CANDIDATE"])
(candidate / "prompts").mkdir(exist_ok=True)
(candidate / "prompts/evolve-result.md").write_text("unbounded policy\\n")
manifest = json.loads(Path(os.environ["ATREX_EVOLUTION_INPUT"]).read_text())
Path(os.environ["ATREX_EVOLUTION_OUTPUT"]).write_text(json.dumps({
    "schema_version": 3,
    "proposal_type": "evolved",
    "base_revision_id": manifest["parent_revision_id"],
    "hypothesis": "Continue until the evolution direction is complete.",
    "expected_effect": "Avoid terminating evolution due to provider token count.",
    "changed_paths": ["prompts/evolve-result.md"],
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
        max_stdout_chars=8192,
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
    provider_stdout = (context.session_trace_path / "provider/stdout.stream-json").read_text()
    assert "raw hidden reasoning" in provider_stdout
    assert "raw-tool-secret" in provider_stdout
    assert "raw tool result" in provider_stdout
    assert "Bearer raw-provider-secret" in provider_stdout
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
    normalized = (context.session_trace_path / "events.jsonl").read_text().splitlines()
    assert json.loads(normalized[0]) == {
        "id": "epoch:test:challenger",
        "type": "session",
        "version": 0,
    }
    assert all(json.loads(line)["ignorable"] is True for line in normalized[1:])


def test_rendered_prompt_exposes_no_runtime_authority(tmp_path: Path) -> None:
    context = _context(tmp_path)
    repository_prompt = Path(__file__).resolve().parents[1] / "prompts/evolve.md"
    config = replace(
        _config(tmp_path, Path("/bin/false")),
        prompt_path=repository_prompt,
    )
    prompt = render_prompt(context, config)

    assert "# Binding DSL constraint" in prompt
    assert "authoritative and immutable" in prompt
    assert "Do not redirect the Optimizer to another DSL" in prompt
    assert EVIDENCE_PROMPT.rstrip() in prompt
    assert '"dsl": "triton"' in prompt
    assert "gateway" not in prompt.lower().split("# session context", 1)[1]
    assert "wiki" not in prompt.lower().split("# session context", 1)[1]
    assert "input/parent" in prompt
    assert f"input/agents/{REVISION}" in prompt
    assert "runtime-tools/evolver_tools.py" in prompt
    assert "frozen_evidence_and_candidate_control" in prompt
    assert "# Runtime capabilities" in prompt
    assert "connect a best Kernel revision" in prompt
    assert "not a mandatory call sequence" in prompt
    assert "candidate-reset --base" in prompt
    assert "Do not copy, delete, or reconstruct" in prompt
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
            "ATREX_EVOLUTION_INPUT": str(context.manifest_path),
            "ATREX_EVOLUTION_CANDIDATE": str(context.candidate_root),
            "ATREX_EVOLUTION_OUTPUT": str(context.output_path),
            "ATREX_EVIDENCE_PROMPT_PATH": str(context.evidence_root / "instructions.md"),
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
