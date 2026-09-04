# Atrex Kernel Agent Evolver

English | [中文](README.zh.md)

Atrex Kernel Agent Evolver is a separately versioned, fixed Agent Bundle that proposes one
Optimizer-repository Challenger from one Runtime-authored Evolution workspace. It may revise Active,
reuse a visible historical revision unchanged, or revise a visible historical revision. It is not part of the
Optimizer revision it edits, is never visible to an Optimizer Session, and has no Gateway, Wiki,
evaluation, scheduling, retention, or promotion authority.

One invocation:

1. validates Runtime-private `EvolutionInputManifestV10` and every Runtime-owned path;
2. reads the complete Parent repository, current participant repositories, historical Agent
   repositories, optimization summaries, latest-Epoch Conversations, and runtime state directly
   from the frozen filesystem;
3. when deriving from history, replaces writable Candidate source with the selected historical
   Agent source and may synthesize one common state seed from visible historical state;
4. starts one fresh non-interactive Coding Agent with a repository-owned fixed Prompt;
5. selects `evolved`, `reuse`, or `evolve_from_history`, permitting changes only in writable
   `candidate/` when a new revision is proposed;
6. emits an unredacted Session Artifact containing the rendered Prompt, retained Provider
   stream-json stdout/stderr, a normalized usage index, and a strict provider-token report; the
   high-frequency Claude `system/thinking_tokens` estimate event is intentionally omitted; and
7. exposes the local `evolution-report` command, which returns structured repair guidance on a
   failed draft and atomically publishes the first valid `EvolutionOutput`; Runtime then
   independently validates and seals the proposal.

## Agent backends

Version 2 supports `claude`, `codex`, `qodercli`, and `pi` through fresh non-interactive CLI
Adapters. The repository configuration supplies standalone defaults; Runtime injects the
authoritative Backend, Lineage-selected model, reasoning effort, and session settings for managed
runs. An empty model selects the Backend CLI default. Every Backend emits
the same normalized trace and provider-token contract. There is no token cutoff: usage remains
mandatory telemetry, while process wall time and output bounds remain safety limits. Every run
publishes `TokenUsageReportV1` with a null budget; Codex usage and raw rollout capture are obtained
from its isolated Session Ledger.

Claude uses a fresh session ID with native persistence enabled; it never resumes prior context. Its native main/child JSONLs are retained under `provider/claude-session.raw-jsonl` and `provider/claude-subagents/`, including on timeout or failure. `events.jsonl` contains one latest usage record per response, with `message_id` and `source_path` for joining back to tool calls. Print-stream counters are provisional; repeated updates replace earlier counters. `session.json.response_usage_complete` is true only when native response counters reconcile with the terminal bill. Gaps remain partial with diagnostics; the terminal bill is not replaced with estimates. Do not sum native and stdout copies, or add the terminal bill to response usage.

The sealed `conversation.jsonl` is a reading view: Claude native content takes precedence over duplicate stdout messages. Distinct thinking/text/tool blocks remain intact; uncovered stdout content, diagnostics, compaction boundaries, and terminal results remain visible. Duplicate initial prompts and native queue/title/file-history bookkeeping are omitted from this view only. The live view still follows stdout until sealing. Raw Provider files and the normalized usage index are unchanged.

The Coding Agent may modify any Agent-owned content in the unified `candidate/` Bundle, including
implementation, configuration, prompts, memory, knowledge, skills, tools, and hooks. Each adaptive
directory has one effective copy and a maintained README index. Runtime seals the complete Bundle
and its adaptive checkpoint for subsequent optimization. Input Bundles and per-Trajectory resources
are read-only evidence. Evolver, Runtime, and deployment policies are outside the Candidate.

## Repository contract

- `atrex-evolver-bundle.json` declares the single `src/main.py` entrypoint.
- `atrex-evolver.json` supplies standalone Backend defaults, Prompt, timeout, and output bounds.
- `prompts/evolve.md` contains the evidence-driven Agent-engineering procedure.
- Runtime supplies its Agent binding, in-memory Evolution manifest and Evidence Prompt, workspace
  paths, and `ATREX_TOKEN_USAGE_REPORT` plus explicitly allowed provider credentials and
  isolated-home variables.
- Runtime stdin must contain only `Run the versioned Evolver Bundle once.`; it cannot replace the
  versioned Prompt.

See [Design](docs/design.md) and [Runtime usage](docs/quickstart.md).

## Development

```bash
python -m pytest -q
ruff check src tests
mypy src tests
python -m compileall -q src tests
```

This project is licensed under the [Apache License 2.0](LICENSE).
