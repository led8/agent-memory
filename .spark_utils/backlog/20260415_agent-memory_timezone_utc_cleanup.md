# Task: Agent Memory Timezone UTC Cleanup

## Plan

1. Clean the runtime UTC helpers and direct `datetime.utcnow()` calls.
   - Inputs: `short_term.py`, `reasoning.py`, `long_term.py`, runtime integrations that still build datetimes.
   - Outputs: timezone-aware UTC datetimes in runtime code paths.
   - Success criteria: runtime write paths no longer create naive datetimes.
   - Checkpoint: inspect patched runtime files before test execution.

2. Align impacted tests, mocks, and fixtures only where necessary.
   - Inputs: failing tests or helper code relying on naive datetimes.
   - Outputs: tests compatible with timezone-aware UTC values.
   - Success criteria: targeted memory and CLI tests remain green.
   - Checkpoint: run unit and targeted integration tests.

3. Verify the real CLI symptom is gone.
   - Inputs: local Neo4j container and shell-first memory commands.
   - Outputs: evidence that `memory` write commands no longer emit `datetime.utcnow()` deprecation warnings.
   - Success criteria: replayed shell commands complete without that warning.
   - Checkpoint: rerun a minimal shell scenario.

4. Update tracking and findings.
   - Inputs: test outputs and shell replay observations.
   - Outputs: todo and issue note updated with the cleanup result.
   - Success criteria: the follow-up is traceable and the remaining gaps, if any, are explicit.

## Dependencies

### Mandatory runtime
- Python standard library `datetime`
  - Why: switch from naive `utcnow()` to timezone-aware UTC timestamps.
  - Minimal alternative: none.

### Optional runtime
- None

### Mandatory dev/test/tooling
- `pytest`
  - Why: validate runtime and fixture compatibility.
  - Minimal alternative: manual replay only, which is insufficient.
- `uv`
  - Why: project-standard Python/test runner.
  - Minimal alternative: direct `.venv` execution, less aligned.
- local Neo4j via Docker
  - Why: validate the user-visible CLI warning disappears.
  - Minimal alternative: unit tests only, which do not prove the shell symptom is gone.

### Optional dev/test/tooling
- None

## Skills
- `[HAVE]` `voidm-memory`
  - Why: preserve repo continuity and decisions.
- `[HAVE]` `python`
  - Why: patch Python runtime/tests cleanly.
- `[HAVE]` `general`
  - Why: keep the cleanup local and simple.

## MCP Tools
- `[HAVE]` none
  - Why: all work is local.
