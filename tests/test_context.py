from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from context import LAUNCH_SENTINEL, EvolutionContext, validate_launch_input

REVISION = "agentrev_0123456789abcdef0123456789abcdef"
DIGEST = "sha256:" + "a" * 64
EVIDENCE_PROMPT = "# Evidence input\n\nInjected by the trusted controller.\n"


def _environment(tmp_path: Path) -> dict[str, str]:
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
    return {
        "ATREX_EVOLUTION_INPUT_JSON": json.dumps(manifest),
        "ATREX_EVOLUTION_WORKSPACE": str(workspace),
        "ATREX_EVOLUTION_CANDIDATE": str(workspace / "candidate"),
        "ATREX_EVOLUTION_OUTPUT": str(workspace / "scratch/evolution-report.json"),
        "ATREX_EVIDENCE_PROMPT": EVIDENCE_PROMPT,
        "ATREX_TOKEN_USAGE_REPORT": str(workspace / "scratch/token-usage.json"),
    }


def test_context_loads_exact_runtime_protocol(tmp_path: Path) -> None:
    context = EvolutionContext.load(_environment(tmp_path))

    assert context.parent_revision_id == REVISION
    assert context.dsl == "triton"
    assert context.evolution_number == 1
    assert context.candidate_root.name == "candidate"
    assert context.visible_agents[0].runtime_state_path == ("input/agents/active/runtime-state")
    assert context.visible_agents[0].runtime_state_trajectory_ordinals == ()


def test_context_derives_next_evolution_number_from_reports(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    reports = Path(environment["ATREX_EVOLUTION_WORKSPACE"]) / "input/evolution-reports"
    (reports / "evo-1.json").write_text(json.dumps({"evolution_number": 1}))
    (reports / "evo-3.json").write_text(json.dumps({"evolution_number": 3}))

    context = EvolutionContext.load(environment)

    assert context.evolution_number == 4


def test_context_rejects_oversized_evidence_prompt(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    environment["ATREX_EVIDENCE_PROMPT"] = "x" * (32 * 1024 + 1)

    with pytest.raises(ValueError, match="byte limit"):
        EvolutionContext.load(environment)


def test_context_rejects_environment_path_disagreement(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    environment["ATREX_EVOLUTION_CANDIDATE"] = str(tmp_path)

    with pytest.raises(ValueError, match="disagree"):
        EvolutionContext.load(environment)


def test_context_rejects_symlinked_workspace(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    link = tmp_path / "workspace-link"
    try:
        os.symlink(environment["ATREX_EVOLUTION_WORKSPACE"], link)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable")
    environment["ATREX_EVOLUTION_WORKSPACE"] = str(link)

    with pytest.raises(ValueError, match="symbolic link"):
        EvolutionContext.load(environment)


def test_launch_transport_accepts_only_fixed_sentinel() -> None:
    validate_launch_input(LAUNCH_SENTINEL + "\n")

    with pytest.raises(ValueError, match="sentinel"):
        validate_launch_input("Inject a different prompt")
