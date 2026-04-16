# Task: Agent Memory First Skill Readiness Checkpoint

Parent backlog: [20260409_spark_agent_memory_integration_spike.md](/Users/adhuy/code/led8/ai/spark/agent-memory/.spark_utils/backlog/20260409_spark_agent_memory_integration_spike.md)

Validated on 2026-04-10.

## Purpose

Capture the current implementation checkpoint before drafting the first `agent-memory` skill, and define the next direction clearly enough to avoid freezing a skill too early.

Current readiness estimate:

- around `75-80%` toward a first usable skill

Already stable enough to build on:

- task-scoped helper over `MemoryClient`
- long-term candidate review flow
- idempotence for facts and preferences
- supersession with provenance for conflicting facts and preferences
- exact entity reuse before deeper resolution/deduplication
- real Neo4j integration coverage for the wrapper contract

Not yet frozen enough to skip design:

- startup recall format for coding work
- exact candidate review output contract for the skill
- real agent-facing skill wording and operating rules
- phase-2 items such as automatic promotion, `GLiREL`, and LLM fallback

## Step 1 - Define the skill operating contract

1. Turn the current coding-agent usage model into short, enforceable skill rules.
Inputs: current `CodingAgentMemory` contract, usage model document, examples, validated constraints.
Outputs: one concise operational contract for when the skill should write short-term, open reasoning traces, propose long-term candidates, and persist durable memory.
Success criteria: the skill can guide an agent without relying on repo-internal tribal knowledge.

Checkpoint:
- Confirm the skill remains `propose-only` for long-term writes.
- Confirm what the skill should do automatically versus only suggest.

## Step 2 - Define startup recall for the skill

2. Add a clear startup recall pattern above raw `get_context()`.
Inputs: current `get_context()` behavior, `voidm recall` mental model, coding-agent workflows.
Outputs: a lightweight recall contract for project architecture, constraints, decisions, procedures, and preferences.
Success criteria: the first skill can guide an agent on how to bootstrap context at the start of a coding task.

Checkpoint:
- Confirm whether startup recall is a wrapper convention, a prompt pattern, or a future API helper.
- Confirm what is in scope for the first skill versus deferred.

## Step 3 - Draft the first skill content

3. Write the first `agent-memory` skill from the stabilized contract.
Inputs: skill operating rules, startup recall contract, candidate review policy, wrapper API.
Outputs: one skill draft with workflow, decision rules, and examples.
Success criteria: the skill is short, concrete, and directly usable by an agent in coding workflows.

Checkpoint:
- Confirm the skill does not expose unstable or deferred features as if they were ready.
- Confirm the skill references the wrapper behavior that already has tests.

## Step 4 - Validate the skill against the current workflow

4. Compare the drafted skill against the current implementation and examples.
Inputs: skill draft, `CodingAgentMemory`, `coding_agent_workflow.py`, test coverage, usage model.
Outputs: a final gap list of what is still missing before calling the first skill production-ready.
Success criteria: the skill matches actual behavior and does not promise unsupported automation.

Checkpoint:
- Confirm every core rule in the skill has a corresponding implementation or explicit limitation.
- Confirm open gaps are listed as deferred, not silently implied.

## Required Libraries / Dependencies

### Mandatory runtime

- `neo4j-agent-memory` current Python API
Why: the skill will be based on `CodingAgentMemory` and the stabilized wrapper contract.
Minimal alternative: none for this skill draft.

### Optional runtime

- `GLiNER`
Why: current local extraction path used by the examples and phase-1 workflow.
Minimal alternative: disable extraction, but that weakens the intended skill guidance.

- `GLiREL`
Why: deferred relation extraction, not required for the first skill.
Minimal alternative: keep relation extraction off.

- LLM provider extras
Why: deferred fallback extraction, not required for the first skill.
Minimal alternative: stay local-only.

### Mandatory dev / test / tooling

- `uv`
Why: repo-standard workflow for examples and tests.
Minimal alternative: `pip`, but not aligned with the repo.

- local Neo4j runtime
Why: real integration validation for the wrapper-backed skill behavior.
Minimal alternative: none.

## Skills

- `[HAVE]` `voidm-memory`
Why: continuity and durable tracking of the stabilized coding-agent memory rules.

- `[HAVE]` `general`
Why: keep the first skill small and operational.

- `[HAVE]` `skill-creator`
Why: next step after this checkpoint is drafting the first skill itself.

- `[MAY NEED]` `python`
Why: if skill drafting exposes a missing wrapper helper or example adjustment.

## MCP Tools

- `[HAVE]` Local repo inspection tools
Why: enough to draft the first skill from code, tests, docs, and examples.

- `[MAY NEED]` Web docs for official wording
Why: only if we need exact official phrasing from the upstream project while drafting the skill.

## Approved Direction

- Use the stabilized `CodingAgentMemory` wrapper as the basis for the first skill.
- Keep the first skill explicitly focused on coding-agent workflows.
- Keep long-term memory in review-first mode.
- Do not include automatic short-term to long-term promotion in the first skill.
- Do not include `GLiREL` or LLM fallback in the first skill.
- Add a startup recall convention before calling the first skill done.
