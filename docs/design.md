# Evolver Bundle Design

English | [中文](design.zh.md)

## 1. Role and isolation

The Evolver is a separately versioned worker implementation, not a component inside the Optimizer
Candidate. Runtime launches it in a fresh workspace and process after an Epoch checkpoint exists. The Optimizer
never receives the Evolver repository, configuration, Prompt, trace, credentials, or process state.

Runtime materializes this workspace:

```text
run-<uuid>/
├── evolution-input.json       # read-only EvolutionInputManifestV3
├── input/
│   ├── parent/                # read-only complete Optimizer repository
│   ├── agents/                # read-only visible Agent revision repositories
│   │   └── agentrev_<id>/
│   └── evidence/              # read-only EvidenceViewManifestV1 tree
│       ├── manifest.json      # role=evolver; completed Epochs only
│       ├── bootstrap/
│       └── epochs/
├── candidate/                 # writable complete copy of Parent
└── scratch/                   # writable report, trace, and isolated Agent state
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

The entrypoint accepts only Evolution manifest schema 3 with the exact fixed path map. The manifest
identifies exactly one Parent and a nonempty, duplicate-free `visible_agents` catalog. Runtime
includes the retained Lineage Agent history plus Challengers already created earlier in the current
Epoch; each catalog entry supplies its Parent link, creator, relationship, and current-Epoch
Challenger ordinal when applicable, and resolves to one read-only repository under `input/agents/`. It also
requires a strict Evidence view with the matching lineage checkpoint, `role="evolver"`, the
completed promoted Agent lineage, and no current Epoch. It binds each environment path to that manifest and rejects
links and path escapes. A usage-report destination is mandatory, but no token budget is accepted.

The Evidence structure Prompt Fragment is authored and materialized by Runtime. This repository
only verifies its fixed path and Manifest-bound Digest before appending it to the final Prompt.

The Coding Agent writes EvolutionOutputV2 with Parent identity, hypothesis, expected effect, and an
exact sorted changed-path declaration. Runtime remains authoritative: it independently
hashes Parent and Candidate, verifies the actual changed set and Bundle policy, seals provenance, and
runs the configured Active-versus-Challenger-pool evaluation.

## 4. Token and process ownership

The Claude backend parses stream-json usage per unique provider message, uses the terminal usage when
available, and counts uncached input, output, cache reads, and cache writes exactly once. Token count
never terminates the child. Outer SIGTERM/SIGINT is relayed to that group; timeout and captured
stdout/stderr are bounded. The report uses a null budget and fails closed when a completed model
request lacks complete provider buckets.

The Session Artifact preserves the final rendered Prompt at `input/prompt.md`, the captured Claude
stream-json stream at `provider/stdout.stream-json`, and captured Provider stderr at
`provider/stderr.log`. Runtime and Evolver apply no redaction, event selection, or text rewriting to
those files. Reasoning, tool arguments and results, credentials, or other sensitive fields emitted
by the Provider therefore remain present. `events.jsonl` is an additional normalized usage index;
`session.json` records termination state and whether raw Provider capture avoided truncation. The
configured stdout/stderr limits remain safety limits: overflow fails the Session and marks the raw
stream incomplete rather than silently presenting a truncated stream as complete. Environment
credentials are not proactively copied when the Provider did not emit them.

## 5. Evolution of the Evolver

This first repository is fixed per deployment Git commit. A future self-evolution layer may propose
a new Evolver commit, but it must use a separate evaluation and promotion policy from Optimizer evolution.
It must never let an unpromoted Evolver rewrite itself in place or change the trusted Runtime boundary.
