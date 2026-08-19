# Atrex Kernel Agent Evolver

English | [中文](README.zh.md)

Atrex Kernel Agent Evolver is a separately versioned, fixed Agent Bundle that proposes one complete
Optimizer-repository Challenger from one Runtime-authored Evolution workspace. It is not part of the
Optimizer revision it edits, is never visible to an Optimizer Session, and has no Gateway, Wiki,
evaluation, scheduling, retention, or promotion authority.

One invocation:

1. validates `EvolutionInputManifestV4` and every Runtime-owned path;
2. reads the complete Parent repository, the read-only visible Agent revision catalog, and one
   strict, Epoch-organized Evidence view containing all completed branches, Kernel artifacts, and
   Agent selection outcomes;
3. uses Runtime-injected read-only tools to query the frozen Agent/Kernel/Epoch history;
4. starts one fresh non-interactive Coding Agent with a repository-owned fixed Prompt;
5. permits changes only in the writable complete Candidate repository;
6. emits an unredacted Session Artifact containing the rendered Prompt, captured raw Claude
   stream-json stdout/stderr, a normalized usage index, and a strict provider-token report; and
7. validates the Agent-authored `EvolutionOutputV2` before Runtime independently validates and seals
   the Candidate.

## Current backend

Version 1 implements Claude CLI stream-json execution with live provider-token accounting. It has no
token cutoff: provider usage remains mandatory telemetry, while process wall time and output bounds
remain safety limits. It always publishes `TokenUsageReportV1` with a null budget. Codex is
deliberately not claimed yet: a conforming Codex backend must observe its Session Ledger and publish
the same complete accounting.

The Coding Agent may change any valid Optimizer-owned file under `candidate/`, including its Agent
backend configuration, Prompt, workflow, tool bindings, memory policy, and DSL guidance. It cannot
change this Evolver, Runtime, or deployment policy because those files are absent or read-only.

## Repository contract

- `atrex-evolver-bundle.json` declares the single `src/main.py` entrypoint.
- `atrex-evolver.json` fixes backend behavior, Prompt, timeout, and output bounds.
- `prompts/evolve.md` contains the evidence-driven Agent-engineering procedure.
- Runtime supplies only `ATREX_EVOLUTION_INPUT`, `ATREX_EVOLUTION_CANDIDATE`,
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
