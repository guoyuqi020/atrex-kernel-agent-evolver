# Objective

Produce one evidence-driven revision of the complete writable Optimizer repository in `candidate/`.
The goal is to improve the Optimizer's ability to discover a faster correct Kernel for the given DSL
in the next fixed-budget Epoch. This is Agent engineering, not Kernel implementation work.

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

1. Inspect the complete Parent repository before editing.
2. Inspect every repository listed in `visible_agent_repositories`. They contain the current Active,
   already-created Challengers in this Epoch, and retained Agent designs from the Lineage. Compare
   their concrete prompts, skills, workflows, and tools; do not merely vary the Parent blindly.
3. Read the unified Evidence view in Epoch order. For every completed Epoch, compare the Active and
   every Challenger under `branches/`, inspect their Attempt outcomes and exact Kernel artifacts,
   and use `winner_kernel_agent_revision_id`, `best_kernel_revision_id`, and the `selected` fields as
   authoritative selection facts. Do not mistake one fast Kernel for proof that every Agent change
   was useful. Separate authoritative evaluation facts from untrusted Agent annotations. Look for
   repeated failed hypotheses, missing information, brittle workflow steps, incorrect tool
   instructions, weak memory retrieval, or an overly broad search policy.
4. State one concrete bottleneck and one minimal Agent-level hypothesis internally.
5. Change only files required to test that hypothesis. You may revise Backend configuration, Prompt,
   workflow code, tool bindings, memory policy, or DSL guidance, provided the Bundle remains valid.
6. Review the exact Parent-versus-Candidate file set and content differences. Remove unrelated churn.
7. Write the terminal JSON report. `changed_paths` must be the exact sorted set of repository-relative
   regular files that were added, modified, or removed. A no-op is invalid.

# Terminal output

Write exactly one JSON object with this shape to the supplied output path:

```json
{
  "schema_version": 2,
  "parent_revision_id": "agentrev_00000000000000000000000000000000",
  "hypothesis": "A specific explanation of why the Agent change should help.",
  "expected_effect": "The observable optimization behavior expected in the next Epoch.",
  "changed_paths": ["path/changed/in/the/candidate"]
}
```

Do not claim that the Candidate is better. The trusted evaluator independently validates the tree
and compares the Parent and Candidate Agent revisions after this process exits.
