from __future__ import annotations

import json
from pathlib import Path

import pytest

from report import EvolutionOutputContractError, validate_evolution_output
from session import safe_error

ACTIVE = "agentrev_0123456789abcdef0123456789abcdef"
HISTORICAL = "agentrev_11111111111111111111111111111111"
VISIBLE = frozenset((ACTIVE, HISTORICAL))


def _validate(path: Path) -> dict[str, object]:
    return validate_evolution_output(
        path,
        active_revision_id=ACTIVE,
        visible_revision_ids=VISIBLE,
        historical_revision_ids=frozenset((HISTORICAL,)),
        max_bytes=4096,
    )


def test_output_requires_sorted_safe_changed_paths(tmp_path: Path) -> None:
    path = tmp_path / "output.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "proposal_type": "evolved",
                "base_revision_id": ACTIVE,
                "hypothesis": "Tighten the search policy.",
                "expected_effect": "Fewer repeated unsuccessful changes.",
                "changed_paths": ["src/workflow.py", "prompts/episode.md"],
            }
        )
    )
    with pytest.raises(ValueError, match="sorted"):
        _validate(path)


@pytest.mark.parametrize(
    "value",
    [
        {
            "schema_version": 3,
            "proposal_type": "evolved",
            "base_revision_id": ACTIVE,
            "hypothesis": "Tighten the search policy.",
            "expected_effect": "Fewer repeated unsuccessful changes.",
            "changed_paths": ["prompts/episode.md", "src/workflow.py"],
            "unimplemented_capabilities": [
                {
                    "capability": "Automatic profiler-guided tool synthesis.",
                    "expected_benefit": "Spend fewer attempts on irrelevant bottlenecks.",
                    "reason_unimplemented": "No profiler capability is available to the Evolver.",
                }
            ],
        },
        {
            "schema_version": 3,
            "proposal_type": "reuse",
            "candidate_revision_id": HISTORICAL,
            "hypothesis": "Retry a previously strong design.",
            "expected_effect": "Recover its prior search behavior.",
        },
        {
            "schema_version": 3,
            "proposal_type": "evolve_from_history",
            "base_revision_id": HISTORICAL,
            "hypothesis": "Repair the historical design's one weak step.",
            "expected_effect": "Retain its strengths with fewer repeated trials.",
            "changed_paths": ["prompts/episode.md"],
        },
    ],
)
def test_output_accepts_all_strict_protocol_v3_modes(
    tmp_path: Path, value: dict[str, object]
) -> None:
    path = tmp_path / "output.json"
    path.write_text(json.dumps(value))
    assert _validate(path) == value


def test_output_rejects_revision_outside_frozen_visibility(tmp_path: Path) -> None:
    path = tmp_path / "output.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "proposal_type": "reuse",
                "candidate_revision_id": "agentrev_22222222222222222222222222222222",
                "hypothesis": "Unknown Agent.",
                "expected_effect": "None.",
            }
        )
    )
    with pytest.raises(ValueError, match="outside the frozen"):
        _validate(path)


def test_output_rejects_malformed_unimplemented_capability(tmp_path: Path) -> None:
    path = tmp_path / "output.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "proposal_type": "reuse",
                "candidate_revision_id": HISTORICAL,
                "hypothesis": "Retry a previously strong design.",
                "expected_effect": "Recover its prior search behavior.",
                "unimplemented_capabilities": [
                    {
                        "capability": "Profiler-guided search.",
                        "expected_benefit": "Select useful hypotheses faster.",
                    }
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="fields are invalid"):
        _validate(path)


def test_contract_violations_name_the_offending_field(tmp_path: Path) -> None:
    path = tmp_path / "output.json"
    # The shape a real Evolver produced: prose strings where objects are required.
    path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "proposal_type": "evolved",
                "base_revision_id": ACTIVE,
                "hypothesis": "Bundle reusable skills into the sealed repository.",
                "expected_effect": "Spend less budget rebuilding apparatus.",
                "changed_paths": ["prompts/episode.md"],
                "unimplemented_capabilities": [
                    "Cross-attempt persistence: no handoff mechanism exists by design.",
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(EvolutionOutputContractError) as raised:
        _validate(path)

    assert "unimplemented_capabilities[0]" in str(raised.value)
    assert safe_error(raised.value)["message"] == str(raised.value)


def test_unknown_failures_still_report_only_their_type() -> None:
    assert safe_error(RuntimeError("upstream detail")) == {"error_type": "RuntimeError"}
