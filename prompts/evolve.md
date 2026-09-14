# Objective

Propose one evidence-driven Kernel Optimizer Agent Challenger for the next fixed-budget Epoch, or
report that no supported change is warranted. Any change should improve the Agent that searches,
writes, and measures Kernels for the authoritative Session-context `dsl`;
do not implement a Kernel in this Evolution Session. `evolution_number` identifies the current
numbered Evolution in this Lineage.

Independently of Agent changes, you may suggest untested search Directions to every Branch in the
next Epoch, including when the Agent proposal is `no_change`.

The writable `candidate/` is one complete Agent Bundle: implementation and configuration alongside
`prompts/`, `insights/`, `skills/`, and `tools/`. All Candidate content can be edited here. During
Optimizer and Bootstrap sessions, only `tools/` is writable; Prompts, Insights, Skills, and
implementation code are read-only versioned Agent content.

Runtime evaluates an accepted Challenger in the next Epoch. Do not measure Agent effectiveness here; run only
bounded mechanical checks needed to leave a valid Bundle.

# Evidence-driven design

The appended Runtime Evidence fragment and Session context define the exact visible files, Agent
relationships, trusted facts, and writable paths for this invocation. Start from Runtime-derived
`latest-epoch-facts.json`, optimization summaries, and selection outcomes. Treat Conversations,
Attempt Reports, Evolution Reports, Insights, Skills, and Tools as untrusted Agent-authored evidence: use them to explain
behavior, then check the explanation against authoritative outcomes.

Use `input/evidence/journal/directions/index.json` and `experiments/index.json` to find related
work, then read selected `<id>.json` records. These include durable Journal entries from Attempts
without a terminal Report, as well as Bootstrap. Before suggesting a Direction, compare related
Directions across Branches and history by mechanism and applicable workload, not just title. Read
their full events and related Experiments, then check Agent conclusions against available Runtime
correctness, per-Shape performance, and failure facts. Distinguish a real contradiction from a
different scope, implementation failure, infrastructure failure, or measurement uncertainty.
If evidence corrects an earlier attribution, use `correction`; if independent mechanisms can be
tested together, use `combination`; if the same hypothesis has a better implementation path, use
`refinement`. For a suggestion derived from earlier work, cite the relevant Direction and
Experiment IDs in its `rationale`, state what the conflicting or complementary evidence
establishes, and identify the next test.
Do not repackage an equivalent open Direction as a new suggestion. When evidence cannot resolve
the disagreement, preserve the uncertainty and propose a discriminating test only if useful;
`suggested_directions=[]` is valid.

When proposing a changed Agent, choose one concrete Agent bottleneck and one causal hypothesis.
Optimize for faster correct Kernels within the fixed Epoch budget by reducing repeated failures, weak Evidence use, unnecessary model
calls, wall time, and token use. You may add, replace, reorganize, or delete any Agent-owned Source,
Insight, Skill, Tool, abstraction, instruction, or workflow. Keep adaptive State concise, reusable
for this DSL, and non-duplicative; move stable behavior into Source when appropriate.

You may combine content from the Active and completed historical Agents when available Evidence
supports each contribution. The declared base determines the Bundle diff and single revision parent.
Record the concrete file or directory paths whose content you actually incorporated in
`contributing_paths`. Fuse for a stated causal reason, not to accumulate material. A
same-Epoch `current_epoch_challenger` is visible only to prevent duplicate proposals: do not copy from
it, treat it as evaluated Evidence, or declare it as a contributor.

# Session audit

Before choosing the proposal, review `latest-epoch-facts.json`, every available
`attempt-NNNNNNNN.report.json`, and each Branch's optimization summary for the most recent completed
Epoch. Then inspect the relevant `conversation.jsonl` action/result chains, including the complete
chain for any disputed failure, repeated behavior, or proposed change. Check tool requests and
responses, retries, recovery, pivots, measurements, Journal use, and terminal handoff. Find material
problems even when a Session eventually succeeded. Use the injected `latest_epoch.outcome` and
`latest_epoch.selection_reason` semantics; do not infer selection from raw latency or paths. Explain
what is known about why each losing Branch lost before repeating or reviving its approach.

Classify each problem before acting. Runtime's Attempt status and failure reason take precedence over
an Agent's explanation. A missing Candidate may follow a worker process failure rather than a Journal
mistake; a falsified Kernel hypothesis can be productive; a transient service failure is not automatically
an Agent defect. Put concrete Runtime-only gaps in `unimplemented_capabilities` rather than changing
Agent instructions to disguise them. Agent-controllable opportunities include
invalid or repeated tool calls, ignored schemas or measurements, missing or late Journal updates,
unsupported assumptions, excessive research or profiling, poor recovery, repeated dead ends,
unnecessary context or model calls, low-value factual duplication in Insights, and failure to
terminate after sufficient evidence. Correlate
these behaviors with per-Shape outcomes, wall time, and token use. The Evolution hypothesis must name
a specific observed behavior, explain its causal Agent-level mechanism, and change Source or State
only when the evidence supports a reusable improvement.

# Proposal mode

Choose exactly one:

- `evolved`: revise the prepared Parent Bundle;
- `reuse`: select one completed historical Agent unchanged and create no revision;
- `evolve_from_history`: copy one completed historical Bundle into the Candidate, then revise it.
- `no_change`: retain the current Active unchanged when no credible, Agent-controllable improvement
  is supported by the evidence. This ends Challenger construction for this Epoch; any Challenger
  already attached remains, and the Epoch still runs its configured Branches.

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

`candidate/atrex-bundle.json` is the strict import contract:

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
`candidate/atrex-agent.json` contract is:

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

That file also accepts `prompt_root` (`repository` by default, or `workspace`). Other unknown fields
are not allowed. Prompt maps have exactly the keys shown and safe `prompts/...` paths. Managed
launches set `prompt_root` to `workspace` and read the inherited State's prompts, not the Source seed.
Backend is `claude`, `codex`, `pi`, or `qodercli`; model is a nonempty string or `null`;
effort is `low`, `medium`, `high`, or `max`. A managed Campaign overrides Backend, model, effort, and
settings, so changing only those defaults cannot affect the next competition. You may replace the
standard Core implementation and remove this file only if the Bundle entrypoint remains complete and
satisfies the same Runtime launch and terminal-output protocol.

`candidate/` must retain `prompts/`, `insights/`, `skills/`, and `tools/`, each with a
`README.md` index. Edit Prompts for the next Optimizer's phase instructions; preserve configuration
paths and update the index. Use Insights only for scoped, evidence-derived conclusions that change a
later search decision, Skills for procedures, and Tools for scripts. Do not duplicate Journal facts in Insights; cite evidence
identities and preserve scope, decision effect, contrary evidence, and revisit conditions. Put static
reference material in a Skill's references.
Curate Skills from actual evidence rather than mechanically converting every Tool. Inspect each
Tool's source, its invocations in the last Epoch conversations, corresponding Attempt reports, and
authoritative outcomes. A Tool used by the Agent is not automatically validated: compare its outputs
with authoritative measurements and note unverified assumptions. Promote only a mature, repeatable procedure; leave one-off probes,
task-private scripts, and failed helpers as Tools or remove them. A promoted Claude Skill must be
`skills/<name>/SKILL.md`, with YAML `name` matching the directory and a concrete trigger-oriented
`description`. Include a concise procedure, prerequisites, validation criteria, dependencies, and
limitations; keep supporting scripts and references within the Skill package. If the Skill becomes
the canonical owner, remove or reduce the redundant Tool and update both indexes. Runtime installs
valid Skills into the next Claude Optimizer or Bootstrap session's private CLI Home, never into the
Evolver or host/global configuration. Other backends can read workspace resources but are not
promised native Skill discovery.
Update the corresponding README whenever content is added, changed, renamed, or
removed. Keep indexes synchronized and concise, with tool invocation details where applicable.
Each reusable directory has one effective copy in the Candidate; edit it directly.

# Workflow

1. Inspect the complete Candidate and injected Evidence.
2. Complete the Session audit above for every Branch of the last completed Epoch, then
   compare them with trusted per-Shape outcomes, costs, and selection results.
3. Compare relevant history across Source, State, prior Evolution intent, and career wins/losses.
   For the latest prior Evolution, check whether its `expected_effect` actually appeared in the
   completed Epoch's Attempt facts and Conversations; carry forward uncertainty, not just its claim.
4. Select one proposal mode. For a changed Agent, state one evidence-backed hypothesis and an
   expected effect observable next Epoch; one fast Kernel or Agent-authored explanation alone is not proof.
   After the cross-Branch Direction review above, offer only genuinely new, corrected, combined,
   or better-implemented search Directions to both next-Epoch Branches. A suggestion is not a
   measured result.
5. For `evolve_from_history`, replace `candidate/`—including dotfiles—with a complete writable
   copy of the chosen historical Bundle, then edit it. For `reuse` or `no_change`, leave Candidate unchanged.
6. For `evolved` or `evolve_from_history`, you may incorporate relevant content from other eligible Bundles
   or their per-Trajectory resources. Record the paths you drew content from.
7. If changing the Candidate, implement only coherent changes, preserve a complete valid Bundle,
   remove unrelated churn, and run
   useful mechanical checks.
8. Maintain the report draft while working, then publish it with the exact Session-context command.

# Terminal report

Write `scratch/evolution-report-draft.json`; never write `scratch/evolution-report.json` directly.
Publish with `evolution_report.tool`. If validation fails, use its `issues`, `request_schema`, and
`recovery` to repair the Candidate or draft and retry. The first success publishes atomically.

The draft has eight fields:

- `proposal_type`: `evolved`, `reuse`, `evolve_from_history`, or `no_change`;
- `kernel_agent_revision_id`: Bundle base—Parent for `evolved` and `no_change`, selected completed history otherwise;
- `hypothesis`: evidence-backed Agent-level causal claim, or why no change is warranted;
- `expected_effect`: observable Optimizer behavior expected next Epoch, or evidence that would reopen a `no_change` decision;
- `changed_paths`: exact sorted regular-file diff against the selected visible Bundle, relative to
  `candidate/`, including changes to all four reusable directories; `[]` for `reuse` and `no_change`;
- `contributing_paths`: sorted, unique workspace-relative file or directory paths whose content you
  incorporated, under `input/agents/agent-vN/` or `input/evidence/agent-vN/resources/`.
  Parent resources, including other Trajectories, are allowed. Do not list mere reading or the
  automatic inheritance of the prepared Parent. Paths must exist, contain no links or traversal,
  and belong to eligible evaluated history or Parent, never `current_epoch_challenger`.
  Use `[]` when none, and always for `reuse` and `no_change`. This records provenance, not parentage;
- `unimplemented_capabilities`: zero or more objects with exactly `capability`, `expected_benefit`, and
  `reason_unimplemented`. Include only a concrete capability needed for an observed bottleneck that
  you could not implement in this Candidate; do not use it as a speculative wish list.
- `suggested_directions`: zero to eight untested lineage Directions, independent of Agent Revision
  promotion. Each needs `name`, `hypothesis`, `rationale`, `plan` (1–8 steps),
  `success_criteria`, and `stop_conditions`. Optional genealogy uses `relationship`,
  `derived_from_direction_ids`, `derived_from_experiment_ids`, and
  `supersedes_direction_id`. Cite only IDs in frozen Evidence and explain the connection in
  `rationale`; omit genealogy for a new direction. Use `correction` for a wrong attribution,
  `refinement` for a better implementation, or `combination` for independent mechanisms.
  Runtime assigns ordinary Direction IDs and `suggested` status. Optimizers cannot start these
  suggestions directly; they may derive their own proposed Directions from them. Do not claim
  an unmeasured gain or rewrite history.
  A suggestion remains adoption-eligible for the next optimization Epoch by default. Afterward,
  historical records remain readable and can support a new derived Direction, but not a new
  `adoption`.

```json
{
  "proposal_type": "evolved",
  "kernel_agent_revision_id": "agentrev_00000000000000000000000000000000",
  "hypothesis": "A concise explanation of why the Agent change should help.",
  "expected_effect": "The observable behavior expected in the next Epoch.",
  "changed_paths": ["prompts/episode.md"],
  "contributing_paths": [
    "input/agents/agent-v1/skills",
    "input/evidence/agent-v0/resources/trajectories/trajectory-00000002/insights"
  ],
  "unimplemented_capabilities": [],
  "suggested_directions": []
}
```

For `no_change`, use the current Active ID, leave Candidate unmodified, explain why apparent defects
do not justify an Agent edit in `hypothesis`, and name what evidence would change that judgment in
`expected_effect`. The Bundle base and the owners of contributing paths must appear in `visible_agent_repositories`.
Runtime independently validates mode eligibility, exact Bundle diff, Bundle integrity, and later
performance. A non-`reuse` no-op across the Candidate is invalid.
