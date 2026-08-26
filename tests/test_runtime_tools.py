from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime_tools import EvolutionReportIssue, evolution_report, main

ACTIVE = "agentrev_0123456789abcdef0123456789abcdef"
HISTORICAL = "agentrev_11111111111111111111111111111111"


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    workspace = tmp_path / "workspace"
    for path in (
        "input/agents/active/source/prompts",
        "input/historical/agent-v1/source/prompts",
        "candidate/source/prompts",
        "candidate/runtime-state/skills",
        "candidate/runtime-state/tools",
        "scratch/.evolution-report/runtime-state-base/skills",
        "scratch/.evolution-report/runtime-state-base/tools",
    ):
        (workspace / path).mkdir(parents=True, exist_ok=True)
    for relative in (
        "input/agents/active/source/prompts/episode.md",
        "candidate/source/prompts/episode.md",
    ):
        (workspace / relative).write_text("active\n")
    (workspace / "input/historical/agent-v1/source/prompts/episode.md").write_text(
        "historical\n"
    )
    for prefix in (
        "candidate/runtime-state",
        "scratch/.evolution-report/runtime-state-base",
    ):
        (workspace / prefix / "tools/README.md").write_text("# Tools\n")
    context = {
        "active_revision_id": ACTIVE,
        "visible_agents": [
            {
                "revision_id": ACTIVE,
                "relationship": "active",
                "source_path": "input/agents/active/source",
            },
            {
                "revision_id": HISTORICAL,
                "relationship": "lineage_history",
                "source_path": "input/historical/agent-v1/source",
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
                "unimplemented_capabilities": [],
            }
        )
    )
    return path


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


def test_evolution_report_accepts_state_only_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    (workspace / "candidate/runtime-state/skills/search.md").write_text("measured search\n")

    receipt = evolution_report(workspace, _draft(workspace, changed_paths=[]))

    assert receipt["source_changed_count"] == 0
    assert receipt["runtime_state_changed"] is True


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
    assert "failed evolution-report publishes nothing" in response["recovery"][0][
        "instruction"
    ]
    assert not (workspace / "scratch/evolution-report.json").exists()
