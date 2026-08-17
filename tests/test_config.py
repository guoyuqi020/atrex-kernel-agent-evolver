from __future__ import annotations

import json
from pathlib import Path

import pytest

from config import EvolverConfig


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "evolver"
    (repository / "prompts").mkdir(parents=True)
    (repository / "prompts/evolve.md").write_text("fixed prompt\n", encoding="utf-8")
    (repository / "atrex-evolver.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "agent_backend": "claude",
                "agent_executable": "claude",
                "model": "",
                "reasoning_effort": "max",
                "session_settings": "",
                "prompt": "prompts/evolve.md",
                "agent_timeout_seconds": 60,
                "max_stdout_chars": 1000,
                "max_stderr_chars": 1000,
                "max_output_manifest_bytes": 4096,
            }
        ),
        encoding="utf-8",
    )
    return repository


def test_config_loads_fixed_claude_backend(tmp_path: Path) -> None:
    config = EvolverConfig.load(_repository(tmp_path))

    assert config.agent_backend == "claude"
    assert config.prompt_path.name == "evolve.md"


def test_config_rejects_unaccounted_backend(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    value = json.loads((repository / "atrex-evolver.json").read_text())
    value["agent_backend"] = "codex"
    (repository / "atrex-evolver.json").write_text(json.dumps(value))

    with pytest.raises(ValueError, match="supports only"):
        EvolverConfig.load(repository)


def test_config_rejects_prompt_escape(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    value = json.loads((repository / "atrex-evolver.json").read_text())
    value["prompt"] = "../outside.md"
    (repository / "atrex-evolver.json").write_text(json.dumps(value))

    with pytest.raises(ValueError, match="safe repository-relative"):
        EvolverConfig.load(repository)

