from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from runtime_tools import EvolutionReportIssue, evolution_report, main

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
        for name in ("prompts", "insights", "skills", "tools"):
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


@pytest.mark.parametrize(
    "relative",
    [
        "input/agents/agent-v1/skills",
        "input/agents/agent-v1/skills/README.md",
        "input/evidence/agent-v0/resources/trajectories/trajectory-00000002/insights",
    ],
)
def test_report_accepts_bundle_and_parent_trajectory_contributions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    resources = (
        workspace / "input/evidence/agent-v0/resources/trajectories/trajectory-00000002/insights"
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
    value["contributing_paths"] = ["input/agents/agent-v0/insights"]
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
    "directory", ("prompts", "insights", "skills", "tools")
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
    "directory", ("prompts", "insights", "skills", "tools")
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
