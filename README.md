# Atrex Kernel Agent Evolver

English | [中文](README.zh.md)

Atrex Kernel Agent Evolver is a separately versioned, fixed Agent Bundle that proposes one
Optimizer-repository Challenger from one Runtime-authored Evolution workspace. It may revise Active,
reuse a visible historical revision unchanged, or revise a visible historical revision. It is not part of the
Optimizer revision it edits, is never visible to an Optimizer Session, and has no Gateway, Wiki,
evaluation, scheduling, retention, or promotion authority.

One invocation:

1. validates `EvolutionInputManifestV4` and every Runtime-owned path;
2. reads the complete Parent repository, the read-only visible Agent revision catalog, and one
   strict, Epoch-organized Evidence view containing all completed branches, Kernel artifacts, and
   Agent selection outcomes;
3. uses Runtime-injected tools to query frozen Agent/Kernel/Epoch history and, when deriving from
   history, atomically reset the writable Candidate to an eligible historical repository;
4. starts one fresh non-interactive Coding Agent with a repository-owned fixed Prompt;
5. selects `evolved`, `reuse`, or `evolve_from_history`, permitting changes only in the writable
   complete Candidate repository when a new revision is proposed and requiring the Runtime reset
   operation for a historical base;
6. emits an unredacted Session Artifact containing the rendered Prompt, retained Provider
   stream-json stdout/stderr, a normalized usage index, and a strict provider-token report; the
   high-frequency Claude `system/thinking_tokens` estimate event is intentionally omitted; and
7. validates the tagged Agent-authored `EvolutionOutputV3` before Runtime independently validates
   and seals the proposal.

## Agent backends

Version 2 supports `claude`, `codex`, `qodercli`, and `pi` through fresh non-interactive CLI
Adapters. The repository configuration supplies standalone defaults; Runtime injects the
authoritative Backend, Lineage-selected model, reasoning effort, and session settings for managed
runs. An empty model selects the Backend CLI default. Every Backend emits
the same normalized trace and provider-token contract. There is no token cutoff: usage remains
mandatory telemetry, while process wall time and output bounds remain safety limits. Every run
publishes `TokenUsageReportV1` with a null budget; Codex usage and raw rollout capture are obtained
from its isolated Session Ledger.

The Coding Agent has full design authority over `candidate/`: it may add, replace, reorganize, or
delete any Optimizer-owned content, including Agent architecture, backend configuration, prompts,
skills, workflows, tools, memory policy, DSL guidance, tests, and documentation. It may replace the
existing design wholesale when that is the best evidence-backed way to improve Kernel-optimization
effectiveness or efficiency. The resulting repository must still be a valid Optimizer Bundle. It
cannot change this Evolver, Runtime, or deployment policy because those files are absent or read-only.

The Evolution report may also list structured `unimplemented_capabilities`: useful Agent
capabilities, their expected Kernel-optimization benefit, and why the Evolver could not implement
them in the Candidate. These entries are advisory and grant no additional authority.

## Repository contract

- `atrex-evolver-bundle.json` declares the single `src/main.py` entrypoint.
- `atrex-evolver.json` supplies standalone Backend defaults, Prompt, timeout, and output bounds.
- `prompts/evolve.md` contains the evidence-driven Agent-engineering procedure.
- Runtime supplies its Agent binding, `ATREX_EVOLUTION_INPUT`, `ATREX_EVOLUTION_CANDIDATE`,
  `ATREX_EVOLUTION_OUTPUT`, and `ATREX_TOKEN_USAGE_REPORT` plus explicitly
  allowed provider credentials and isolated-home variables.
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
