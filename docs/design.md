# Evolver Bundle Design

English | [中文](design.zh.md)

## 1. Role and isolation

The Evolver is a separately versioned worker implementation, not a component inside the Optimizer
Candidate. Runtime launches it in a fresh workspace and process after an Epoch checkpoint exists. The Optimizer
never receives the Evolver repository, configuration, Prompt, trace, credentials, or process state.

Runtime materializes this workspace:

```text
run-<uuid>/
├── evolution-input.json       # read-only EvolutionInputManifestV4
├── input/
│   ├── parent/                # read-only complete Optimizer repository
│   ├── agents/                # read-only visible Agent revision repositories
│   │   └── agentrev_<id>/
│   └── evidence/              # read-only EvidenceViewManifestV1 tree
│       ├── manifest.json      # role=evolver; all completed branches
│       ├── bootstrap/
│       └── epochs/
│           └── <epoch>/
│               ├── summary.json
│               ├── branches/ # Active and every Challenger Attempt history
│               ├── kernels/  # exact Kernel artifacts plus index.json
│               └── evolution/# every Challenger Evolver trace
├── runtime-tools/              # frozen Runtime-owned inspection and Candidate reset
│   ├── evolver_tools.py
│   ├── catalog.json        # exact vN/agent-vN lineage catalog
│   └── kernels/            # every historical exact Kernel artifact
├── candidate/                 # writable complete copy of selected base
└── scratch/                   # writable report, base record, trace, and isolated Agent state
```

Runtime path validation and process capabilities are the current trust boundary; Prompt instructions
are defense in depth. The Evolver receives no Runtime Gateway/Wiki capability and must not evaluate
GPU Kernels. OS sandboxing is intentionally deferred and must be added before treating hostile Agent
code as contained.

## 2. Versioned behavior

The full Git commit is the deployment behavior identity, matching the Optimizer Base convention.
Runtime fetches exactly that commit, validates the Git tree, safely exports it, and seals the whole
snapshot into content-addressed storage before launch. `atrex-evolver-bundle.json` declares the
single entrypoint; Runtime additionally derives a complete-tree content digest for integrity and
provenance. Links, submodules, special files, unsafe archives, or limit overflow are rejected. A
deployment may pin a different commit later, but one running Epoch never mutates this repository.

The fixed stdin sentinel prevents deployment configuration from silently replacing the versioned
Prompt while retaining compatibility with Runtime's current process transport.

## 3. Input and output

The entrypoint accepts only Evolution manifest schema 4 with the exact fixed path map. The manifest
identifies exactly one Parent and a nonempty, duplicate-free `visible_agents` catalog. Runtime
includes the retained Lineage Agent history plus Challengers already created earlier in the current
Epoch; each catalog entry supplies its Parent link, creator, relationship, and current-Epoch
Challenger ordinal when applicable, and resolves to one read-only repository under `input/agents/`. It also
requires a strict Evidence view with the matching lineage checkpoint, `role="evolver"`, all branches
of every completed Epoch, and no current Epoch. Completed summaries retain the Active, Challenger,
winner Agent, starting Kernel, and best Kernel identities. Branch trees retain every Attempt and
authoritative outcome; `kernels/` materializes each referenced exact Kernel artifact once. It binds
each environment path to that manifest and rejects
links and path escapes. A usage-report destination is mandatory, but no token budget is accepted.

Runtime also injects a snapshot-scoped inspection and Candidate-control client plus Catalog under
`runtime-tools/`. The Catalog supplies exact Lineage-local Kernel and Agent version labels,
provenance, evaluation facts, and paths to every historical Kernel Artifact. The client provides
bounded JSON `history`, `branches`, `attempts`, `kernels`, `kernel-read`, `agents`, `agent-diff`, and
`trace-paths` commands. Its sole mutation, `candidate-reset --base <agentrev>`, accepts only a
manifest entry marked `lineage_history`, stages a complete writable copy, atomically replaces
`candidate/`, and records the selected base in `scratch/candidate-base.json`. It reads only this
frozen workspace and confers no Registry, Gateway, Wiki, evaluation, or promotion authority.

The Evidence structure Prompt Fragment is authored and materialized by Runtime. This repository
only verifies its fixed path and Manifest-bound Digest before appending it to the final Prompt.

The Coding Agent writes tagged `EvolutionOutputV3`. It may derive a new revision from Active,
reuse one visible historical revision unchanged, or derive a new revision from one visible
historical revision. New-revision proposals include an exact sorted changed-path declaration
relative to the selected base. Every mode may include bounded structured
`unimplemented_capabilities`, recording a capability, its expected Kernel-optimization benefit, and
the concrete reason it could not be implemented. Runtime preserves these untrusted advisory entries
in Evolution Evidence so later Evolvers can inspect them; they confer no authority and do not change
selection. Runtime remains authoritative: it validates frozen visibility,
requires the Candidate-base record to match the proposal mode, independently hashes Base and
Candidate, verifies the actual changed set and Bundle policy, seals
per-Epoch proposal provenance, and runs the configured Active-versus-Challenger-pool evaluation.
Revision parentage remains a tree; reuse and promotion are participation events, not ancestry edges.

## 4. Token and process ownership

Claude, Codex, QoderCLI, and Pi use separate non-interactive command/stream Adapters with one common
Session result. Claude and Qoder parse stream-json usage, Pi aggregates settled message/compaction
usage, and Codex observes its isolated Session Ledger and captures the raw rollout. Every Adapter
normalizes uncached input, output, cache reads, and cache writes exactly once. Token count never
terminates the child. Outer SIGTERM/SIGINT is relayed to that group; timeout and captured
stdout/stderr are bounded. The report uses a null budget and fails closed when a completed model
request lacks complete provider buckets.

The Session Artifact preserves the final rendered Prompt at `input/prompt.md`, the captured Provider
stream at `provider/stdout.stream-json`, and captured Provider stderr at
`provider/stderr.log`. `conversation.jsonl` combines the exact Runtime input, every retained
Provider stdout event, any raw Codex rollout, and the terminal capture status. It explicitly marks
Provider-managed system instructions unavailable when the CLI does not export them. Runtime and
Evolver apply no redaction or text rewriting to retained events. They omit only the high-frequency
Claude `system/thinking_tokens` estimate event and disclose that selection in
`session.json.provider_event_filters`; final authoritative usage remains in `events.jsonl`.
Reasoning, tool arguments and results, credentials, or other sensitive fields emitted
by the Provider therefore remain present. `events.jsonl` is an additional normalized usage index;
`session.json` records termination state and whether raw Provider capture avoided truncation. The
configured stdout/stderr limits remain safety limits: overflow fails the Session and marks the raw
stream incomplete rather than silently presenting a truncated stream as complete. Environment
credentials are not proactively copied when the Provider did not emit them.

## 5. Evolution of the Evolver

This first repository is fixed per deployment Git commit. A future self-evolution layer may propose
a new Evolver commit, but it must use a separate evaluation and promotion policy from Optimizer evolution.
It must never let an unpromoted Evolver rewrite itself in place or change the trusted Runtime boundary.
