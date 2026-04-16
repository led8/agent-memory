# Agent Memory Reasoning Recall Improvement Findings

Date: 2026-04-16
Status: validated
Scope: reasoning trace recall in `MemoryClient.get_context()` and shell-first CLI `memory get-context`

## Result

- reasoning search now falls back to lexical trace matching when vector recall misses
- reasoning context now includes:
  - key action
  - tool names
  - latest observation
- `MemoryClient.get_context()` no longer nests a duplicate `Similar Past Tasks` heading

## Validation

- focused integration tests passed:
  - `tests/integration/test_reasoning_memory.py::TestReasoningMemorySearch::test_search_similar_traces_falls_back_to_text_match`
  - `tests/integration/test_memory_client.py::TestMemoryClientGetContext::test_get_context_includes_reasoning_details`
- wider CLI integration sweep passed:
  - `tests/integration/test_memory_cli.py`
- shell-first replay passed with:
  - session: `coding/agent-memory/reasoning-recall-shell-replay-final-2/20260416`
  - query: `How should I handle durable coding-agent memory from the shell?`
  - observed context block:
    - `## Similar Past Tasks`
    - `Key action: inspect shell memory context`
    - `Tools: rg`
    - `Observation: Confirmed durable fact recall appears in get-context for shell memory.`

## Implementation Notes

- `GET_TRACE_WITH_STEPS` now returns map projections for steps and tool calls, including `step_id` on tool-call rows so reasoning details can be reconstructed reliably.
- targeted test runs should stay sequential when they share one live Neo4j database, otherwise cleanup from one pytest process can erase another process's trace mid-assertion.
