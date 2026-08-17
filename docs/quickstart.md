# Runtime integration

English | [中文](quickstart.zh.md)

The Bundle is not a standalone campaign tool. Runtime creates its workspace and invokes the declared
entrypoint once. For the current compatibility transport configure:

```json
{
  "agent_provider": "atrex-evolver-claude",
  "bundle_root": "../src/atrex-kernel-agent-evolver",
  "bundle_sha256": "<canonical-bundle-sha256>",
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

Generate the digest after every intentional Bundle change:

```bash
atrex-kernel-agent-runtime digest-evolver-bundle \
  --path src/atrex-kernel-agent-evolver
```

Bundle and command-prefix paths are resolved relative to the Runtime configuration file. Runtime
validates the strict root manifest, rejects links and special files, hashes every behavior-bearing
regular file, compares that digest before startup, and appends the manifest-owned entrypoint to the
command prefix. Pass Claude credentials only through Runtime's explicit inherited-environment
allowlist. The outer Worker timeout must be greater than `agent_timeout_seconds` in
`atrex-evolver.json` so the Bundle can reap its child first.

Calling `src/main.py` without the exact Runtime manifest, paths, quota, and sentinel is expected to
fail closed.

On every started Agent session, `scratch/evolver-session/` contains the unredacted rendered Prompt
under `input/`, captured raw Claude stdout/stderr under `provider/`, plus `events.jsonl` and
`session.json` as normalized accounting and completion metadata. Runtime seals this entire directory
as the Session Artifact.
