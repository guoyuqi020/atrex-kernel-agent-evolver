# Runtime integration

English | [中文](quickstart.zh.md)

The Bundle is not a standalone campaign tool. Runtime creates its workspace and invokes the declared
entrypoint once. For the current compatibility transport configure:

```json
{
  "agent_backend": "claude",
  "reasoning_effort": "max",
  "session_settings": "",
  "repository": "git@github.com:guoyuqi020/atrex-kernel-agent-evolver.git",
  "commit": "<full-evolver-commit-sha>",
  "git_executable": "/usr/bin/git",
  "fetch_timeout_seconds": 120,
  "max_archive_bytes": 16777216,
  "command_prefix": [".venv/bin/python"],
  "max_bundle_files": 1024,
  "max_bundle_bytes": 8388608,
  "environment": {
    "values": {},
    "inherit": ["PATH"],
    "inherit_optional": ["ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "CODEX_HOME"]
  },
  "isolated_home_environment_keys": ["HOME"],
  "session_trace_relative_path": "scratch/evolver-session",
  "token_usage_report_relative_path": "scratch/token-usage.json",
  "timeout_seconds": 1800,
  "terminate_grace_seconds": 10,
  "max_diagnostic_bytes": 131072,
  "max_output_manifest_bytes": 16384
}
```

Local repository and command-prefix paths are resolved relative to the Runtime configuration file;
production should use the separately controlled remote repository shown above.
Runtime fetches exactly the configured full commit, rejects links/submodules and unsafe archives,
seals the complete exported tree in its Artifact Store, validates the strict root manifest and
Bundle limits, and appends the manifest-owned entrypoint to the command prefix. The derived content
digest remains an integrity/provenance value; deployment identity is the Git commit. Pass the
selected Backend's credentials only through Runtime's explicit inherited-environment allowlist. The outer Worker
timeout must be greater than `agent_timeout_seconds` in `atrex-evolver.json` so the Bundle can reap
its child first.

Runtime binds Backend, the Lineage-selected model, reasoning effort, and Backend-specific session
settings. An empty model selects the Backend CLI default. The Evolver
repository owns the Adapter implementation and versioned Prompt. Calling `src/main.py` without the exact Runtime manifest, paths,
usage-report destination, and sentinel is expected to fail closed.

Every Agent session creates `scratch/evolver-session/` before the Provider starts. The unredacted
Prompt, raw Provider stdout/stderr, and `conversation.jsonl` are inspectable and updated while the
session runs. `session.json` reports `state: running` until completion; the
`.runtime-live-session` marker identifies an unsealed or interrupted projection. On normal exit the
Bundle replaces the projection with the complete transcript, normalized `events.jsonl`, and final
`session.json`, then Runtime seals the directory as the Session Artifact. A catchable failure keeps
the available partial transcript with `state: interrupted`.

The rendered Session context contains the exact Python command for the Runtime-injected inspection
client. From the Evolution workspace, append one of these subcommands:

```bash
<injected-python> runtime-tools/evolver_tools.py history
<injected-python> runtime-tools/evolver_tools.py branches --epoch 1
<injected-python> runtime-tools/evolver_tools.py attempts --epoch 1 --branch challenger-0001
<injected-python> runtime-tools/evolver_tools.py kernels
<injected-python> runtime-tools/evolver_tools.py kernel-read --revision kernelrev_<id>
<injected-python> runtime-tools/evolver_tools.py agents
<injected-python> runtime-tools/evolver_tools.py agent-diff --base agentrev_<id> --candidate agentrev_<id>
<injected-python> runtime-tools/evolver_tools.py trace-paths --epoch 1
<injected-python> runtime-tools/evolver_tools.py candidate-reset --base agentrev_<historical-id>
```

All commands use only the frozen local snapshot and return JSON; they do not contact Runtime.
`candidate-reset` is the sole mutation: it is required for `evolve_from_history`, accepts only
completed Lineage history, and atomically replaces only `candidate/` while recording its base.

No usage budget is supplied. The schema-v2 usage report remains mandatory with `budget=null` and
`budget_exhausted=false`. QoderCLI records credits; Claude, Codex, and Pi record provider tokens.
Incomplete accounting in the selected provider-native unit fails the run.
