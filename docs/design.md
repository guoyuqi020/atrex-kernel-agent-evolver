# Evolver Bundle Design

English | [中文](design.zh.md)

## 1. Role and isolation

The Evolver is a separately versioned worker implementation, not a component inside the Optimizer
Candidate. Runtime launches it in a fresh workspace and process after an Epoch checkpoint exists. The Optimizer
never receives the Evolver repository, configuration, Prompt, trace, credentials, or process state.

Runtime materializes this workspace:

```text
run-<uuid>/
├── input/
│   ├── agents/                # current competition pool only
│   │   ├── active/{source,runtime-state}/
│   │   └── challenger-<ordinal>/{source,runtime-state}/
│   ├── evidence/              # read-only authorized execution Evidence
│   │   ├── active/{optimization-summary.json,sessions/}
│   │   └── challenger-<ordinal>/{optimization-summary.json,sessions/}
│   └── historical/            # completed, non-current Agent versions
│       └── agent-v<N>/
│           ├── source/        # exact versioned Agent repository
│           ├── optimization-summary.json
│           └── runtime-state/ # per-Trajectory skills/tools
├── candidate/                 # writable Agent Candidate
│   ├── source/                # complete versioned Bundle
│   └── runtime-state/         # one common {skills,tools} seed
└── scratch/                   # writable report, trace, and isolated Agent state
```

Runtime path validation and process capabilities are the current trust boundary; Prompt instructions
are defense in depth. The Evolver receives no Runtime Gateway/Wiki capability and must not evaluate
GPU Kernels. OS sandboxing is intentionally deferred and must be added before treating hostile Agent
code as contained.

The Evolution manifest and Evidence Prompt are passed to the outer Bundle process in memory, not
materialized in the Agent-visible workspace. Evolver receives no Runtime HTTP capability; all
authorized inputs are immutable files already present under `input/`.

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

The entrypoint accepts only Evolution manifest schema 9 with the exact fixed path map. The manifest
identifies exactly one Parent and a nonempty, duplicate-free `visible_agents` catalog. Runtime
includes the retained Lineage Agent history plus Challengers already created earlier in the current
Epoch; each catalog entry supplies its Parent link, creator, relationship, and current-Epoch
Challenger ordinal when applicable. Current participants resolve under `input/agents/`; completed,
non-current versions resolve under `input/historical/agent-vN/`. The unified Evidence view exposes
each current participant's Runtime-derived optimization summary and one authoritative
`conversation.jsonl` per Attempt from its latest completed Epoch. Conversations are grouped by
Trajectory; Bootstrap and older Epoch conversations remain private Runtime history. Runtime also
projects each available prior Agent-creation `EvolutionOutput` into ordered
`input/evolution-reports/evo-N.json` wrappers that link the Source Base and produced Agent to their
visible Source and Runtime State paths. Full Evolution traces remain private. Per-Trajectory
adaptive `skills/` and `tools/` live under the corresponding `runtime-state/` beside the current
source; historical directories co-locate source, accumulated effect, and runtime state. They are
non-versioned Lineage state and are the only adaptive Skill/Tool storage. Top-level `skills/` and
`tools/` are reserved and invalid in versioned source. Evolver may curate the writable
`candidate/runtime-state/` directly or improve the source mechanism that governs its future use.
Runtime seals complete Candidate Source and State independently, then pairs both Digests as one
logical Bundle. That exact State initializes every new Trajectory.
Each optimization summary separates the Agent Revision's most recent completed Epoch from its
career record. The latest-Epoch section counts correct, incorrect, and missing Candidate Kernels and
embeds the best correct Kernel's authoritative per-Shape Gateway projection. The career section
counts completed-Epoch participations, wins, and losses.
Runtime derives this compact view from the matching immutable Lineage checkpoint. It does not expose
an Agent-facing `epochs/` tree or duplicate that detailed history inside the Evolution workspace. It binds
each environment path to the manifest and rejects
links and path escapes. A usage-report destination is mandatory, but no token budget is accepted.

`Parent` is a role, not another repository or directory. It is exactly the visible Agent whose
relationship is `active`, stored once under `input/agents/active/`. Runtime copies its Source and
the latest completed Epoch winner's best-Kernel Trajectory terminal State after that Epoch's last
Attempt into Candidate. The next Epoch's Active Branch uses the same State seed. Missing terminal
State falls back to that Trajectory's Epoch-start State, the revision seed, and then the empty default.
Historical versions
are stored under `input/historical/agent-vN/`. For `evolve_from_history`, Evolver replaces Candidate
Source with the selected historical Source and may synthesize the common seed from visible historical
Trajectories. The terminal output names only its `kernel_agent_revision_id`; Runtime uses that
Revision's Source as the proposal reference and checks its
Source identity while retaining Runtime State identity as private control data, then
computes the actual Diff across Source and the initial Active State. Every new Revision seals both
components as one logical Agent Bundle.
No Candidate-control tool or side record is trusted or required.

The Evidence structure Prompt Fragment is authored from a Runtime source template and passed to the
outer Bundle process in memory before being appended to the final Prompt.

The Coding Agent writes uniform `EvolutionOutput`. Every mode uses `kernel_agent_revision_id` and
`changed_paths`; the latter reports only sorted Source-root-relative paths. Reuse requires an empty
array, and a State-only new revision may also report an empty array. It
may derive a new revision from Active,
reuse one visible historical revision unchanged, or derive a new revision from one visible
historical revision. New-revision proposals include an exact sorted changed-path declaration
relative to the selected Source base. Runtime computes State changes privately. Every mode
may include bounded structured
`unimplemented_capabilities`, recording a capability, its expected Kernel-optimization benefit, and
the concrete reason it could not be implemented. Runtime preserves these untrusted advisory entries
in Evolution Evidence so later Evolvers can inspect them; they confer no authority and do not change
selection. Runtime remains authoritative: it validates frozen visibility, independently hashes Base
and Candidate, verifies the actual changed set and Bundle policy, seals
per-Epoch proposal provenance, and runs the configured Active-versus-Challenger-pool evaluation.
Revision parentage remains a tree; reuse and promotion are participation events, not ancestry edges.

The Agent maintains `scratch/evolution-report-draft.json` and invokes the fixed read-only Bundle
tool `python input/evolver/src/runtime_tools.py evolution-report --request
scratch/evolution-report-draft.json`. A failed invocation publishes nothing and returns `issues`, the
exact `request_schema`, and bounded `recovery` instructions. The Agent may correct and retry until
the first success atomically publishes `scratch/evolution-report.json`; calls after success are
rejected. The tool checks the actual Source Diff and the private initial-State snapshot, while the
outer Bundle and Runtime independently repeat validation after the Coding Agent exits.

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
