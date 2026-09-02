from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from context import LAUNCH_SENTINEL, EvolutionContext, validate_launch_input

REVISION = "agentrev_0123456789abcdef0123456789abcdef"
RIVAL = "agentrev_fedcba9876543210fedcba9876543210"
DIGEST = "sha256:" + "a" * 64
EVIDENCE_PROMPT = "# Evidence input\n\nInjected by the trusted controller.\n"


def _environment(tmp_path: Path) -> dict[str, str]:
    workspace = tmp_path / "run"
    for relative in (
        "input/agents/agent-v0/source",
        "input/agents/agent-v0/runtime-state/trajectories",
        "input/evidence/agent-v0/sessions",
        "input/evidence/agent-v0/reports",
        "input/evolution-reports",
        "candidate/source",
        "candidate/runtime-state/skills",
        "candidate/runtime-state/tools",
        "scratch",
    ):
        (workspace / relative).mkdir(parents=True, exist_ok=True)
    (workspace / "candidate/runtime-state/tools/README.md").write_text("# Tools\n")
    (workspace / "input/evidence/agent-v0/optimization-summary.json").write_text("{}")
    manifest = {
        "schema_version": 11,
        "parent_revision_id": REVISION,
        "evidence_checkpoint": DIGEST,
        "idempotency_key": "epoch:test:challenger",
        "dsl": "triton",
        "optimizer_digest": DIGEST,
        "visible_agents": [
            {
                "revision_id": REVISION,
                "version": "agent-v0",
                "optimizer_digest": DIGEST,
                "path": "input/agents/agent-v0/source",
                "optimization_summary_path": "input/evidence/agent-v0/optimization-summary.json",
                "sessions_path": "input/evidence/agent-v0/sessions",
                "reports_path": "input/evidence/agent-v0/reports",
                "runtime_state_path": "input/agents/agent-v0/runtime-state",
                "parent": True,
                "relationship": "active",
                "challenger_ordinal": None,
                "parent_revision_id": None,
                "created_by": "bootstrap",
            }
        ],
        "paths": {
            "agents": "input/agents",
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
    assert context.visible_agents[0].runtime_state_path == ("input/agents/agent-v0/runtime-state")
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


def _add_version(
    environment: dict[str, str],
    *,
    version: str,
    relationship: str,
    parent: bool,
    challenger_ordinal: int | None,
    competed: bool,
) -> dict[str, str]:
    """Add one visible Agent version to the workspace and manifest."""
    workspace = Path(environment["ATREX_EVOLUTION_WORKSPACE"])
    for relative in (
        f"input/agents/{version}/source",
        f"input/agents/{version}/runtime-state/trajectories",
    ):
        (workspace / relative).mkdir(parents=True)
    (workspace / f"input/evidence/{version}").mkdir(parents=True)
    (workspace / f"input/evidence/{version}/optimization-summary.json").write_text("{}")
    if competed:
        (workspace / f"input/evidence/{version}/sessions").mkdir()
        (workspace / f"input/evidence/{version}/reports").mkdir()
    manifest = json.loads(environment["ATREX_EVOLUTION_INPUT_JSON"])
    manifest["visible_agents"].append(
        {
            "revision_id": RIVAL,
            "version": version,
            "optimizer_digest": DIGEST,
            "path": f"input/agents/{version}/source",
            "optimization_summary_path": f"input/evidence/{version}/optimization-summary.json",
            "sessions_path": f"input/evidence/{version}/sessions" if competed else None,
            "reports_path": f"input/evidence/{version}/reports" if competed else None,
            "runtime_state_path": f"input/agents/{version}/runtime-state",
            "parent": parent,
            "relationship": relationship,
            "challenger_ordinal": challenger_ordinal,
            "parent_revision_id": REVISION,
            "created_by": "evolver",
        }
    )
    environment["ATREX_EVOLUTION_INPUT_JSON"] = json.dumps(manifest)
    return environment


def _with_pool_challenger(environment: dict[str, str]) -> dict[str, str]:
    """Add the last completed Epoch's losing Challenger branch to the visible pool."""
    return _add_version(
        environment,
        version="agent-v1",
        relationship="challenger",
        parent=False,
        challenger_ordinal=1,
        competed=True,
    )


def test_context_accepts_the_last_completed_epoch_losing_branch(tmp_path: Path) -> None:
    context = EvolutionContext.load(_with_pool_challenger(_environment(tmp_path)))

    loser = next(item for item in context.visible_agents if item.revision_id == RIVAL)
    assert loser.relationship == "challenger"
    assert loser.challenger_ordinal == 1
    assert loser.parent is False
    assert loser.version == "agent-v1"
    assert loser.path == "input/agents/agent-v1/source"
    assert loser.sessions_path == "input/evidence/agent-v1/sessions"
    assert loser.reports_path == "input/evidence/agent-v1/reports"
    assert loser.sessions_root is not None
    assert loser.reports_root is not None


def test_context_accepts_a_parent_in_the_challenger_slot(tmp_path: Path) -> None:
    environment = _with_pool_challenger(_environment(tmp_path))
    manifest = json.loads(environment["ATREX_EVOLUTION_INPUT_JSON"])
    manifest["parent_revision_id"] = RIVAL
    for entry in manifest["visible_agents"]:
        entry["parent"] = entry["revision_id"] == RIVAL
    environment["ATREX_EVOLUTION_INPUT_JSON"] = json.dumps(manifest)

    context = EvolutionContext.load(environment)

    assert context.parent_revision_id == RIVAL
    parent = next(item for item in context.visible_agents if item.parent)
    assert parent.relationship == "challenger"


def test_context_rejects_a_parent_outside_the_comparison_pool(tmp_path: Path) -> None:
    environment = _add_version(
        _environment(tmp_path),
        version="agent-v1",
        relationship="current_epoch_challenger",
        parent=True,
        challenger_ordinal=1,
        competed=False,
    )
    manifest = json.loads(environment["ATREX_EVOLUTION_INPUT_JSON"])
    manifest["parent_revision_id"] = RIVAL
    for entry in manifest["visible_agents"]:
        entry["parent"] = entry["revision_id"] == RIVAL
    environment["ATREX_EVOLUTION_INPUT_JSON"] = json.dumps(manifest)

    with pytest.raises(ValueError, match="visible Agent entry is invalid"):
        EvolutionContext.load(environment)


def test_context_accepts_a_current_epoch_challenger_without_sessions(tmp_path: Path) -> None:
    environment = _add_version(
        _environment(tmp_path),
        version="agent-v1",
        relationship="current_epoch_challenger",
        parent=False,
        challenger_ordinal=1,
        competed=False,
    )

    context = EvolutionContext.load(environment)

    fresh = next(item for item in context.visible_agents if item.revision_id == RIVAL)
    assert fresh.relationship == "current_epoch_challenger"
    assert fresh.sessions_path is None
    assert fresh.reports_path is None
    assert fresh.sessions_root is None
    assert fresh.reports_root is None
    assert fresh.path == "input/agents/agent-v1/source"


def test_context_rejects_the_previous_input_schema(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    manifest = json.loads(environment["ATREX_EVOLUTION_INPUT_JSON"])
    manifest["schema_version"] = 10
    environment["ATREX_EVOLUTION_INPUT_JSON"] = json.dumps(manifest)

    with pytest.raises(ValueError, match="unsupported Evolution input schema_version"):
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
