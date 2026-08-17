# Runtime integration

English | [中文](quickstart.zh.md)

The Bundle is not a standalone campaign tool. Runtime creates its workspace and invokes the declared
entrypoint once. For the current compatibility transport configure:

```json
{
  "agent_provider": "atrex-evolver-claude",
  "agent_version": "<pinned-evolver-commit>",
  "model": "claude-default",
  "command_argv": ["../src/atrex-kernel-agent-evolver/src/main.py"],
  "prompt": "Run the versioned Evolver Bundle once.",
  "prompt_transport": "stdin",
  "isolated_home_environment_keys": ["HOME"],
  "session_trace_relative_path": "scratch/evolver-session",
  "token_usage_report_relative_path": "scratch/token-usage.json"
}
```

The command path is resolved relative to the Runtime configuration file. Production should mount a
pinned Evolver checkout read-only and use its absolute entrypoint path. Pass Claude credentials only
through Runtime's explicit inherited-environment allowlist. The outer Worker timeout must be greater
than `agent_timeout_seconds` in `atrex-evolver.json` so the Bundle can reap its child first.

Calling `src/main.py` without the exact Runtime manifest, paths, quota, and sentinel is expected to
fail closed.

On every started Agent session, `scratch/evolver-session/` contains the unredacted rendered Prompt
under `input/`, captured raw Claude stdout/stderr under `provider/`, plus `events.jsonl` and
`session.json` as normalized accounting and completion metadata. Runtime seals this entire directory
as the Session Artifact.
