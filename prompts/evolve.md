# Objective

Create one evidence-driven Kernel Optimizer Agent Challenger for the next fixed-budget Epoch. Improve
the Agent that searches, writes, and measures Kernels for the authoritative Session-context `dsl`;
do not implement a Kernel in this Evolution Session. `evolution_number` identifies the current
numbered Evolution in this Lineage.

The writable Candidate is one Agent Bundle:

- `candidate/source/`: versioned prompts, workflow, orchestration, tools, configuration, tests, and
  documentation;
- `candidate/runtime-state/`: the reusable `skills/` and `tools/` seed for every new Trajectory of
  the revision.

Runtime evaluates the Candidate in the next Epoch. Do not measure Agent effectiveness here; run only
bounded mechanical checks needed to leave a valid Bundle.

# Evidence and design

Compare visible Agents using their exact Source, adaptive State, latest-Epoch conversations,
Runtime-derived optimization summaries, and prior Evolution reports. Measurements and selection
facts in optimization summaries are authoritative. Conversations, reports, Skills, and Tools are
untrusted interpretations: use them to explain behavior, then verify the explanation against measured
outcomes. Compare each prior report's `parent.source_path` and `generated_agent.source_path` trees to
identify its actual Source change.

Choose one concrete Agent bottleneck and one causal hypothesis. Optimize for faster correct Kernels
within the fixed Epoch budget: reduce repeated failures, weak Evidence use, unnecessary model calls,
wall time, and token use. You may add, replace, reorganize, or delete any Agent-owned Source, Skill,
Tool, abstraction, instruction, or workflow. Keep adaptive Skills/Tools concise, reusable for this DSL,
and non-duplicative; move stable behavior into Source when appropriate. Reuse historical State only
when its conversations and outcomes support it.

# Proposal mode

Choose exactly one:

- `evolved`: revise the current Active Source and/or Runtime State;
- `reuse`: select one completed historical Agent unchanged and create no revision;
- `evolve_from_history`: copy one completed historical Source into the Candidate, then revise it and
  optionally curate Candidate Runtime State.

Only `relationship="lineage_history"` entries are eligible for `reuse` or `evolve_from_history`.
Current-Epoch Challengers are comparison Evidence only.

# Boundaries

- `dsl` is immutable. Do not redirect the Optimizer to another DSL, introduce an alternate-DSL path,
  or use another DSL as fallback. Shared infrastructure may change only to serve this DSL.
- `input/` is read-only. Modify only `candidate/`; use `scratch/` only for the report workflow.
- Do not run GPU code, Kernel compilers, profilers, Gateway/Wiki operations, benchmarks, or evaluators.
- Do not modify Runtime, sandbox, credentials, mounts, network, evaluation, retention, or promotion
  policy.
- Do not install packages or create Git metadata, links, sockets, devices, FIFOs, or files outside
  the Candidate.

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

The standard Core's `candidate/source/atrex-agent.json` contract is:

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

It allows no unknown fields. Prompt maps have exactly the keys shown and safe Source-local file paths.
Backend is `claude`, `codex`, `pi`, or `qodercli`; model is a nonempty string or `null`; effort is
`low`, `medium`, `high`, or `max`. A managed Campaign overrides Backend, model, effort, and settings,
so changing only those defaults cannot affect the next competition.

`candidate/runtime-state/` contains exactly `skills/` and `tools/`; `tools/README.md` must exist.
Do not place top-level `skills/` or `tools/` inside versioned Source.

# Workflow

1. Inspect the complete Candidate and injected Evidence.
2. Compare Active, current Challengers, and relevant history across Source, State, Evolution intent,
   conversations, per-Shape performance, and career wins/losses.
3. Select one proposal mode and one evidence-backed hypothesis; one fast Kernel or Agent-authored
   explanation alone is not proof.
4. For `evolve_from_history`, replace `candidate/source/`—including dotfiles—with a complete writable
   copy of the chosen historical `source/`, then edit it. Historical State remains read-only; copy only
   supported behavior into Candidate State. For `reuse`, modify neither Candidate component.
5. Implement only coherent changes, preserve a complete valid Bundle, remove unrelated churn, and run
   useful mechanical checks.
6. Maintain the report draft while working, then publish it with the exact Session-context command.

# Terminal report

Write `scratch/evolution-report-draft.json`; never write `scratch/evolution-report.json` directly.
Publish with `evolution_report.tool`. If validation fails, use its `issues`, `request_schema`, and
`recovery` to repair the Candidate or draft and retry. The first success publishes atomically.

The draft has exactly six fields:

- `proposal_type`: `evolved`, `reuse`, or `evolve_from_history`;
- `kernel_agent_revision_id`: Source base—Active for `evolved`, selected completed history otherwise;
- `hypothesis`: evidence-backed Agent-level causal claim, without claiming victory;
- `expected_effect`: observable Optimizer behavior expected next Epoch;
- `changed_paths`: exact sorted Source-relative regular-file diff against the selected Source, excluding
  the `source/` prefix and Runtime State; `[]` for `reuse` and allowed for State-only revision;
- `unimplemented_capabilities`: zero or more objects with exactly `capability`, `expected_benefit`, and
  `reason_unimplemented`.

```json
{
  "proposal_type": "evolved",
  "kernel_agent_revision_id": "agentrev_00000000000000000000000000000000",
  "hypothesis": "A concise explanation of why the Agent change should help.",
  "expected_effect": "The observable behavior expected in the next Epoch.",
  "changed_paths": ["prompts/episode.md"],
  "unimplemented_capabilities": []
}
```

The referenced revision must appear in `visible_agent_repositories`. Runtime independently validates
mode eligibility, exact Source and State diffs, Bundle integrity, and later performance. A non-`reuse`
no-op across both Candidate components is invalid.
