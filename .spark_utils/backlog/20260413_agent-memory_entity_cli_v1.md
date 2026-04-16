# Task: Agent Memory Entity CLI V1

Date: 2026-04-13
Repo: `agent-memory`

## 1. Plan

1. Define the entity CLI V1 contract.
   Inputs: current entity model, alias handling, merge behavior, user requirement for a more complete V1.
   Outputs: stable semantics for `update-entity`, `alias-entity`, `merge-entity`, and `delete`.
   Success criteria: no ambiguity between correcting an entity, adding an alias, merging duplicates, and cleaning up bad data.

2. Fix entity alias consistency in the core model.
   Inputs: `LongTermMemory.add_entity`, `_add_alias_to_entity`, query builder, parse logic.
   Outputs: aliases handled consistently in stored graph properties and parsed entities.
   Success criteria: alias-based retrieval works reliably for add, alias, and merge flows.
   Checkpoint: targeted tests prove aliases survive round-trips.

3. Add reusable entity operations behind the CLI.
   Inputs: `MemoryCliService`, `LongTermMemory`, graph queries.
   Outputs: testable service helpers for `update_entity`, `alias_entity`, and `merge_entity`.
   Success criteria: Click handlers stay thin and entity semantics live in reusable code.
   Checkpoint: unit tests can cover the service behavior without shelling out.

4. Extend the `memory` CLI group.
   Inputs: finalized semantics and service helpers.
   Outputs:
   - `update-entity`
   - `alias-entity`
   - `merge-entity`
   Success criteria: V1 exposes a safe shell-first entity workflow without introducing `replace-entity`.
   Checkpoint: `neo4j-agent-memory memory --help` shows the new commands.

5. Test the entity surface.
   Inputs: updated core model, service layer, CLI commands.
   Outputs: unit and integration coverage for entity updates, aliases, and merges.
   Success criteria:
   - `update-entity` preserves identity and relationships
   - `alias-entity` is idempotent and blocks obvious collisions
   - `merge-entity` preserves useful graph structure and aliases
   Checkpoint: targeted CLI integration tests pass on local Neo4j.

6. Update the skill and references.
   Inputs: implemented commands.
   Outputs: `agent-memory` skill and examples reflect the real V1 entity workflow.
   Success criteria: the skill explains entity maintenance without the old manual workaround.
   Checkpoint: skill validation passes.

7. Update tracking and high-level docs if needed.
   Inputs: final entity CLI surface.
   Outputs: todo/backlog updated and README adjusted only if the new commands are explicitly user-facing.
   Success criteria: docs describe the actual entity workflow.

## 2. Dependencies

### Mandatory runtime

- `neo4j`
  Why: entity workflows and merges are graph-native operations.
  Minimal alternative: none.
- `click`
  Why: existing CLI framework.
  Minimal alternative: ad hoc scripts, which would undermine the CLI surface.
- `pydantic` and `pydantic-settings`
  Why: existing configuration and models.
  Minimal alternative: none worth introducing here.

### Optional runtime

- none expected
  Why: the required alias and merge primitives already exist in the repo.

### Mandatory dev/test/tooling

- `pytest`
  Why: entity command and integration coverage.
  Minimal alternative: manual testing only, not acceptable.
- `uv`
  Why: repository-standard execution path.
  Minimal alternative: direct `pip` workflow, but that diverges from the repo.
- local Neo4j via Docker/Desktop
  Why: merge behavior must be validated on the real graph backend.
  Minimal alternative: mocks only, insufficient here.

### Optional dev/test/tooling

- `click.testing.CliRunner`
  Why: direct CLI tests without subprocess overhead.
  Minimal alternative: subprocess tests, slower and noisier.

## 3. Skills

- `[HAVE]` `voidm-memory`
  Why: continuity for durable repo decisions and prior entity-memory choices.
- `[HAVE]` `python`
  Why: implementation and test work.
- `[HAVE]` `general`
  Why: keep the surface simple and safe.
- `[MAY NEED]` `skill-creator`
  Why: final skill pass once the entity CLI commands are stable.

## 4. MCP Tools

- `[HAVE]` none
  Why: this tranche is entirely local.
