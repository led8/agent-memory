# Task: Agent Memory Entity CLI V1

Parent backlog: [20260413_agent-memory_entity_cli_v1.md](/Users/adhuy/code/led8/ai/spark/agent-memory/.spark_utils/backlog/20260413_agent-memory_entity_cli_v1.md)

## Checklist
- [x] define the entity command contract and semantics
- [x] fix alias consistency in the core entity model
- [x] add reusable entity operations behind the CLI
- [x] add `update-entity`, `alias-entity`, and `merge-entity`
- [x] add unit tests for the new entity CLI surface
- [x] add integration coverage for entity updates, aliases, and merges
- [x] update the `agent-memory` skill and references
- [x] run final verification

## Notes
- `replace-entity` stays out of V1.
- `delete` remains cleanup-only.
- `update-entity` is for same-identity corrections, not replacement semantics.
- `_to_python_datetime()` had been broken by a bad helper move; fixed before final verification.
