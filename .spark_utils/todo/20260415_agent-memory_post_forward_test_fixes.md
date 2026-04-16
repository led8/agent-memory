# Task: Agent Memory Post Forward-Test Fixes

Parent backlog: [20260415_agent-memory_post_forward_test_fixes.md](/Users/adhuy/code/led8/ai/spark/agent-memory/.spark_utils/backlog/20260415_agent-memory_post_forward_test_fixes.md)

## Checklist
- [x] fix the installed skill path
- [x] harden the shell examples
- [x] inspect the `get-context` composition path
- [x] improve or explain `get-context` behavior with evidence
- [x] rerun the affected forward-test flow
- [x] update the findings note

## Notes
- Prior forward-test findings are recorded in `.spark_utils/issues/20260414_agent-memory_skill_forward_test_findings.md`.
- The current repo skill content lives under `skills-examples/agent-memory`.
- Installed Codex skill now points to `skills-examples/agent-memory`.
- `get-context` now includes long-term facts and fact search falls back to lexical matching when vector recall misses.
