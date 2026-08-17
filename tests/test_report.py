from __future__ import annotations

import json
from pathlib import Path

import pytest

from report import validate_evolution_output

REVISION = "agentrev_0123456789abcdef0123456789abcdef"


def test_output_requires_sorted_safe_changed_paths(tmp_path: Path) -> None:
    path = tmp_path / "output.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "parent_revision_id": REVISION,
                "hypothesis": "Tighten the search policy.",
                "expected_effect": "Fewer repeated unsuccessful changes.",
                "changed_paths": ["src/workflow.py", "prompts/episode.md"],
            }
        )
    )

    with pytest.raises(ValueError, match="sorted"):
        validate_evolution_output(
            path,
            expected_parent_revision_id=REVISION,
            max_bytes=4096,
        )


def test_output_accepts_strict_protocol_v2(tmp_path: Path) -> None:
    path = tmp_path / "output.json"
    value = {
        "schema_version": 2,
        "parent_revision_id": REVISION,
        "hypothesis": "Tighten the search policy.",
        "expected_effect": "Fewer repeated unsuccessful changes.",
        "changed_paths": ["prompts/episode.md", "src/workflow.py"],
    }
    path.write_text(json.dumps(value))

    assert (
        validate_evolution_output(
            path,
            expected_parent_revision_id=REVISION,
            max_bytes=4096,
        )
        == value
    )
