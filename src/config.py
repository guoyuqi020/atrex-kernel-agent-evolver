"""Strict, repository-owned Evolver behavior configuration."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_EXECUTABLE = re.compile(r"^[A-Za-z0-9_.+-]+$")
_DEFAULT_EXECUTABLE = {
    "claude": "claude",
    "codex": "codex",
    "pi": "pi",
    "qodercli": "qodercli",
}


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{label} must be a string" + ("" if allow_empty else " and not blank"))
    if "\x00" in value:
        raise ValueError(f"{label} cannot contain NUL")
    return value


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _repository_file(repository: Path, value: object, label: str) -> Path:
    relative = Path(_text(value, label))
    if relative.is_absolute() or relative == Path(".") or ".." in relative.parts:
        raise ValueError(f"{label} must be a safe repository-relative path")
    path = repository.joinpath(*relative.parts)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must name a regular file")
    resolved = path.resolve()
    if not resolved.is_relative_to(repository.resolve()):
        raise ValueError(f"{label} escapes the Evolver repository")
    return resolved


@dataclass(frozen=True)
class EvolverConfig:
    """Fixed Agent framework and process bounds owned by one Evolver revision."""

    agent_backend: str
    agent_executable: str
    reasoning_effort: str
    session_settings: str
    prompt_path: Path
    agent_timeout_seconds: int
    max_stderr_chars: int
    max_output_manifest_bytes: int
    runtime_bound: bool = False
    model: str | None = None

    @classmethod
    def load(
        cls,
        repository: Path,
        environment: Mapping[str, str] | None = None,
    ) -> EvolverConfig:
        path = repository / "atrex-evolver.json"
        if path.is_symlink() or not path.is_file():
            raise ValueError("Evolver config must be a regular file")
        value = _object(json.loads(path.read_text(encoding="utf-8")), "Evolver config")
        expected = {
            "schema_version",
            "agent_backend",
            "agent_executable",
            "reasoning_effort",
            "session_settings",
            "prompt",
            "agent_timeout_seconds",
            "max_stderr_chars",
            "max_output_manifest_bytes",
        }
        if set(value) != expected:
            raise ValueError(
                f"Evolver config fields disagree with schema: {sorted(set(value) ^ expected)}"
            )
        if value["schema_version"] != 2:
            raise ValueError("unsupported Evolver config schema_version")
        backend = _text(value["agent_backend"], "agent_backend")
        if backend not in {"claude", "codex", "pi", "qodercli"}:
            raise ValueError(f"unsupported Evolver agent backend: {backend}")
        executable = _text(value["agent_executable"], "agent_executable")
        executable_path = Path(executable)
        if not executable_path.is_absolute() and _EXECUTABLE.fullmatch(executable) is None:
            raise ValueError("agent_executable must be an absolute path or a command name")
        effort = _text(value["reasoning_effort"], "reasoning_effort")
        if effort not in {"low", "medium", "high", "max"}:
            raise ValueError("unsupported reasoning_effort")
        settings = _text(value["session_settings"], "session_settings", allow_empty=True)
        binding = os.environ if environment is None else environment
        binding_keys = {
            "ATREX_AGENT_BACKEND",
            "ATREX_AGENT_MODEL",
            "ATREX_AGENT_REASONING_EFFORT",
            "ATREX_AGENT_SESSION_SETTINGS",
        }
        present = binding_keys.intersection(binding)
        if present and present != binding_keys:
            missing = sorted(binding_keys - present)
            raise ValueError(f"incomplete Runtime Agent binding; missing: {missing}")
        runtime_bound = bool(present)
        if runtime_bound:
            backend = _text(binding["ATREX_AGENT_BACKEND"], "Runtime agent backend")
            if backend not in {"claude", "codex", "pi", "qodercli"}:
                raise ValueError(f"unsupported Runtime Evolver agent backend: {backend}")
            effort = _text(
                binding["ATREX_AGENT_REASONING_EFFORT"],
                "Runtime reasoning effort",
            )
            if effort not in {"low", "medium", "high", "max"}:
                raise ValueError(f"unsupported Runtime reasoning effort: {effort}")
            settings = binding["ATREX_AGENT_SESSION_SETTINGS"]
            if "\x00" in settings:
                raise ValueError("Runtime session settings cannot contain NUL")
            runtime_model = binding["ATREX_AGENT_MODEL"].strip()
            if "\x00" in runtime_model:
                raise ValueError("Runtime model cannot contain NUL")
            model = runtime_model or None
            executable = _DEFAULT_EXECUTABLE[backend]
        else:
            model = None
        return cls(
            agent_backend=backend,
            agent_executable=executable,
            reasoning_effort=effort,
            session_settings=settings,
            prompt_path=_repository_file(repository, value["prompt"], "prompt"),
            agent_timeout_seconds=_positive_int(
                value["agent_timeout_seconds"], "agent_timeout_seconds"
            ),
            max_stderr_chars=_positive_int(value["max_stderr_chars"], "max_stderr_chars"),
            max_output_manifest_bytes=_positive_int(
                value["max_output_manifest_bytes"], "max_output_manifest_bytes"
            ),
            runtime_bound=runtime_bound,
            model=model,
        )
