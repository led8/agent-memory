# Task: Agent Memory V1.1 Durable Supersession Edges

Parent backlog: [20260416_agent-memory_v1_1_durable_supersession_edges.md](/Users/adhuy/code/led8/ai/spark/agent-memory/.spark_utils/backlog/20260416_agent-memory_v1_1_durable_supersession_edges.md)

## Checklist
- [x] define supersession-edge semantics
- [x] implement explicit `SUPERSEDED_BY` edges for facts and preferences
- [x] keep default reads stable
- [x] add targeted tests
- [x] update findings and notes

## Notes
- This tranche should strengthen graph structure without expanding into full provenance or governance modeling.
- Semantics kept: metadata stays the default truth for active vs superseded reads, and the graph now also carries `(:Fact)-[:SUPERSEDED_BY]->(:Fact)` and `(:Preference)-[:SUPERSEDED_BY]->(:Preference)` edges for audit and graph-native traversal.
- Write paths covered:
- `CodingAgentMemory.remember_preference()` and `remember_fact()` when they supersede conflicting active entries.
- CLI `replace-preference` and `replace-fact` when they create a new active entry.
- Validation:
- `uv run pytest tests/unit/integrations/test_coding_agent.py -q`
- `NEO4J_URI=bolt://localhost:7687 NEO4J_USERNAME=neo4j NEO4J_PASSWORD=test-password uv run pytest tests/integration/test_coding_agent.py tests/integration/test_memory_cli.py -q`
