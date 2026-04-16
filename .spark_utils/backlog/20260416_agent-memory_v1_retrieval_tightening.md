# Task: Agent Memory V1 Retrieval Tightening

Date: 2026-04-16
Repo: `agent-memory`

## 1. Plan

1. Define the short-term write cadence for V1.
   Inputs: current usage model, installed skill, forward-test findings, current short-term CLI/Python flows.
   Outputs: clear rules for what should be written to short-term memory and what should be skipped.
   Success criteria: an agent can decide whether to write a short-term item without relying on vague judgment.
   Checkpoint: simple `store / skip / summarize later` guidance exists and matches the actual product.

2. Define the startup recall contract for coding work.
   Inputs: `MemoryClient.get_context()`, current skill wording, coding-agent examples, forward-test findings.
   Outputs: a stable start-of-task recall procedure for coding workflows.
   Success criteria: startup recall is a documented and testable workflow, not an implicit habit.
   Checkpoint: one short startup sequence is documented and grounded in implemented behavior.

3. Add a more opinionated coding-oriented context assembly path.
   Inputs: current `get_context` composition, existing retrieval across short-term/long-term/reasoning.
   Outputs: either a preset or a thin additional assembly path for coding startup context.
   Success criteria: coding recall is sharper than raw `get-context` while staying compatible with the shell-first surface.
   Checkpoint: one concrete example produces tighter coding context than the current generic assembly.

4. Align the skill, examples, and high-level docs.
   Inputs: finalized cadence rules, startup recall contract, coding-oriented context assembly.
   Outputs: updated skill, references, and high-level docs reflecting real behavior.
   Success criteria: the skill explains how to operate the current product, not an aspirational one.
   Checkpoint: skill content and examples stay coherent with the implementation.

5. Validate the tranche end-to-end.
   Inputs: targeted tests and a shell-first replay.
   Outputs: verification evidence and updated task tracking.
   Success criteria: the new retrieval contract is tested and reproducible from the shell.
   Checkpoint: targeted tests pass and one coding-style replay confirms the expected context.

## 2. Dependencies

### Mandatory runtime

- none
  Why: this tranche should stay within the existing Python, CLI, and graph surface.
  Minimal alternative: none.

### Optional runtime

- none

### Mandatory dev/test/tooling

- `pytest`
  Why: validate retrieval behavior and prevent regressions.
  Minimal alternative: shell replay only, insufficient.
- `uv`
  Why: repository-standard runner.
  Minimal alternative: direct `.venv` execution, less aligned.
- local Neo4j via Docker
  Why: verify shell-first behavior against the real graph backend.
  Minimal alternative: mocks only, insufficient.

### Optional dev/test/tooling

- none

## 3. Skills

- `[HAVE]` `voidm-memory`
  Why: preserve repo continuity and prior product decisions.
- `[HAVE]` `python`
  Why: implement the retrieval and documentation updates cleanly.
- `[HAVE]` `general`
  Why: keep the tranche focused and avoid expanding into V2 work.
- `[MAY NEED]` `skill-creator`
  Why: only if the skill rewrite becomes more than a small operational adjustment.

## 4. MCP Tools

- `[HAVE]` none
  Why: all work is local.
