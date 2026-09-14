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
│   │       ├── src/ and configuration
│   │       └── {prompts,insights,skills,tools}/
│   ├── evidence/              # read-only authorized execution Evidence
│   │   └── agent-v<N>/
│   │       ├── resources/trajectories/trajectory-NNNNNNNN/
│   │       ├── optimization-summary.json
│   │       ├── sessions/      # last completed Epoch's branches only
│   │       └── reports/       # last completed Epoch's branches only
│   └── evolution-reports/     # prior Agent-creation reports
├── candidate/                 # writable Agent Candidate
│   ├── src/ and configuration
│   └── {prompts,insights,skills,tools}/
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

The entrypoint accepts Evolution manifest schema 11 with fixed paths, one Parent, and a nonempty
`visible_agents` catalog. Every entry has a Lineage version, revision ID, Parent link, creator,
relationship, Bundle `path`, summary path, optional Sessions/reports paths, and `resources_path`.
Relations are `active`, `challenger`, `current_epoch_challenger`, and `lineage_history`.
The `parent: true` entry is the last completed Epoch's winner, not necessarily its Active branch.

Each `input/agents/agent-vN/` is a complete read-only Bundle. The Parent combines implementation
with the winning best-Kernel Trajectory's terminal resources; missing terminal State falls back to
Epoch-start State, revision seed, then packaged defaults. The next Active uses the same initial
resources. Other visible Bundles use their revision seeds. Runtime copies the complete Parent to
writable `candidate/`: implementation and four adaptive directories, each present only once.

Every version has an optimization summary under `input/evidence/agent-vN/`; only participants in
the last completed Epoch also expose its Conversations and Attempt reports, grouped by Trajectory.
The summary separates latest-Epoch correct/incorrect/missing-Candidate counts and the best correct
Kernel's per-Shape authoritative Gateway result from career participation/win/loss counts.
`selection_reason` describes the final pairwise decision, not every step of a multi-Challenger
tournament. Bootstrap and older-Epoch conversations remain private.

Supplementary learned resources from available Trajectories are under
`input/evidence/agent-vN/resources/trajectories/trajectory-NNNNNNNN/`. Evolver can compare and
synthesize eligible Agents' prompts, insights, skills, and tools. Every adaptive directory
must retain a README index updated on content changes. Insights hold scoped, evidence-derived
decision guidance; static reference material belongs in Skill references. Optimizer changes only
Tools. Evolver promotes a Tool to `skills/<name>/SKILL.md` only when actual Session use and outcomes
support a reusable procedure, then removes redundant copies and updates both indexes. Runtime
installs Skill directories only when starting the next Claude Optimizer session, into its private
CLI Home.

Prior reports at `input/evolution-reports/evo-N.json` use `parent.path`, `generated_agent.path`,
to reference complete Bundles. `report.contributing_paths` retains the original Session-relative
contribution paths; current resources may differ from the archived snapshots. These are Agent-authored intent,
not evidence that the proposal won. Full Evolution traces remain Runtime-private.

The seven-field `EvolutionOutput` contains `proposal_type`, `kernel_agent_revision_id`,
`hypothesis`, `expected_effect`, `changed_paths`, `contributing_paths`, and
`unimplemented_capabilities`.

- `evolved`: edit the prepared Parent Bundle.
- `reuse`: select eligible history unchanged; leave Candidate untouched and report no changed paths.
- `evolve_from_history`: replace Candidate with a complete writable copy of the selected historical
  Bundle before editing. Runtime validates the declared base.
- `no_change`: retain Active unchanged when no supported Agent-controllable change exists; leave
  Candidate untouched. Runtime closes the remaining Challenger slots and runs the Epoch normally.
- `changed_paths` is the exact sorted diff relative to the selected Bundle root, including all four
  adaptive directories. A new revision must contain a real change.
- Contributions identify actual incorporated Bundle/resource paths, including Parent Trajectories.
  Runtime freezes their exact contents; eligibility, not exclusion of the base, determines validity.
- Unimplemented capabilities state a concrete need, expected benefit, and reason it could not be
  implemented; they grant no permission or selection advantage.

Maintain `scratch/evolution-report-draft.json` and submit through
`python3 input/evolver/src/runtime_tools.py evolution-report --request scratch/evolution-report-draft.json`.
Errors return `issues`, `request_schema`, and `recovery` without publishing. The first success
atomically creates `scratch/evolution-report.json`. Runtime independently validates the complete
Bundle diff and imports the Bundle plus its four-directory checkpoint. Performance selection happens
in the next Epoch, not in the Evolver session. Optimizer implementation permissions and inheritance
rules are unchanged.

`contributing_paths` records sorted, unique workspace-relative files or directories actually incorporated from
`input/agents/agent-vN/` or `input/evidence/agent-vN/resources/`, including Parent resources from other
Trajectories. Mere reading and automatic Parent inheritance are not contributions. Paths must exist,
contain no links/traversal, and belong to eligible evaluated history or Parent, never a same-Epoch
unevaluated Challenger. `reuse` requires `[]`. Runtime records ownership and exact content snapshots
in the Evolution Trace; the field does not change the Bundle base or revision ancestry.

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
