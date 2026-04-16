# Task: Agent Memory Reasoning Recall Improvement

## Plan

1. Inspect and isolate the current reasoning recall bottleneck.
   - Inputs: `MemoryClient.get_context()`, `ReasoningMemory.get_context()`, `ReasoningMemory.get_similar_traces()`, current forward-test findings.
   - Outputs: a targeted retrieval strategy for `Similar Past Tasks`.
   - Success criteria: the change scope is limited to reasoning retrieval and formatting.
   - Checkpoint: confirm the current bottleneck before patching.

2. Add a fallback retrieval path for reasoning traces.
   - Inputs: reasoning trace task, outcome, steps, and tool calls already stored in Neo4j.
   - Outputs: a text-based fallback query for traces when vector similarity yields nothing.
   - Success criteria: reasoning recall no longer depends exclusively on `task_embedding` similarity at threshold `0.7`.
   - Checkpoint: targeted trace query returns a known trace for a shell-first scenario.

3. Enrich the reasoning context formatting.
   - Inputs: retrieved traces and their steps/tool calls.
   - Outputs: more actionable `Similar Past Tasks` content with key action, tools, and observations when available.
   - Success criteria: the reasoning section is useful to an agent, not just descriptive.
   - Checkpoint: inspect the formatted context string locally.

4. Cover the regression with tests.
   - Inputs: reasoning and memory client integration tests.
   - Outputs: tests that verify reasoning fallback retrieval and presence in combined `get_context()`.
   - Success criteria: the forward-test weakness becomes a covered behavior.
   - Checkpoint: targeted integration tests pass.

5. Replay a shell-first scenario and update tracking.
   - Inputs: real CLI commands against local Neo4j.
   - Outputs: evidence that `get-context` now surfaces reasoning memory in a practical scenario.
   - Success criteria: shell replay confirms the improvement.
   - Checkpoint: findings note and todo updated with the result.

## Dependencies

### Mandatory runtime
- none
  - Why: the improvement stays inside the existing reasoning retrieval and formatting logic.
  - Minimal alternative: none.

### Optional runtime
- none

### Mandatory dev/test/tooling
- `pytest`
  - Why: lock in the reasoning recall behavior with tests.
  - Minimal alternative: shell replay only, insufficient.
- `uv`
  - Why: project-standard test and CLI runner.
  - Minimal alternative: direct `.venv` execution, less aligned.
- local Neo4j via Docker
  - Why: verify the real shell-first behavior after the patch.
  - Minimal alternative: tests only.

### Optional dev/test/tooling
- none

## Skills
- `[HAVE]` `voidm-memory`
  - Why: preserve repo continuity and prior decisions.
- `[HAVE]` `python`
  - Why: patch retrieval and tests in Python.
- `[HAVE]` `general`
  - Why: keep the change targeted and simple.

## MCP Tools
- `[HAVE]` none
  - Why: all work is local.
