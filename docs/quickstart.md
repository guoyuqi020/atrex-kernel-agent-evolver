# Runtime integration

English | [中文](quickstart.zh.md)

The Bundle is not a standalone campaign tool. Runtime creates its workspace and invokes the declared
entrypoint once. For the current compatibility transport configure:

```json
{
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
    "inherit": ["PATH", "ANTHROPIC_AUTH_TOKEN"]
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
digest remains an integrity/provenance value; deployment identity is the Git commit. Pass Claude
credentials only through Runtime's explicit inherited-environment allowlist. The outer Worker
timeout must be greater than `agent_timeout_seconds` in `atrex-evolver.json` so the Bundle can reap
its child first.

Provider, model, and versioned Prompt configuration are intentionally absent from Runtime JSON; the
Evolver repository owns them. Calling `src/main.py` without the exact Runtime manifest, paths,
usage-report destination, and sentinel is expected to fail closed.

On every started Agent session, `scratch/evolver-session/` contains the unredacted rendered Prompt
under `input/`, captured raw Claude stdout/stderr under `provider/`, plus `events.jsonl` and
`session.json` as normalized accounting and completion metadata. Runtime seals this entire directory
as the Session Artifact.

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
```

These commands query only the frozen local snapshot and return JSON; they do not contact Runtime.

No `ATREX_TOKEN_BUDGET` is supplied. The usage report remains mandatory and uses
`budget_tokens=null` and `budget_exhausted=false`; incomplete provider accounting fails the run.
