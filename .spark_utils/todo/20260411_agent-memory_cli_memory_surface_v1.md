# Task: Agent Memory CLI Memory Surface V1

Parent backlog: [20260411_agent-memory_cli_memory_surface_v1.md](/Users/adhuy/code/led8/ai/spark/agent-memory/.spark_utils/backlog/20260411_agent-memory_cli_memory_surface_v1.md)

## Checklist
- [x] define the final V1 command contract and semantics
- [x] add a reusable CLI service layer
- [x] add the `memory` command group to the existing CLI
- [x] implement the V1 memory commands
- [x] add unit tests for the CLI surface
- [x] add integration coverage for critical durable-memory commands
- [x] rewrite the `agent-memory` skill around the real CLI
- [x] run final verification

## Notes
- The skill must explain real commands, not example scripts.
- `replace-*` is preferred over blind in-place mutation for durable facts and preferences.
- `delete` should remain explicit by UUID and type.
- The skill now documents the `neo4j-agent-memory memory ...` surface directly.
- Final verification:
  - `uv run pytest tests/unit/cli/test_memory_cli.py -q`
  - `NEO4J_URI=bolt://localhost:7687 NEO4J_USERNAME=neo4j NEO4J_PASSWORD=test-password uv run pytest tests/integration/test_memory_cli.py -q`
  - `python3 /Users/adhuy/.codex/skills/.system/skill-creator/scripts/quick_validate.py /Users/adhuy/code/led8/ai/spark/agent-memory/skills/agent-memory`
  - `python3 /Users/adhuy/.codex/skills/.system/skill-creator/scripts/quick_validate.py /Users/adhuy/.codex/skills/agent-memory`
