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
                "schema_version": 2,
                "agent_backend": "claude",
                "agent_executable": "claude",
                "reasoning_effort": "max",
                "session_settings": "",
                "prompt": "prompts/evolve.md",
                "agent_timeout_seconds": 60,
                "max_stderr_chars": 1000,
                "max_output_manifest_bytes": 4096,
            }
        ),
        encoding="utf-8",
    )
    return repository


def test_config_loads_bundle_default_backend(tmp_path: Path) -> None:
    config = EvolverConfig.load(_repository(tmp_path))

    assert config.agent_backend == "claude"
    assert config.prompt_path.name == "evolve.md"


@pytest.mark.parametrize("backend", ("claude", "codex", "qodercli", "pi"))
def test_runtime_binding_selects_every_supported_backend(
    tmp_path: Path,
    backend: str,
) -> None:
    repository = _repository(tmp_path)
    config = EvolverConfig.load(
        repository,
        {
            "ATREX_AGENT_BACKEND": backend,
            "ATREX_AGENT_MODEL": "runtime-model",
            "ATREX_AGENT_REASONING_EFFORT": "high",
            "ATREX_AGENT_SESSION_SETTINGS": "",
        },
    )

    assert config.agent_backend == backend
    assert config.model == "runtime-model"
    assert config.agent_executable == backend
    assert config.reasoning_effort == "high"
    assert config.runtime_bound is True


def test_config_rejects_incomplete_runtime_binding(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="incomplete Runtime Agent binding"):
        EvolverConfig.load(
            _repository(tmp_path),
            {"ATREX_AGENT_BACKEND": "codex"},
        )


def test_config_rejects_prompt_escape(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    value = json.loads((repository / "atrex-evolver.json").read_text())
    value["prompt"] = "../outside.md"
    (repository / "atrex-evolver.json").write_text(json.dumps(value))

    with pytest.raises(ValueError, match="safe repository-relative"):
        EvolverConfig.load(repository)


def test_runtime_session_timeout_overrides_the_bundle_agent_timeout(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    assert EvolverConfig.load(repository).agent_timeout_seconds == 60

    bound = EvolverConfig.load(
        repository,
        environment={"ATREX_SESSION_TIMEOUT_SECONDS": "10800.0"},
    )

    assert bound.agent_timeout_seconds == 10_800


@pytest.mark.parametrize("value", ("0", "-1", "abc", ""))
def test_runtime_session_timeout_must_be_a_positive_number(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValueError):
        EvolverConfig.load(
            _repository(tmp_path),
            environment={"ATREX_SESSION_TIMEOUT_SECONDS": value},
        )
