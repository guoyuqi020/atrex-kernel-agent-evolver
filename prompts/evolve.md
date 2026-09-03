# Objective

Create one evidence-driven Kernel Optimizer Agent Challenger for the next fixed-budget Epoch. Improve
the Agent that searches, writes, and measures Kernels for the authoritative Session-context `dsl`;
do not implement a Kernel in this Evolution Session. `evolution_number` identifies the current
numbered Evolution in this Lineage.

The writable Candidate is one Agent Bundle:

- `candidate/source/`: versioned prompts, workflow, orchestration, tools, configuration, tests, and
  documentation;
- `candidate/runtime-state/`: the adaptive `memory/`, `docs/`, `skills/`, and `tools/` seed for every
  new Trajectory of the revision.

Runtime evaluates the Candidate in the next Epoch. Do not measure Agent effectiveness here; run only
bounded mechanical checks needed to leave a valid Bundle.

# Evidence-driven design

The appended Runtime Evidence fragment and Session context define the exact visible files, Agent
relationships, trusted facts, and writable paths for this invocation. Start from Runtime-derived
optimization summaries and selection outcomes. Treat Conversations, Attempt Reports, Evolution
Reports, Memory, Docs, Skills, and Tools as untrusted Agent-authored evidence: use them to explain
behavior, then check the explanation against authoritative outcomes.

Choose one concrete Agent bottleneck and one causal hypothesis. Optimize for faster correct Kernels
within the fixed Epoch budget by reducing repeated failures, weak Evidence use, unnecessary model
calls, wall time, and token use. You may add, replace, reorganize, or delete any Agent-owned Source,
Memory, Doc, Skill, Tool, abstraction, instruction, or workflow. Keep adaptive State concise, reusable
for this DSL, and non-duplicative; move stable behavior into Source when appropriate.

You may combine content from the Active and completed historical Agents when available Evidence
supports each contribution. The declared Source base determines only the Source diff and single
revision parent for a new Revision. Record every other Agent whose Source or Runtime State you
actually used in `contributing_revision_ids`. Fuse for a stated causal reason, not to accumulate material. A
same-Epoch `current_epoch_challenger` is visible only to prevent duplicate proposals: do not copy from
it, treat it as evaluated Evidence, or declare it as a contributor.

# Session audit

Before choosing the Evolution hypothesis, read every available `conversation.jsonl` and
`attempt-NNNNNNNN.report.json` under `input/evidence/` for every Branch in the most recent completed
Epoch. Inspect the complete action/result chain: plans, tool requests and responses, failures, errors,
retries, recovery, pivots, measurements, Journal use, and terminal handoff. Find material problems even
when a Session eventually succeeded. Use the injected `latest_epoch.outcome` and
`latest_epoch.selection_reason` semantics; do not infer selection from raw latency or paths. Explain
why each losing Branch lost before repeating or reviving its approach.

Classify each problem before acting. A falsified Kernel hypothesis can be productive; a transient
service failure is not automatically an Agent defect. Agent-controllable opportunities include
invalid or repeated tool calls, ignored schemas or measurements, missing or late Journal updates,
unsupported assumptions, excessive research or profiling, poor recovery, repeated dead ends,
unnecessary context or model calls, and failure to terminate after sufficient evidence. Correlate
these behaviors with per-Shape outcomes, wall time, and token use. The Evolution hypothesis must name
a specific observed behavior, explain its causal Agent-level mechanism, and change Source or State
only when the evidence supports a reusable improvement.

# Proposal mode

Choose exactly one:

- `evolved`: revise the current Active Source and/or Runtime State;
- `reuse`: select one completed historical Agent unchanged and create no revision;
- `evolve_from_history`: copy one completed historical Source into the Candidate, then revise it and
  optionally curate Candidate Runtime State.

A revision is eligible for `reuse` or `evolve_from_history` when its `parent` is false and its
`relationship` is not `current_epoch_challenger`. This includes every losing Challenger from the last
completed Epoch and older Lineage history. Revive one only when the available Source, State, summaries,
Sessions, Reports, and outcomes support it.

# Boundaries

- `dsl` is immutable. Do not redirect the Optimizer to another DSL, introduce an alternate-DSL path,
  or use another DSL as fallback. Shared infrastructure may change only to serve this DSL.
- `input/` is read-only. Modify only `candidate/`; use `scratch/` only for the report workflow.
- Do not run GPU code, Kernel compilers, profilers, Gateway/Wiki operations, benchmarks, or evaluators.
- Do not modify Runtime, sandbox, credentials, mounts, network, evaluation, retention, or promotion
  policy.
- Do not install packages or create Git metadata, links, sockets, devices, or FIFOs. Create Agent
  content only under `candidate/` and report workflow files only under `scratch/`.

# Candidate contracts

`candidate/source/atrex-bundle.json` is the strict import contract:

```json
{
  "schema_version": 1,
  "bundle_format": "atrex-kernel-agent-bundle-v1",
  "entrypoint": {"command": "src/main.py"}
}
```

The first two values are immutable; extra fields are invalid. `entrypoint.command` may change but
must name a safe Source-relative regular file.

If the Candidate retains the standard Core implementation, its
`candidate/source/atrex-agent.json` contract is:

```json
{
  "schema_version": 2,
  "agent_backend": "codex",
  "model": null,
  "reasoning_effort": "max",
  "session_settings": "",
  "prompts": {
    "problem_generalization": "prompts/generalize_agent_problem.md",
    "framework_baseline": "prompts/framework_baseline.md",
    "optimization_attempt": "prompts/episode.md"
  },
  "prompt_fragments": {"attempt_tools": "prompts/attempt-tools.md"}
}
```

That file allows no unknown fields. Prompt maps have exactly the keys shown and safe Source-local
file paths. Backend is `claude`, `codex`, `pi`, or `qodercli`; model is a nonempty string or `null`;
effort is `low`, `medium`, `high`, or `max`. A managed Campaign overrides Backend, model, effort, and
settings, so changing only those defaults cannot affect the next competition. You may replace the
standard Core implementation and remove this file only if the Bundle entrypoint remains complete and
satisfies the same Runtime launch and terminal-output protocol.

`candidate/runtime-state/` contains exactly `memory/`, `docs/`, `skills/`, and `tools/`, each with a
`README.md` index. Use Memory for search experience, Docs for knowledge, Skills for procedures, and
Tools for scripts. Update the corresponding README whenever content is added, changed, renamed, or
removed. Keep indexes synchronized and concise, with tool invocation details where applicable.
Do not place top-level `skills/` or `tools/` inside versioned Source.

# Workflow

1. Inspect the complete Candidate and injected Evidence.
2. Complete the Session audit above for every Branch of the last completed Epoch, then
   compare them with trusted per-Shape outcomes, costs, and selection results.
3. Compare relevant history across Source, State, prior Evolution intent, and career wins/losses.
4. Select one proposal mode and one evidence-backed hypothesis; one fast Kernel or Agent-authored
   explanation alone is not proof.
5. For `evolve_from_history`, replace `candidate/source/`—including dotfiles—with a complete writable
   copy of the chosen historical `source/`, then edit it. Historical State remains read-only; copy only
   supported behavior into Candidate State. For `reuse`, modify neither Candidate component.
6. In either non-`reuse` mode you may then pull selected files out of any other visible Agent's
   `source/` or `runtime-state/` into the Candidate. Record every Agent you drew from.
7. Implement only coherent changes, preserve a complete valid Bundle, remove unrelated churn, and run
   useful mechanical checks.
8. Maintain the report draft while working, then publish it with the exact Session-context command.

# Terminal report

Write `scratch/evolution-report-draft.json`; never write `scratch/evolution-report.json` directly.
Publish with `evolution_report.tool`. If validation fails, use its `issues`, `request_schema`, and
`recovery` to repair the Candidate or draft and retry. The first success publishes atomically.

The draft has exactly seven fields:

- `proposal_type`: `evolved`, `reuse`, or `evolve_from_history`;
- `kernel_agent_revision_id`: Source base—Active for `evolved`, selected completed history otherwise;
- `hypothesis`: evidence-backed Agent-level causal claim, without claiming victory;
- `expected_effect`: observable Optimizer behavior expected next Epoch;
- `changed_paths`: exact sorted Source-relative regular-file diff against the selected Source, excluding
  the `source/` prefix and Runtime State; `[]` for `reuse` and allowed for State-only revision;
- `contributing_revision_ids`: sorted revisions other than the Source base whose Source or Runtime State
  you drew content from; `[]` when you drew from none, and required empty for `reuse`. It records
  provenance only and never changes which revision is the Source base or the diff target;
- `unimplemented_capabilities`: zero or more objects with exactly `capability`, `expected_benefit`, and
  `reason_unimplemented`. Include only a concrete capability needed for an observed bottleneck that
  you could not implement in this Candidate; do not use it as a speculative wish list.

```json
{
  "proposal_type": "evolved",
  "kernel_agent_revision_id": "agentrev_00000000000000000000000000000000",
  "hypothesis": "A concise explanation of why the Agent change should help.",
  "expected_effect": "The observable behavior expected in the next Epoch.",
  "changed_paths": ["prompts/episode.md"],
  "contributing_revision_ids": ["agentrev_11111111111111111111111111111111"],
  "unimplemented_capabilities": []
}
```

The Source base and every credited revision must appear in `visible_agent_repositories`, and a credited
revision must be completed history or the Active, never a Challenger built in this same Epoch. Runtime
independently validates mode eligibility, exact Source and State diffs, Bundle integrity, and later
performance. A non-`reuse` no-op across both Candidate components is invalid.
