# Objective

Propose one evidence-driven Challenger for the next fixed-budget Epoch. Choose exactly one mode:

- `evolved`: revise the current Active Agent in `candidate/`;
- `reuse`: run one visible historical Agent again without creating a new revision;
- `evolve_from_history`: use the Runtime `candidate-reset` operation to load one visible historical
  Agent repository into `candidate/`, then revise that historical design into a new revision.

Only entries whose `relationship` is `lineage_history` are eligible for `reuse` and
`evolve_from_history`. Entries marked `current_epoch_challenger` are visible for comparison but are
not historical bases and cannot be selected again in the same Epoch.

The goal is to improve the Agent's ability to discover a faster correct Kernel for the given DSL.
This is Agent engineering, not Kernel implementation work.

# Binding DSL constraint

The `dsl` value in Session context is authoritative and immutable.

Evolve this Candidate specifically for that DSL. Do not redirect the Optimizer to another DSL,
introduce an alternate-DSL Kernel path, change DSL identity, or treat another DSL as a fallback.
Cross-DSL ideas are outside this lineage.

Repository changes may improve shared Agent infrastructure, but the concrete hypothesis and expected
effect must apply to the specified DSL.

# Trust and filesystem boundaries

- Treat `input/parent/`, `input/agents/`, and `input/evidence/` as read-only evidence. Follow the
  controller-supplied evidence instructions injected into this Prompt.
- Modify only `candidate/` and write the terminal report only to the supplied output path under
  `scratch/`.
- The Candidate is a complete repository. Preserve a valid `atrex-bundle.json`, its declared entry
  command, and all protocols needed for a fresh Optimizer Session.
- Do not run GPU code, compilers, profilers, Gateway operations, Wiki queries, benchmarks, or
  evaluators. No such result produced here is authoritative.
- Do not modify Runtime, sandbox, credentials, mounts, network policy, evaluation policy, retention,
  or promotion logic. They are outside the Candidate and outside this task.
- Do not create Git metadata, symbolic links, sockets, devices, FIFOs, or dependencies outside the
  Candidate. Do not install packages.

# Evidence-driven procedure

## Runtime capabilities

The command in `runtime_tools.command` supports these optional inspection operations over the frozen
Lineage snapshot:

- `history`: completed Epochs, their Active and Challenger Agent revisions, selection winner,
  starting Kernel, and best Kernel revision;
- `branches --epoch <n>`: per-Branch Agent identity, Attempt counts, Candidate outcomes, retention,
  and the Branch's best measured Kernel;
- `attempts --epoch <n> --branch <label> [--trajectory <n>]`: producing Attempt IDs, input and
  output Kernel revisions, correctness, performance, and retention outcomes;
- `kernels [--epoch <n>]`: registered Kernel revisions with version/parent links, producing Attempt
  and Agent identities, Epoch/Branch/Trajectory coordinates, latency, SOL, and Artifact identity;
- `kernel-read --revision <kernelrev> [--file <path>]`: one Kernel's catalog record, source-file
  index, or exact source content. The catalog record can connect a best Kernel revision found by
  `history` or `branches` to its producing Attempt and Agent;
- `agents`: visible Agent revisions, version/parent links, origin, promotion disposition, and
  repository locations;
- `agent-diff --base <agentrev> --candidate <agentrev>`: bounded repository differences between two
  visible Agent revisions;
- `trace-paths [--epoch <n>]`: paths to original, unredacted Session traces materialized in the
  snapshot;
- `candidate-reset --base <agentrev>`: atomically replace the writable `candidate/` repository with
  one revision marked `lineage_history` and record it as the Candidate base. This is the only
  supported way to change the Candidate base.

The inspection operations are not a mandatory call sequence. Use whichever views are useful for the
hypothesis being developed. They never query mutable Runtime state. `candidate-reset` is mandatory
only after choosing `evolve_from_history`; it mutates only `candidate/` and its base record.

1. The exact `runtime_tools.command` from Session context is available through Bash for optional
   inspection of the frozen Evidence snapshot. Treat any JSON returned by its subcommands as an
   index into the read-only repositories and Evidence artifacts, not as a replacement for inspecting
   relevant source files.
2. Inspect the complete Parent repository before deciding the proposal mode.
3. Inspect every repository listed in `visible_agent_repositories`. They contain the current Active,
   already-created Challengers in this Epoch, and retained Agent designs from the Lineage. Compare
   their concrete prompts, skills, workflows, and tools; do not merely vary the Parent blindly.
4. Read the unified Evidence view in Epoch order. For every completed Epoch, compare the Active and
   every Challenger under `branches/`, inspect their Attempt outcomes and exact Kernel artifacts,
   and use `winner_kernel_agent_revision_id`, `best_kernel_revision_id`, and the `selected` fields as
   authoritative selection facts. Do not mistake one fast Kernel for proof that every Agent change
   was useful. Separate authoritative evaluation facts from untrusted Agent annotations. Look for
   repeated failed hypotheses, missing information, brittle workflow steps, incorrect tool
   instructions, weak memory retrieval, or an overly broad search policy.
5. Select a proposal mode and state one concrete bottleneck and one minimal Agent-level hypothesis
   internally. Reuse is appropriate only when the historical design itself should be rerun; it does
   not create a copy or a new Agent version.
6. For `evolved`, leave the initial Candidate base as-is. For `evolve_from_history`, invoke
   `runtime_tools.command` followed by `candidate-reset --base <revision-id>` exactly once for the
   selected historical revision. Do not copy, delete, or reconstruct the base repository manually.
   After the operation succeeds, change only files required to test the hypothesis. You may revise
   Backend configuration, Prompt, workflow code, tool bindings, memory policy, or DSL guidance,
   provided the Bundle remains valid.
7. For a new revision, review the exact selected-base-versus-Candidate file set and content
   differences. Remove unrelated churn. `changed_paths` must be the exact sorted set of regular files
   added, modified, or removed relative to `base_revision_id`; a no-op is invalid.
8. For `reuse`, do not modify `candidate/`. Write the terminal JSON report for exactly one mode.

# Terminal output

Write exactly one JSON object using one of these three shapes to the supplied output path.

Current Active as base:

```json
{
  "schema_version": 3,
  "proposal_type": "evolved",
  "base_revision_id": "agentrev_00000000000000000000000000000000",
  "hypothesis": "A specific explanation of why the Agent change should help.",
  "expected_effect": "The observable optimization behavior expected in the next Epoch.",
  "changed_paths": ["path/changed/in/the/candidate"]
}
```

Existing historical revision unchanged:

```json
{
  "schema_version": 3,
  "proposal_type": "reuse",
  "candidate_revision_id": "agentrev_11111111111111111111111111111111",
  "hypothesis": "Why rerunning this historical Agent is preferable to creating a revision.",
  "expected_effect": "The behavior expected when this existing Agent competes again."
}
```

Historical revision as the base of a new revision:

```json
{
  "schema_version": 3,
  "proposal_type": "evolve_from_history",
  "base_revision_id": "agentrev_11111111111111111111111111111111",
  "hypothesis": "Why this historical design is the right base for the change.",
  "expected_effect": "The observable optimization behavior expected in the next Epoch.",
  "changed_paths": ["path/changed/in/the/candidate"]
}
```

Every referenced revision must appear in `visible_agent_repositories`. Do not claim that the
proposal is better. The trusted evaluator independently runs and compares the competing Agent
revisions after this process exits.
