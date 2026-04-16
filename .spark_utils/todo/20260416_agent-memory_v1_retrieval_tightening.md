# Task: Agent Memory V1 Retrieval Tightening

Parent backlog: [20260416_agent-memory_v1_retrieval_tightening.md](/Users/adhuy/code/led8/ai/spark/agent-memory/.spark_utils/backlog/20260416_agent-memory_v1_retrieval_tightening.md)

## Checklist
- [x] define short-term write cadence rules
- [x] define coding startup recall contract
- [x] implement a tighter coding-oriented context assembly path
- [x] update skill, examples, and high-level docs
- [x] run targeted verification
- [x] update findings and notes

## Notes
- This tranche should improve real coding recall without changing the underlying memory model broadly.
- `CodingAgentMemory.get_startup_recall()` now drives the opinionated coding startup view, and the CLI exposes it as `memory recall`.
- Startup recall uses low-threshold durable search first, then falls back to recent repo-scoped durable memory and current-session reasoning when embeddings do not surface results.
- Verification:
- `uv run pytest tests/unit/integrations/test_coding_agent.py tests/unit/cli/test_memory_cli.py -q`
- `NEO4J_URI=bolt://localhost:7687 NEO4J_USERNAME=neo4j NEO4J_PASSWORD=test-password uv run pytest tests/integration/test_coding_agent.py -q`
- shell replay validated on session `coding/agent-memory/startup-recall-shell-replay/20260416-recall`
