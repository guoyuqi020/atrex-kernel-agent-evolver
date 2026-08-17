# Runtime integration

English | [中文](quickstart.zh.md)

The Bundle is not a standalone campaign tool. Runtime creates its workspace and invokes the declared
entrypoint once. For the current compatibility transport configure:

```json
{
  "agent_provider": "atrex-evolver-claude",
  "repository": "git@github.com:guoyuqi020/atrex-kernel-agent-evolver.git",
  "commit": "<full-evolver-commit-sha>",
  "git_executable": "/usr/bin/git",
  "fetch_timeout_seconds": 120,
  "max_archive_bytes": 16777216,
  "command_prefix": ["../.venv/bin/python"],
  "max_bundle_files": 1024,
  "max_bundle_bytes": 8388608,
  "model": "claude-default",
  "prompt": "Run the versioned Evolver Bundle once.",
  "prompt_transport": "stdin",
  "isolated_home_environment_keys": ["HOME"],
  "session_trace_relative_path": "scratch/evolver-session",
  "token_usage_report_relative_path": "scratch/token-usage.json"
}
```

Local repository and command-prefix paths are resolved relative to the Runtime configuration file;
production should use the separately controlled remote repository shown above.
Runtime fetches exactly the configured full commit, rejects links/submodules and unsafe archives,
seals the complete exported tree in its Artifact Store, validates the strict root manifest and
Bundle limits, and appends the manifest-owned entrypoint to the command prefix. The derived content
digest remains an integrity/provenance value; deployment identity is the Git commit. Pass Claude
credentials only through Runtime's explicit inherited-environment allowlist. The outer Worker
timeout must be greater than `agent_timeout_seconds` in `atrex-evolver.json` so the Bundle can reap
its child first.

Calling `src/main.py` without the exact Runtime manifest, paths, quota, and sentinel is expected to
fail closed.

On every started Agent session, `scratch/evolver-session/` contains the unredacted rendered Prompt
under `input/`, captured raw Claude stdout/stderr under `provider/`, plus `events.jsonl` and
`session.json` as normalized accounting and completion metadata. Runtime seals this entire directory
as the Session Artifact.
