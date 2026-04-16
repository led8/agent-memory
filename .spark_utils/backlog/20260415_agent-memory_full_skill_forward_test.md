# Task: Agent Memory Full Skill Forward-Test

## Plan

1. Validate the forward-test baseline.
   - Inputs: installed skill under `~/.codex/skills/agent-memory`, local Neo4j container, `neo4j-agent-memory memory` CLI.
   - Outputs: confirmed shell-first environment ready for end-to-end testing.
   - Success criteria: skill path resolves, Neo4j is healthy, CLI is runnable.
   - Checkpoint: baseline commands succeed before scenario execution.

2. Run a complete short-term + reasoning + durable memory scenario.
   - Inputs: task-scoped session, shell commands for messages, trace, tool call, durable fact, and `get-context`.
   - Outputs: one end-to-end scenario proving the full shell workflow.
   - Success criteria: command chaining works with real JSON IDs and `get-context` reflects the durable fact.
   - Checkpoint: scenario transcript and key IDs captured.

3. Run a durable preference/fact lifecycle scenario.
   - Inputs: `add-preference`, `replace-preference`, `add-fact`, `replace-fact`, `search`, `inspect`.
   - Outputs: evidence for idempotence and supersession behavior.
   - Success criteria: active entries are returned by default search and superseded entries remain inspectable.
   - Checkpoint: inspect output shows supersession metadata.

4. Run an entity lifecycle scenario.
   - Inputs: `add-entity`, `update-entity`, `alias-entity`, `merge-entity`, `inspect`, `search`.
   - Outputs: evidence that entity maintenance works from the shell without `replace-entity`.
   - Success criteria: identity is preserved on update, aliases resolve, merge records provenance.
   - Checkpoint: inspect output for target and merged source captured.

5. Evaluate the product promise of `get-context`.
   - Inputs: memories created during scenarios 2–4.
   - Outputs: a concrete assessment of what `get-context` currently returns well and what it still misses.
   - Success criteria: clear statement of current retrieval quality with examples.
   - Checkpoint: compare expected versus actual returned context.

6. Record the findings without changing policy or code.
   - Inputs: outputs from all scenarios.
   - Outputs: updated issue note and todo status, with verdict on current skill readiness.
   - Success criteria: the result is traceable and actionable, and any new bugs are separated from the test itself.

## Dependencies

### Mandatory runtime
- local Neo4j via Docker
  - Why: the skill is shell-first and must be validated against the real graph backend.
  - Minimal alternative: none for a real forward-test.
- `uv`
  - Why: standard runner for the repo CLI.
  - Minimal alternative: direct `.venv` execution, less aligned.

### Optional runtime
- none

### Mandatory dev/test/tooling
- `zsh`
  - Why: validate real shell quoting and command chaining exactly as the skill expects.
  - Minimal alternative: none.
- `.spark_utils`
  - Why: keep the forward-test findings traceable.
  - Minimal alternative: none.

### Optional dev/test/tooling
- `pytest`
  - Why: only if a shell finding needs corroboration.
  - Minimal alternative: shell-only validation.

## Skills
- `[HAVE]` `voidm-memory`
  - Why: continuity across the repo and prior decisions.
- `[HAVE]` `general`
  - Why: keep the test protocol focused and simple.

## MCP Tools
- `[HAVE]` none
  - Why: the forward-test is fully local.
