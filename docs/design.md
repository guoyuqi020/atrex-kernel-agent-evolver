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
│   ├── agents/                # every visible Agent version, one location each
│   │   └── agent-v<N>/
│   │       ├── source/        # exact versioned Agent repository
│   │       └── runtime-state/ # per-Trajectory memory/docs/memory/docs/skills/tools
│   ├── evidence/              # read-only authorized execution Evidence
│   │   └── agent-v<N>/
│   │       ├── optimization-summary.json
│   │       ├── sessions/      # last completed Epoch's branches only
│   │       └── reports/       # last completed Epoch's branches only
│   └── evolution-reports/     # prior Agent-creation reports
├── candidate/                 # writable Agent Candidate
│   ├── source/                # complete versioned Bundle
│   └── runtime-state/         # one common {memory,docs,skills,tools} seed
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

The entrypoint accepts only Evolution manifest schema 11 with the exact fixed path map. The manifest
identifies exactly one Parent and a nonempty, duplicate-free `visible_agents` catalog. Runtime
includes the retained Lineage Agent history plus Challengers already created earlier in the current
Epoch; each catalog entry supplies its Lineage version, Parent link, creator, `relationship`
(`active`, `challenger`, `current_epoch_challenger`, or `lineage_history`), and
Challenger ordinal when applicable. Every visible revision resolves to exactly one location keyed by
that version: `input/agents/agent-vN/` holds its sealed Source and per-Trajectory Runtime State, and
`input/evidence/agent-vN/` holds what Runtime derived about it. No directory name encodes an Epoch role.
Every version has an optimization summary; only the branches that competed in the most recent
completed Epoch also have `sessions/` and `reports/`, all drawn from that same Epoch so they are
directly comparable. The Parent is the entry marked `parent`, which is that Epoch's winner. Each
summary states the revision's `branch` and `outcome`. Its `selection_reason` records the final
pairwise selection step, not every comparison in a multi-Challenger tournament, so it must not be
treated as the individual reason every losing revision lost.
Conversations and Attempt reports are grouped by Trajectory; Bootstrap and older Epoch conversations
remain private Runtime history, and current-Epoch Challengers have neither because they have
run no Attempt. Runtime also projects each available prior Agent-creation `EvolutionOutput` into ordered
`input/evolution-reports/evo-N.json` wrappers that link the Source Base and produced Agent to their
visible Source and Runtime State paths. Full Evolution traces remain private. Per-Trajectory
adaptive `memory/`, `docs/`, `skills/`, and `tools/` live under the corresponding `runtime-state/` beside that version's
source, co-locating source, accumulated effect, and runtime state. They are
non-versioned Lineage state and are the adaptive State storage. Top-level `skills/` and
`tools/` are reserved and invalid in versioned source. Evolver may curate the writable
`candidate/runtime-state/` directly or improve the source mechanism that governs its future use.
Runtime seals complete Candidate Source and State independently, then pairs both Digests as one
logical Bundle. That exact State initializes every new Trajectory. Each of the four directories must
contain a README index updated with every content change; their roles are search memories, knowledge,
procedures, and scripts. Source's own implementation documentation is separate from adaptive Docs.
Each optimization summary separates the Agent Revision's most recent completed Epoch from its
career record. The latest-Epoch section counts correct, incorrect, and missing Candidate Kernels and
embeds the best correct Kernel's authoritative per-Shape Gateway projection. The career section
counts completed-Epoch participations, wins, and losses.
Runtime derives this compact view from the matching immutable Lineage checkpoint. It does not expose
an Agent-facing `epochs/` tree or duplicate that detailed history inside the Evolution workspace. It binds
each environment path to the manifest and rejects
links and path escapes. A usage-report destination is mandatory, but no token budget is accepted.

`Parent` is a role, not another repository or directory. It is exactly the visible Agent marked
`parent`, stored once under `input/agents/agent-v<N>/` like every other version. Runtime copies its
Source and the latest completed Epoch winner's best-Kernel Trajectory terminal State after that Epoch's
last Attempt into Candidate. The next Epoch's Active Branch uses the same State seed. Missing terminal
State falls back to that Trajectory's Epoch-start State, the revision seed, and then the empty default.
For `evolve_from_history`, Evolver replaces Candidate
Source with the selected historical Source and may synthesize the common seed from visible historical
Trajectories. The terminal output names only its `kernel_agent_revision_id`; Runtime uses that
Revision's Source as the proposal reference and checks its
Source identity while retaining Runtime State identity as private control data, then
computes the actual Diff across Source and the initial Active State. Every new Revision seals both
components as one logical Agent Bundle.
No Candidate-control tool or side record is trusted or required.

The Evidence structure Prompt Fragment is authored from a Runtime source template and passed to the
outer Bundle process in memory before being appended to the final Prompt.

The Coding Agent writes uniform `EvolutionOutput`. Every mode uses `kernel_agent_revision_id`,
`changed_paths`, and `contributing_revision_ids`; the second reports only sorted Source-root-relative
paths. Reuse requires an empty
array, and a State-only new revision may also report an empty array. It
may derive a new revision from Active,
reuse one visible historical revision unchanged, or derive a new revision from one visible
historical revision. New-revision proposals include an exact sorted changed-path declaration
relative to the selected Source base. Runtime computes State changes privately. A Candidate may also
combine content from several visible Agents; `contributing_revision_ids` names every revision other
than the Source base whose Source or Runtime State it drew from, restricted to completed Lineage
history or the Active. That is provenance, not parentage: the Source base and the diff target remain
the single declared revision. Every mode
may include bounded structured
`unimplemented_capabilities`, recording a capability, its expected Kernel-optimization benefit, and
the concrete reason it could not be implemented. Runtime preserves these untrusted advisory entries
in Evolution Evidence so later Evolvers can inspect them; they confer no authority and do not change
selection. Runtime remains authoritative: it validates frozen visibility, independently hashes Base
and Candidate, verifies the actual changed set and Bundle policy, seals
per-Epoch proposal provenance, and runs the configured Active-versus-Challenger-pool evaluation.
Revision parentage remains a tree; reuse and promotion are participation events, not ancestry edges.

The Agent maintains `scratch/evolution-report-draft.json` and invokes the fixed read-only Bundle
tool `python3 input/evolver/src/runtime_tools.py evolution-report --request
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
`provider/stderr.log`. The sealed `conversation.jsonl` is a reading view: Claude native content takes precedence over duplicate stdout messages. Distinct thinking/text/tool blocks remain intact; uncovered stdout content, diagnostics, compaction boundaries, and terminal results remain visible. Duplicate initial prompts and native queue/title/file-history bookkeeping are omitted from this view only. The live view still follows stdout until sealing. Raw Provider files and the normalized usage index are unchanged. It explicitly marks
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
