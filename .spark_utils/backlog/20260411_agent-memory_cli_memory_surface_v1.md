# Task: Agent Memory CLI Memory Surface V1

Date: 2026-04-11
Repo: `agent-memory`

## 1. Plan

1. Define the CLI V1 contract for agent memory operations.
   Inputs: current `neo4j-agent-memory` CLI, `CodingAgentMemory`, user requirement for shell-only agent operation.
   Outputs: stable V1 command set and semantics for add, replace, inspect, search, and delete.
   Success criteria: each skill action maps to a real command with no ambiguity.

2. Add a reusable service layer behind the CLI.
   Inputs: `MemoryClient`, `CodingAgentMemory`, `LongTermMemory`, `ShortTermMemory`, `ReasoningMemory`.
   Outputs: thin, testable async operations for sessions, messages, traces, facts, preferences, entities, inspect, and delete.
   Success criteria: command callbacks stay thin and business rules live outside Click handlers.
   Checkpoint: unit tests can exercise service logic without invoking the full CLI.

3. Extend the existing CLI with a `memory` command group.
   Inputs: V1 contract and service layer.
   Outputs: `neo4j-agent-memory memory ...` group under the existing entrypoint.
   Success criteria: the CLI exposes the agent-memory workflow directly.
   Checkpoint: `neo4j-agent-memory memory --help` shows the intended command surface.

4. Implement the minimum viable V1 commands.
   Inputs: CLI group and service layer.
   Outputs:
   - `session-id`
   - `add-message`
   - `delete-message`
   - `start-trace`
   - `add-trace-step`
   - `add-tool-call`
   - `complete-trace`
   - `add-entity`
   - `add-preference`
   - `add-fact`
   - `replace-preference`
   - `replace-fact`
   - `inspect`
   - `search`
   - `get-context`
   - `delete`
   Success criteria: all core CRUD and workflow actions needed by the skill exist.
   Checkpoint: help text and JSON output are coherent and minimal.

5. Test the CLI.
   Inputs: service layer and command implementations.
   Outputs: unit tests for CLI callbacks and integration coverage for critical durable-memory behavior on Neo4j.
   Success criteria:
   - add and delete a message
   - add fact and dedupe exact replay
   - replace fact and supersede previous active fact
   - add preference and dedupe exact replay
   - replace preference and supersede previous active preference
   - add entity and reuse exact same-name same-type entity
   - inspect, search, and get-context work for the CLI surface
   Checkpoint: targeted unit tests and integration tests pass locally.

6. Recenter the `agent-memory` skill on the real CLI.
   Inputs: implemented commands.
   Outputs: updated `SKILL.md` and `references/examples.md` using the actual commands rather than example scripts.
   Success criteria: the skill becomes an operational mode of employment for the CLI surface.
   Checkpoint: skill validation passes after the rewrite.

7. Update project tracking and documentation.
   Inputs: final command surface.
   Outputs: updated todo, any required README mention if the CLI surface is now part of the intended user-facing workflow.
   Success criteria: documentation reflects implemented behavior, not aspirational behavior.
   Checkpoint: final review of affected docs.

## 2. Dependencies

### Mandatory runtime

- `neo4j`
  Why: required for the memory backend.
  Minimal alternative: none.
- `pydantic`
  Why: existing memory models and settings.
  Minimal alternative: none.
- `pydantic-settings`
  Why: configuration loading for the client.
  Minimal alternative: manual env parsing, not worth it here.
- `click`
  Why: existing CLI framework.
  Minimal alternative: ad hoc scripts, which would undermine the CLI surface.
- `rich`
  Why: existing CLI output formatting.
  Minimal alternative: plain stdout only, but the repo already depends on Rich for the CLI.

### Optional runtime

- `gliner`
  Why: useful for extraction flows, but not required for basic memory CRUD commands.
  Minimal alternative: no extraction.

### Mandatory dev/test/tooling

- `pytest`
  Why: command and service tests.
  Minimal alternative: manual testing only, not acceptable for this feature.
- `pytest-asyncio`
  Why: async service and integration coverage.
  Minimal alternative: synchronous wrappers only, which would add needless complexity.
- `uv`
  Why: repository-standard execution workflow.
  Minimal alternative: `pip` plus direct `pytest`, but that would diverge from the repo workflow.
- local Neo4j via Docker or Desktop
  Why: integration tests need the real graph backend.
  Minimal alternative: mocks only, insufficient for durable memory behavior.

### Optional dev/test/tooling

- `click.testing.CliRunner`
  Why: fast, direct CLI testing.
  Minimal alternative: subprocess tests, slower and more brittle.

## 3. Skills

- `[HAVE]` `voidm-memory`
  Why: repo continuity and prior decisions.
- `[HAVE]` `python`
  Why: implementation and tests.
- `[HAVE]` `general`
  Why: keep the CLI simple and aligned with the existing codebase.
- `[MAY NEED]` `skill-creator`
  Why: final skill pass once the CLI surface is stable.

## 4. MCP Tools

- `[HAVE]` none
  Why: this feature is fully local.
