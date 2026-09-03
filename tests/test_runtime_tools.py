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
        "input/agents/agent-v0/source/prompts",
        "input/agents/agent-v1/source/prompts",
        "input/agents/agent-v2/source/prompts",
        "candidate/source/prompts",
        "candidate/runtime-state/skills",
        "candidate/runtime-state/tools",
        "scratch/.evolution-report/runtime-state-base/skills",
        "scratch/.evolution-report/runtime-state-base/tools",
    ):
        (workspace / path).mkdir(parents=True, exist_ok=True)
    for relative in (
        "input/agents/agent-v0/source/prompts/episode.md",
        "candidate/source/prompts/episode.md",
    ):
        (workspace / relative).write_text("active\n")
    (workspace / "input/agents/agent-v1/source/prompts/episode.md").write_text("historical\n")
    (workspace / "input/agents/agent-v2/source/prompts/episode.md").write_text("loser\n")
    for prefix in (
        "candidate/runtime-state",
        "scratch/.evolution-report/runtime-state-base",
    ):
        for name in ("memory", "docs", "skills", "tools"):
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
                "source_path": "input/agents/agent-v0/source",
            },
            {
                "revision_id": HISTORICAL,
                "relationship": "lineage_history",
                "parent": False,
                "source_path": "input/agents/agent-v1/source",
            },
            {
                "revision_id": LOSER,
                "relationship": "challenger",
                "parent": False,
                "source_path": "input/agents/agent-v2/source",
            },
        ],
        "candidate_source": "candidate/source",
        "candidate_runtime_state": "candidate/runtime-state",
        "runtime_state_base": "scratch/.evolution-report/runtime-state-base",
        "report_path": "scratch/evolution-report.json",
        "max_report_bytes": 8192,
    }
    monkeypatch.setenv("EVOLUTION_REPORT_CONTEXT_JSON", json.dumps(context))
    return workspace


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
                "contributing_revision_ids": [],
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
                "contributing_revision_ids": [],
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
    (workspace / "candidate/source/prompts/episode.md").write_text("evolved\n")
    draft = _draft(workspace, changed_paths=[])

    with pytest.raises(EvolutionReportIssue) as raised:
        evolution_report(workspace, draft)

    assert raised.value.issues == [
        {
            "path": "changed_paths",
            "code": "source_diff_mismatch",
            "message": "changed_paths must equal the exact sorted Agent Source diff",
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
        "source_changed_count": 1,
        "runtime_state_changed": False,
    }
    assert json.loads((workspace / "scratch/evolution-report.json").read_text()) == json.loads(
        draft.read_text()
    )
    with pytest.raises(EvolutionReportIssue, match="already published"):
        evolution_report(workspace, draft)


@pytest.mark.parametrize("directory", ("memory", "docs", "skills", "tools"))
def test_evolution_report_accepts_state_only_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    directory: str,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    (workspace / "candidate/runtime-state" / directory / "search.md").write_text(
        "measured search\n"
    )

    receipt = evolution_report(workspace, _draft(workspace, changed_paths=[]))

    assert receipt["source_changed_count"] == 0
    assert receipt["runtime_state_changed"] is True


@pytest.mark.parametrize("directory", ("memory", "docs", "skills", "tools"))
def test_report_allows_repairing_a_missing_state_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    directory: str,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    readme = workspace / "candidate/runtime-state" / directory / "README.md"
    readme.unlink()
    draft = _draft(workspace, changed_paths=[])
    with pytest.raises(EvolutionReportIssue) as caught:
        evolution_report(workspace, draft)
    assert caught.value.issues[0]["code"] == "invalid_runtime_state"
    assert "retry evolution-report" in caught.value.issues[0]["hint"]
    assert not (workspace / "scratch/evolution-report.json").exists()
    readme.write_text("repaired current index")
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
