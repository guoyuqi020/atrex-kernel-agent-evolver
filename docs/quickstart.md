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
Prompt, retained Provider stdout/stderr, and `conversation.jsonl` are inspectable and updated while the
session runs. `session.json` reports `state: running` until completion; the
`.runtime-live-session` marker identifies an unsealed or interrupted projection. On normal exit the
Bundle replaces the projection with the retained-event transcript, normalized `events.jsonl`, and final
`session.json`, then Runtime seals the directory as the Session Artifact. A catchable failure keeps
the available partial transcript with `state: interrupted`. The high-frequency Claude
`system/thinking_tokens` estimate event is omitted and declared in
`session.json.provider_event_filters`.

The rendered Session context lists every authorized Agent repository, optimization summary, Session
directory, and runtime-state directory. Evolver reads those immutable files directly. Writable
`candidate/source/` mirrors Active Source. `candidate/runtime-state/{skills,tools}/` starts from the
latest completed Epoch's winning branch and best-Kernel Trajectory, using its terminal State after
the last Attempt in that Epoch. The next Epoch's Active Branch uses the same State seed. When no
terminal checkpoint exists, Runtime falls back to that Trajectory's Epoch-start State, the revision
seed, and the empty default.
For `evolve_from_history`, Evolver replaces Source with the selected historical Source
and may curate the common seed from visible historical Trajectories. Runtime validates the declared
base and the Source/State Diff independently. Every new revision seals both components as one
logical Agent Bundle.

Maintain `scratch/evolution-report-draft.json`, then submit it with:

```bash
python input/evolver/src/runtime_tools.py evolution-report \
  --request scratch/evolution-report-draft.json
```

On error, correct the draft using the returned `issues`, `request_schema`, and `recovery`, then
retry. The first success publishes `scratch/evolution-report.json`; do not call the tool again.

No usage budget is supplied. The schema-v2 usage report remains mandatory with `budget=null` and
`budget_exhausted=false`. QoderCLI records credits; Claude, Codex, and Pi record provider tokens.
Incomplete accounting in the selected provider-native unit fails the run.
