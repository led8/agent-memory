# Agent Memory V1.1 Durable Supersession Edges Findings

Date: 2026-04-16
Repo: `agent-memory`

## Summary

V1.1 now keeps the existing metadata-based supersession behavior for `Fact` and
`Preference`, and adds explicit graph edges for the same event:

- `(:Preference {old})-[:SUPERSEDED_BY]->(:Preference {new})`
- `(:Fact {old})-[:SUPERSEDED_BY]->(:Fact {new})`

The old durable entry still carries:

- `status=superseded`
- `superseded_by=<new-id>`
- `superseded_at=<timestamp>`

The new durable entry still carries:

- `status=active`
- `supersedes_ids=[<old-id>, ...]`

## Scope

Implemented for:

- `CodingAgentMemory.remember_preference()`
- `CodingAgentMemory.remember_fact()`
- CLI `replace-preference`
- CLI `replace-fact`

Not expanded into:

- full provenance modeling
- read-surface changes
- new user-facing inspect payloads

## Validation

- `uv run pytest tests/unit/integrations/test_coding_agent.py -q`
- `NEO4J_URI=bolt://localhost:7687 NEO4J_USERNAME=neo4j NEO4J_PASSWORD=test-password uv run pytest tests/integration/test_coding_agent.py tests/integration/test_memory_cli.py -q`

Integration coverage now asserts both:

- metadata supersession on the old entry
- existence of one `SUPERSEDED_BY` edge from old to new
