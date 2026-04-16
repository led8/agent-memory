# Agent Memory Full Skill Forward-Test Findings

Date: 2026-04-15
Status: executed
Scope: full shell-first forward-test of the current `agent-memory` skill and CLI surface after the post-forward-test fixes and UTC cleanup

## Baseline

- installed skill path resolves:
  - `~/.codex/skills/agent-memory -> agent-memory/skills-examples/agent-memory`
- local Neo4j test container was healthy
- all commands were executed through the real shell-first CLI:
  - `uv run neo4j-agent-memory memory ...`

## Scenario 1: Short-Term + Reasoning + Durable Fact + Context

### Flow Executed

1. `session-id`
2. `add-message` user
3. `add-message` assistant
4. `start-trace`
5. `add-trace-step`
6. `add-tool-call`
7. `add-fact`
8. `complete-trace`
9. `get-context`

### Result

- the full shell-first workflow works end-to-end
- JSON IDs are usable for chaining
- `add-tool-call --arguments-json` is now shell-safe as documented
- `get-context` now surfaces the durable fact correctly

### Observations

- `get-context` returned:
  - recent conversation
  - relevant past messages
  - relevant durable fact
- the reasoning trace itself did not surface in this scenario
- this is not a shell failure, but it confirms that current `get-context` is still stronger on short-term + durable facts than on reasoning recall

## Scenario 2: Preference And Fact Lifecycle

### Preference Result

- `add-preference` worked
- `replace-preference` created a new active entry
- `search --kind preference` returned only the active entry
- `inspect --kind preference` on the old entry showed:
  - `status: superseded`
  - `superseded_by`
  - `superseded_at`
  - `supersession_reason`

### Fact Result

- `add-fact` worked
- `replace-fact` created a new active entry
- `inspect --kind fact` on the old entry showed the same supersession metadata pattern
- `search --kind fact` returned active facts only, but because search is not scope-filtered by default, semantically similar facts from another scenario also appeared

### Product Reading

- supersession behavior is solid
- search behavior is intentionally broad unless the caller constrains it
- this is not a bug, but the skill should continue to treat unscoped search as a wide retrieval surface

## Scenario 3: Entity Lifecycle

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

- the entity lifecycle is viable from the shell
- final target state was correct:
  - updated canonical name preserved
  - aliases contained the old name and the merged duplicate name
- merged source showed:
  - `merged_into`
  - `merged_at`
- alias-oriented search resolved to the canonical target

### Important Note

- `update-entity` and `alias-entity` were launched in parallel once during the test
- intermediate outputs were inconsistent because they touched the same node concurrently
- final sequential inspection was correct
- conclusion: entity maintenance commands should be treated as sequential operations on the same entity

## Scenario 4: `get-context` Quality

### Query: workflow guidance with session

`get-context` returned:
- conversation history
- one relevant preference
- two relevant facts

This is materially aligned with the current skill promise.

### Query: entity-oriented query without session

`get-context` returned:
- a relevant past message
- the workflow preference
- relevant facts
- the canonical entity

This is better than the earlier forward-test and shows that the current product can already combine conversation, durable memory, and entity recall reasonably well.

### Remaining Limitation

- reasoning recall still did not meaningfully surface during the forward-test
- current product strength is:
  - short-term
  - preferences/facts
  - entities
- current product weakness is still:
  - reasoning trace retrieval in everyday `get-context` flows

## Final Verdict

### Ready

- shell-first CRUD surface
- durable preference/fact lifecycle
- entity maintenance surface
- installed skill packaging
- shell example quoting
- durable fact visibility in `get-context`
- UTC warning cleanup on runtime write paths

### Not Yet Strong

- reasoning recall as part of `get-context`
- scoped retrieval ergonomics from the shell when similar durable facts coexist

## Recommendation

- the skill is now good enough for real use and real iteration
- the next improvement should not be another broad refactor
- the most valuable next tranche is to strengthen reasoning retrieval or, at minimum, clarify when users should expect reasoning traces to surface in `get-context`
