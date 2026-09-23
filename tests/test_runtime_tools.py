from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from runtime_tools import EvolutionReportIssue, agent_contract_check, evolution_report, main

ACTIVE = "agentrev_0123456789abcdef0123456789abcdef"
HISTORICAL = "agentrev_11111111111111111111111111111111"
LOSER = "agentrev_22222222222222222222222222222222"


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    workspace = tmp_path / "workspace"
    for path in (
        "input/agents/agent-v0/prompts",
        "input/agents/agent-v1/prompts",
        "input/agents/agent-v2/prompts",
        "candidate/prompts",
        "candidate/skills",
        "candidate/tools",
        "scratch",
    ):
        (workspace / path).mkdir(parents=True, exist_ok=True)
    for relative in (
        "input/agents/agent-v0/prompts/episode.md",
        "candidate/prompts/episode.md",
    ):
        (workspace / relative).write_text("active\n")
    (workspace / "input/agents/agent-v1/prompts/episode.md").write_text("historical\n")
    (workspace / "input/agents/agent-v2/prompts/episode.md").write_text("loser\n")
    for prefix in (
        "candidate",
        "input/agents/agent-v0",
        "input/agents/agent-v1",
        "input/agents/agent-v2",
    ):
        for name in ("prompts", "skills", "tools"):
            directory = workspace / prefix / name
            directory.mkdir(exist_ok=True)
            (directory / "README.md").write_text(f"# {name}\n")
    context = {
        "active_revision_id": ACTIVE,
        "visible_agents": [
            {
                "revision_id": ACTIVE,
                "relationship": "active",
                "parent": True,
                "path": "input/agents/agent-v0",
                "resources_path": "input/evidence/agent-v0/resources",
            },
            {
                "revision_id": HISTORICAL,
                "relationship": "lineage_history",
                "parent": False,
                "path": "input/agents/agent-v1",
                "resources_path": "input/evidence/agent-v1/resources",
            },
            {
                "revision_id": LOSER,
                "relationship": "challenger",
                "parent": False,
                "path": "input/agents/agent-v2",
                "resources_path": "input/evidence/agent-v2/resources",
            },
        ],
        "candidate": "candidate",
        "report_path": "scratch/evolution-report.json",
        "max_report_bytes": 8192,
    }
    monkeypatch.setenv("EVOLUTION_REPORT_CONTEXT_JSON", json.dumps(context))
    return workspace


def _contract_check_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    compatible: bool,
) -> Path:
    workspace = _workspace(tmp_path, monkeypatch)
    contract = workspace / "input/next-session-contract"
    contract.mkdir()
    tools = {
        "schema_version": 1,
        "bindings": {"gateway-execute": {}, "runtime-contract": {}},
        "gateway": {"operations": {"evaluate": {"type": "object"}}},
    }
    environment = {"schema_version": 1, "hardware_target": "sm_120"}
    limits = {"schema_version": 1, "session_timeout_seconds": 3600}
    for name, value in (
        ("tools.json", tools),
        ("environment.json", environment),
        ("limits.json", limits),
    ):
        (contract / name).write_text(json.dumps(value))
    source = workspace / "candidate/src"
    source.mkdir()
    (source / "runtime_tools.py").write_text(
        """import json, os, sys
from pathlib import Path
root = Path(os.environ['ATREX_RUNTIME_CONTRACT_PATH'])
tools = json.loads((root / 'tools.json').read_text())
environment = json.loads((root / 'environment.json').read_text())
limits = json.loads((root / 'limits.json').read_text())
if 'BROKEN' in __file__:
    environment = {'schema_version': 1, 'hardware_target': 'wrong'}
output = Path(sys.argv[sys.argv.index('--output') + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({
    'schema_version': 1,
    'environment': environment,
    'limits': limits,
    'tools': {
        'gateway-execute': {'operations': tools['gateway']['operations']},
        'runtime-contract': {'request_style': 'arguments'},
    },
}))
print(json.dumps({'status': 'written'}))
""".replace("if 'BROKEN' in __file__:", "if True:" if not compatible else "if False:")
    )
    monkeypatch.setenv(
        "ATREX_AGENT_CONTRACT_CHECK_CONTEXT_JSON",
        json.dumps(
            {
                "candidate": "candidate",
                "contract": "input/next-session-contract",
            }
        ),
    )
    return workspace


def test_agent_contract_check_accepts_dynamic_candidate_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _contract_check_workspace(tmp_path, monkeypatch, compatible=True)

    result = agent_contract_check(workspace)

    assert result["status"] == "valid"
    assert result["tool_count"] == 2


def test_agent_contract_check_rejects_a_stale_environment_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _contract_check_workspace(tmp_path, monkeypatch, compatible=False)

    with pytest.raises(ValueError, match="changed or omitted the Runtime environment"):
        agent_contract_check(workspace)


@pytest.mark.parametrize(
    "relative",
    [
        "input/agents/agent-v1/skills",
        "input/agents/agent-v1/skills/README.md",
        "input/evidence/agent-v0/resources/trajectories/trajectory-00000002/tools",
    ],
)
def test_report_accepts_bundle_and_parent_trajectory_contributions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    resources = (
        workspace / "input/evidence/agent-v0/resources/trajectories/trajectory-00000002/tools"
    )
    resources.mkdir(parents=True)
    (resources / "lesson.md").write_text("useful learned content")
    (workspace / "candidate/prompts/episode.md").write_text("revised")
    draft = _draft(workspace, changed_paths=["prompts/episode.md"])
    value = json.loads(draft.read_text())
    value["contributing_paths"] = [relative]
    draft.write_text(json.dumps(value))
    assert evolution_report(workspace, draft)["status"] == "published"


@pytest.mark.parametrize(
    "relative",
    [
        "input/agents/agent-v99",
        "input/agents/agent-v1/missing",
        "input/agents/agent-v1-evil",
        "input/evidence/agent-v0/sessions",
        "candidate/skills",
        "/etc/passwd",
        "input/agents/agent-v1/../agent-v0",
        "input/agents//agent-v1",
        "input/agents/agent-v1/",
        "input/agents/agent-v1/linked",
    ],
)
def test_report_rejects_invalid_contribution_and_allows_repair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    (workspace / "input/agents/agent-v1/linked").symlink_to(workspace / "candidate/prompts")
    (workspace / "candidate/prompts/episode.md").write_text("revised")
    draft = _draft(workspace, changed_paths=["prompts/episode.md"])
    value = json.loads(draft.read_text())
    value["contributing_paths"] = [relative]
    draft.write_text(json.dumps(value))
    with pytest.raises(EvolutionReportIssue, match="contributing_paths"):
        evolution_report(workspace, draft)
    assert not (workspace / "scratch/evolution-report.json").exists()
    value["contributing_paths"] = ["input/agents/agent-v0/tools"]
    draft.write_text(json.dumps(value))
    assert evolution_report(workspace, draft)["status"] == "published"


def test_report_rejects_resources_of_an_unevaluated_challenger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    context = json.loads(os.environ["EVOLUTION_REPORT_CONTEXT_JSON"])
    context["visible_agents"][2]["relationship"] = "current_epoch_challenger"
    monkeypatch.setenv("EVOLUTION_REPORT_CONTEXT_JSON", json.dumps(context))
    resources = workspace / "input/evidence/agent-v2/resources"
    resources.mkdir(parents=True)
    (workspace / "candidate/prompts/episode.md").write_text("revised")
    draft = _draft(workspace, changed_paths=["prompts/episode.md"])
    value = json.loads(draft.read_text())
    value["contributing_paths"] = ["input/evidence/agent-v2/resources"]
    draft.write_text(json.dumps(value))
    with pytest.raises(EvolutionReportIssue, match="eligible completed history"):
        evolution_report(workspace, draft)
    assert not (workspace / "scratch/evolution-report.json").exists()


def _draft(workspace: Path, *, changed_paths: list[str]) -> Path:
    path = workspace / "scratch/evolution-report-draft.json"
    path.write_text(
        json.dumps(
            {
                "proposal_type": "evolved",
                "kernel_agent_revision_id": ACTIVE,
                "hypothesis": "Use a narrower measured search policy.",
                "expected_effect": "Reduce repeated unsupported experiments.",
                "changed_paths": changed_paths,
                "contributing_paths": [],
                "unimplemented_capabilities": [],
            }
        )
    )
    return path


def _typed_draft(
    workspace: Path,
    *,
    proposal_type: str,
    revision_id: str,
    changed_paths: list[str],
) -> Path:
    path = workspace / "scratch/evolution-report-draft.json"
    path.write_text(
        json.dumps(
            {
                "proposal_type": proposal_type,
                "kernel_agent_revision_id": revision_id,
                "hypothesis": "Revive a design whose Session evidence supports it.",
                "expected_effect": "Recover the behavior its Attempt reports justify.",
                "changed_paths": changed_paths,
                "contributing_paths": [],
                "unimplemented_capabilities": [],
            }
        )
    )
    return path


def test_reuse_accepts_the_last_completed_epoch_losing_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    draft = _typed_draft(
        workspace,
        proposal_type="reuse",
        revision_id=LOSER,
        changed_paths=[],
    )

    published = evolution_report(workspace, draft)

    assert published["status"] == "published"


def test_no_change_keeps_the_current_active_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    draft = _typed_draft(
        workspace,
        proposal_type="no_change",
        revision_id=ACTIVE,
        changed_paths=[],
    )

    published = evolution_report(workspace, draft)

    assert published["status"] == "published"


def test_no_change_rejects_a_modified_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    (workspace / "candidate/prompts/episode.md").write_text("changed\n")
    draft = _typed_draft(
        workspace,
        proposal_type="no_change",
        revision_id=ACTIVE,
        changed_paths=[],
    )

    with pytest.raises(EvolutionReportIssue, match="Candidate"):
        evolution_report(workspace, draft)


def test_evolve_from_history_accepts_the_last_completed_epoch_losing_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    draft = _typed_draft(
        workspace,
        proposal_type="evolve_from_history",
        revision_id=LOSER,
        changed_paths=["prompts/episode.md"],
    )

    published = evolution_report(workspace, draft)

    assert published["status"] == "published"


def test_reuse_still_rejects_the_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    draft = _typed_draft(
        workspace,
        proposal_type="reuse",
        revision_id=ACTIVE,
        changed_paths=[],
    )

    with pytest.raises(EvolutionReportIssue, match="Active revision"):
        evolution_report(workspace, draft)


def test_reuse_still_rejects_a_current_epoch_challenger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    context = json.loads(os.environ["EVOLUTION_REPORT_CONTEXT_JSON"])
    for entry in context["visible_agents"]:
        if entry["revision_id"] == LOSER:
            entry["relationship"] = "current_epoch_challenger"
    monkeypatch.setenv("EVOLUTION_REPORT_CONTEXT_JSON", json.dumps(context))
    draft = _typed_draft(
        workspace,
        proposal_type="reuse",
        revision_id=LOSER,
        changed_paths=[],
    )

    with pytest.raises(EvolutionReportIssue, match="completed Lineage history"):
        evolution_report(workspace, draft)


def test_evolution_report_guides_source_diff_repair_and_publishes_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    (workspace / "candidate/prompts/episode.md").write_text("evolved\n")
    draft = _draft(workspace, changed_paths=[])

    with pytest.raises(EvolutionReportIssue) as raised:
        evolution_report(workspace, draft)

    assert raised.value.issues == [
        {
            "path": "changed_paths",
            "code": "bundle_diff_mismatch",
            "message": "changed_paths must equal the exact sorted Agent Bundle diff",
            "expected": ["prompts/episode.md"],
            "actual": [],
        }
    ]
    draft = _draft(workspace, changed_paths=["prompts/episode.md"])
    receipt = evolution_report(workspace, draft)
    assert receipt == {
        "status": "published",
        "report": "scratch/evolution-report.json",
        "proposal_type": "evolved",
        "kernel_agent_revision_id": ACTIVE,
        "changed_count": 1,
    }
    assert json.loads((workspace / "scratch/evolution-report.json").read_text()) == json.loads(
        draft.read_text()
    )
    with pytest.raises(EvolutionReportIssue, match="already published"):
        evolution_report(workspace, draft)


@pytest.mark.parametrize(
    "directory", ("prompts", "skills", "tools")
)
def test_evolution_report_accepts_state_only_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    directory: str,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    (workspace / "candidate" / directory / "search.md").write_text("measured search\n")

    receipt = evolution_report(
        workspace, _draft(workspace, changed_paths=[f"{directory}/search.md"])
    )

    assert receipt["changed_count"] == 1


@pytest.mark.parametrize(
    "task_fact",
    (
        "direction_d7462410254b4c8aa1ba96a0b93a3a58",
        "sha256:" + "a" * 64,
    ),
)
def test_evolution_report_rejects_task_specific_evidence_in_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    task_fact: str,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    path = workspace / "candidate/prompts/task-specific.md"
    path.write_text(f"Prefer this measured direction: {task_fact}\n")
    draft = _draft(workspace, changed_paths=["prompts/task-specific.md"])

    with pytest.raises(EvolutionReportIssue) as caught:
        evolution_report(workspace, draft)

    assert caught.value.issues[0]["code"] == "task_specific_evidence"
    assert "Runtime Journal" in caught.value.issues[0]["hint"]


def test_evolution_report_accepts_task_independent_process_correction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    path = workspace / "candidate/prompts/evidence-discipline.md"
    path.write_text("Verify a measurement before drawing a causal conclusion.\n")

    receipt = evolution_report(
        workspace,
        _draft(workspace, changed_paths=["prompts/evidence-discipline.md"]),
    )

    assert receipt["status"] == "published"


@pytest.mark.parametrize(
    "directory", ("prompts", "skills", "tools")
)
def test_report_allows_repairing_a_missing_state_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    directory: str,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    readme = workspace / "candidate" / directory / "README.md"
    readme.unlink()
    draft = _draft(workspace, changed_paths=[])
    with pytest.raises(EvolutionReportIssue) as caught:
        evolution_report(workspace, draft)
    assert caught.value.issues[0]["code"] == "invalid_runtime_state"
    assert "retry evolution-report" in caught.value.issues[0]["hint"]
    assert not (workspace / "scratch/evolution-report.json").exists()
    readme.write_text("repaired current index")
    draft = _draft(workspace, changed_paths=[f"{directory}/README.md"])
    assert evolution_report(workspace, draft)["status"] == "published"


def test_evolution_report_cli_returns_schema_and_recovery_on_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    draft = _draft(workspace, changed_paths=[])
    monkeypatch.chdir(workspace)

    assert main(["evolution-report", "--request", str(draft)]) == 2

    response = json.loads(capsys.readouterr().out)
    assert response["status"] == "error"
    assert response["issues"][0]["code"] == "no_changes"
    assert response["request_schema"]["additionalProperties"] is False
    assert "failed evolution-report publishes nothing" in response["recovery"][0]["instruction"]
    assert not (workspace / "scratch/evolution-report.json").exists()


def test_workflow_check_cli_returns_actionable_error_without_runtime_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    monkeypatch.delenv("EVOLUTION_WORKFLOW_CHECK_CONTEXT_JSON", raising=False)
    monkeypatch.chdir(workspace)

    assert main(["workflow-check"]) == 2

    response = json.loads(capsys.readouterr().out)
    assert response["command"] == "workflow-check"
    assert response["error"] == "invalid_workflow"
    assert "Repair candidate/workflow" in response["recovery"][0]["instruction"]


@pytest.mark.parametrize("suggestions", [[], [{"name": "Try a new split"}]])
def test_evolution_report_rejects_suggestions_and_guides_repair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    suggestions: list[dict[str, str]],
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    (workspace / "candidate/prompts/episode.md").write_text("revised\n")
    draft = _draft(workspace, changed_paths=["prompts/episode.md"])
    value = json.loads(draft.read_text())
    value["suggested_directions"] = suggestions
    draft.write_text(json.dumps(value))
    monkeypatch.chdir(workspace)

    assert main(["evolution-report", "--request", str(draft)]) == 2
    response = json.loads(capsys.readouterr().out)
    assert response["issues"][0]["path"] == "suggested_directions"
    assert "Remove this field" in response["detail"]
    assert "suggested_directions" not in response["request_schema"]["properties"]
    assert not (workspace / "scratch/evolution-report.json").exists()

    value.pop("suggested_directions")
    draft.write_text(json.dumps(value))
    assert main(["evolution-report", "--request", str(draft)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "published"
