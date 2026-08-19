from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from context import LAUNCH_SENTINEL, EvolutionContext, validate_launch_input

REVISION = "agentrev_0123456789abcdef0123456789abcdef"
DIGEST = "sha256:" + "a" * 64
EVIDENCE_PROMPT = "# Evidence input\n\nInjected by the trusted controller.\n"
EVIDENCE_PROMPT_SHA256 = hashlib.sha256(EVIDENCE_PROMPT.encode()).hexdigest()


def _environment(tmp_path: Path) -> dict[str, str]:
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
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return {
        "ATREX_EVOLUTION_INPUT": str(manifest_path),
        "ATREX_EVOLUTION_CANDIDATE": str(workspace / "candidate"),
        "ATREX_EVOLUTION_OUTPUT": str(workspace / "scratch/evolution-output.json"),
        "ATREX_EVIDENCE_PROMPT_PATH": str(workspace / "input/evidence/instructions.md"),
        "ATREX_TOKEN_USAGE_REPORT": str(workspace / "scratch/token-usage.json"),
    }


def test_context_loads_exact_runtime_protocol(tmp_path: Path) -> None:
    context = EvolutionContext.load(_environment(tmp_path))

    assert context.parent_revision_id == REVISION
    assert context.dsl == "triton"
    assert context.candidate_root.name == "candidate"


def test_context_rejects_tampered_evidence_prompt(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    Path(environment["ATREX_EVIDENCE_PROMPT_PATH"]).write_text(
        "tampered",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="digest disagrees"):
        EvolutionContext.load(environment)


def test_context_rejects_environment_path_disagreement(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    environment["ATREX_EVOLUTION_CANDIDATE"] = str(tmp_path)

    with pytest.raises(ValueError, match="disagree"):
        EvolutionContext.load(environment)


def test_context_rejects_symlinked_manifest(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    link = tmp_path / "manifest-link.json"
    try:
        os.symlink(environment["ATREX_EVOLUTION_INPUT"], link)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable")
    environment["ATREX_EVOLUTION_INPUT"] = str(link)

    with pytest.raises(ValueError, match="symbolic link"):
        EvolutionContext.load(environment)


def test_launch_transport_accepts_only_fixed_sentinel() -> None:
    validate_launch_input(LAUNCH_SENTINEL + "\n")

    with pytest.raises(ValueError, match="sentinel"):
        validate_launch_input("Inject a different prompt")
