# Task: Agent Memory Post Forward-Test Fixes

Date: 2026-04-15
Repo: `agent-memory`

## 1. Plan

1. Fix the installed skill path mismatch.
   Inputs: forward-test findings, actual repo skill location, current `~/.codex/skills/agent-memory` target.
   Outputs: a working installed skill path that resolves to the real repo skill content.
   Success criteria: the installed skill is readable and validates from the standard Codex location.

2. Harden shell examples in the skill references.
   Inputs: forward-test failures, current example commands.
   Outputs: shell-safe command examples, especially for JSON-bearing arguments.
   Success criteria: copied examples execute without shell quoting surprises.
   Checkpoint: validate the skill after the edits.

3. Investigate and improve `get-context` retrieval quality.
   Inputs: forward-test observation that context returned conversation history only, current `get_context` composition path.
   Outputs: a concrete fix or a narrow, evidenced explanation if the current behavior is structurally limited.
   Success criteria: the same forward-test scenario surfaces useful durable memory in context.
   Checkpoint: rerun the scenario-level command after the fix.

4. Update tracking and the forward-test findings.
   Inputs: actual fixes and retest results.
   Outputs: updated todo and issue note.
   Success criteria: the record reflects the corrected state instead of the first failing observation.

## 2. Dependencies

### Mandatory runtime

- `neo4j`
  Why: `get-context` must be validated on the real graph backend.
  Minimal alternative: none.
- `neo4j-agent-memory` CLI via `uv run`
  Why: the fixes must be validated through the actual shell-first surface.
  Minimal alternative: none.

### Optional runtime

- local embedder mode
  Why: deterministic local validation path.
  Minimal alternative: real provider, not needed here.

### Mandatory dev/test/tooling

- `uv`
  Why: repo-standard execution path.
  Minimal alternative: direct interpreter invocation, but it would diverge from the current workflow.
- Docker or Neo4j Desktop
  Why: local Neo4j runtime for retesting.
  Minimal alternative: none practical.

### Optional dev/test/tooling

- none

## 3. Skills

- `[HAVE]` `voidm-memory`
  Why: continuity and durable capture if a stable product decision emerges.
- `[HAVE]` `general`
  Why: keep the fixes targeted and avoid expanding scope.

## 4. MCP Tools

- `[HAVE]` none
  Why: this tranche is local and shell-first.
