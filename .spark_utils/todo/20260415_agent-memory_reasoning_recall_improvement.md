# Task: Agent Memory Reasoning Recall Improvement

Parent backlog: [20260415_agent-memory_reasoning_recall_improvement.md](/Users/adhuy/code/led8/ai/spark/agent-memory/.spark_utils/backlog/20260415_agent-memory_reasoning_recall_improvement.md)

## Checklist
- [x] add a fallback trace retrieval path
- [x] enrich the reasoning context formatting
- [x] add targeted reasoning recall tests
- [x] rerun a shell-first scenario
- [x] update findings and notes

## Notes
- Reasoning `get-context` now surfaces key action, tool names, and the latest observation for matched traces.
- Focused validation passed with `test_search_similar_traces_falls_back_to_text_match`, `test_get_context_includes_reasoning_details`, and `test_memory_cli.py`.
- Shell replay confirmed CLI `get-context` returns the reasoning block for `coding/agent-memory/reasoning-recall-shell-replay-final-2/20260416`.
- When validating against one shared Neo4j test instance, keep targeted pytest runs sequential to avoid cleanup races across processes.
