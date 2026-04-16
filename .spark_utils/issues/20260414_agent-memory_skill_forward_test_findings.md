# Agent Memory Skill Forward-Test Findings

Date: 2026-04-14
Status: executed
Scope: shell-first forward-test of the current `agent-memory` skill and CLI surface

## Test Baseline

- Neo4j local container was healthy
- CLI used through `uv run neo4j-agent-memory memory ...`
- forward-test data used a separate logical repo scope: `agent-memory-forward-test`
- installed skill path under `~/.codex/skills/agent-memory` was not usable as-is because it still pointed to the old `skills/agent-memory` location
- the actual repo skill content used for the test was:
  - `agent-memory/skills-examples/agent-memory/SKILL.md`
  - `agent-memory/skills-examples/agent-memory/references/examples.md`

## Scenario 1: Short-Term + Reasoning + Durable Fact + Context

### Flow Executed

1. `session-id`
2. `add-message` user
3. `add-message` assistant
4. `start-trace`
5. `add-trace-step`
6. `add-tool-call`
7. `complete-trace`
8. `add-fact`
9. `get-context`

### Result

- the flow is executable end-to-end from the shell
- the command surface is sufficient to perform the scenario without hidden Python object access
- IDs and JSON outputs are usable for chaining

### Findings

- `add-tool-call --arguments-json` is fragile in real shell usage
  - the skill example is not shell-safe as written
  - the JSON argument needed stricter escaping to run successfully
- `get-context` returned conversation history only in this scenario
  - it did not surface the new durable fact
  - it also did not visibly surface reasoning trace content
  - this may be a retrieval design limitation rather than a CLI bug
- every write command emitted a `datetime.utcnow()` deprecation warning
  - not a blocker
  - but noisy enough to degrade UX

## Scenario 2: Durable Preference Supersession

### Flow Executed

1. `add-preference`
2. `replace-preference`
3. `search --kind preference`
4. `inspect --kind preference` on the superseded entry

### Result

- the scenario behaves as intended
- `replace-preference` created a new active preference
- search returned only the active preference
- inspect on the old preference showed:
  - `status: superseded`
  - `superseded_by`
  - `superseded_at`
  - `supersession_reason`

### Findings

- this is one of the cleanest parts of the current V1
- the shell surface and the skill guidance are aligned here

## Scenario 3: Entity Maintenance

### Flow Executed

1. `add-entity` canonical
2. `add-entity` duplicate candidate
3. `update-entity`
4. `alias-entity`
5. `merge-entity`
6. `inspect --kind entity` on target
7. `inspect --kind entity` on merged source
8. `search --kind entity`

### Result

- the entity maintenance surface is viable in practice
- `update-entity` preserved identity and moved the old name into aliases
- `alias-entity` was clean and explicit
- `merge-entity` marked the source with `merged_into`
- alias search found the canonical target

### Findings

- `add-entity` surfaced a useful deduplication signal when the duplicate was created
- the current V1 entity model is usable enough for real maintenance work
- the skill and the CLI are aligned on `update-entity`, `alias-entity`, and `merge-entity`

## Product-Level Conclusions

### What Works Well

- the shell-first CLI is real and usable
- durable preference/fact replacement semantics are understandable
- entity maintenance is materially better than the previous manual workaround
- inspect/search outputs are good enough to support iterative work

### Main Gaps Exposed By The Forward-Test

1. installed skill packaging is inconsistent
   - installed path still points to the old location
   - the skill content in the repo is under `skills-examples/agent-memory`

2. skill examples need more shell-safe quoting
   - especially `--arguments-json`

3. `get-context` is weaker than the rest of the product promise
   - in this run it behaved mostly like recent conversation recall
   - it did not make the newly written durable fact visible

4. there is no obvious shell-first cleanup for whole test sessions / traces
   - durable test entries can be deleted individually
   - but short-term + reasoning cleanup is not equally complete from the CLI

5. write-path warnings are noisy
   - `datetime.utcnow()` deprecation warnings should be removed

## Severity Assessment

- high:
  - installed skill path mismatch
- medium:
  - `get-context` not surfacing durable memory strongly enough
  - shell quoting fragility in examples
- low:
  - deprecation warning noise
  - incomplete shell cleanup ergonomics

## Recommendation

Before changing the policy of the skill:

1. fix the installed skill path
2. harden the example quoting
3. investigate `get-context` retrieval quality
4. then re-run the same forward-test once

## Follow-Up 2026-04-15

### Packaging

- `~/.codex/skills/agent-memory` is now installed as a symlink to:
  - `agent-memory/skills-examples/agent-memory`

### Example Quoting

- the `add-tool-call --arguments-json` example was updated to use escaped double quotes
- the command now runs successfully in a real `zsh -lc` shell path during the rerun

### `get-context` Root Cause

- `long_term.get_context()` did not include `facts` at all
- even after adding facts to the composition path, the local hashed embedder could miss fact recall on some queries
- on the rerun query, the fact similarity score was `0.6599`, below the default `0.7` threshold

### `get-context` Fix

- `long_term.get_context()` now includes a `### Relevant Facts` section
- `search_facts()` now falls back to lexical matching when vector recall returns nothing
- this keeps the vector path intact while preventing obvious durable facts from disappearing in shell workflows

### Verification

- unit CLI tests:
  - `uv run pytest tests/unit/cli/test_memory_cli.py -q`
  - result: `7 passed`
- targeted integration test:
  - `uv run pytest tests/integration/test_memory_cli.py::test_memory_cli_get_context_returns_relevant_memory -q`
  - result: `1 passed`
- shell-first rerun:
  - `add-tool-call` succeeds with the updated quoting
  - `get-context` now returns:
    - `## Relevant Knowledge`
    - `### Relevant Facts`
    - `CLI memory workflow recommended_surface neo4j-agent-memory memory commands`

### Remaining Gap

- write-path `datetime.utcnow()` deprecation warnings are still present
- this is UX noise, not a functional blocker

## Follow-Up 2026-04-15 UTC Cleanup

### Root Cause

- the warning came from runtime model construction paths still using naive `datetime.utcnow()`
- the base `MemoryEntry` model in `core/memory.py` was the main shared source
- short-term, reasoning, long-term conversion helpers and AgentCore types also still had naive UTC defaults/fallbacks

### Fix

- runtime UTC defaults now use timezone-aware timestamps via `datetime.now(datetime.UTC)`
- patched files:
  - `src/neo4j_agent_memory/core/memory.py`
  - `src/neo4j_agent_memory/memory/short_term.py`
  - `src/neo4j_agent_memory/memory/reasoning.py`
  - `src/neo4j_agent_memory/memory/long_term.py`
  - `src/neo4j_agent_memory/integrations/agentcore/types.py`

### Verification

- unit CLI tests:
  - `uv run pytest tests/unit/cli/test_memory_cli.py -q`
  - result: `7 passed`
- targeted integration test:
  - `uv run pytest tests/integration/test_memory_cli.py::test_memory_cli_get_context_returns_relevant_memory -q`
  - result: `1 passed`
- shell-first writes rerun:
  - `add-message`
  - `add-fact`
  - `start-trace`
  - result: no `datetime.utcnow()` deprecation warning; timestamps now serialize with `+00:00`

### Remaining Scope

- `datetime.utcnow()` still exists in `src/neo4j_agent_memory/testing/` helpers and fixtures
- those paths are not user-facing and were left untouched in this cleanup tranche
