# Agent Memory Examples

Use this file when the skill rules are not enough and you need a concrete shell workflow.

All commands assume the `memory` CLI group with a local embedder:

```bash
neo4j-agent-memory memory --local-embedder <command> ...
```

If Neo4j connection values are not already configured in the shell, add the connection flags on the `memory` group before the subcommand.

## 1. Build A Task Session

```bash
neo4j-agent-memory memory --local-embedder session-id \
  --repo agent-memory \
  --task "debug extraction"
```

Example result:

```json
{
  "session_id": "coding/agent-memory/debug-extraction/run-1",
  "repo": "agent-memory",
  "task": "debug extraction"
}
```

## 2. Startup Recall

Use `recall` at task start to assemble the repo-scoped coding context for that
session:

```bash
neo4j-agent-memory memory --local-embedder recall \
  --repo agent-memory \
  --task "debug extraction" \
  --session-id "coding/agent-memory/debug-extraction/run-1"
```

This is the opinionated coding-startup view. It keeps the current task stream,
durable repo facts and preferences, entities, and similar reasoning traces in
one compact response.

## 3. Short-Term Memory

### Add The Current User Turn

```bash
neo4j-agent-memory memory --local-embedder add-message \
  --session-id "coding/agent-memory/debug-extraction/run-1" \
  --role user \
  "Investigate why extracted entities are not linked."
```

### Add The Current Assistant Turn

```bash
neo4j-agent-memory memory --local-embedder add-message \
  --session-id "coding/agent-memory/debug-extraction/run-1" \
  --role assistant \
  "I am checking whether the message is linked to the persisted entity id."
```

### Delete A Short-Term Message

```bash
neo4j-agent-memory memory --local-embedder delete-message --id <message-uuid>
```

Use this only when the exact message entry is wrong or should be removed.

Keep `short-term` selective: store the actual task conversation and a few key
observations, not every command and raw terminal output.

## 4. Reasoning Memory

### Start A Trace

```bash
neo4j-agent-memory memory --local-embedder start-trace \
  --session-id "coding/agent-memory/debug-extraction/run-1" \
  --task "debug entity linking"
```

### Add A Trace Step

```bash
neo4j-agent-memory memory --local-embedder add-trace-step \
  --trace-id <trace-uuid> \
  --thought "Check whether the link uses the persisted entity id." \
  --action "Inspect short-term linking logic."
```

### Record A Tool Call

```bash
neo4j-agent-memory memory --local-embedder add-tool-call \
  --step-id <step-uuid> \
  --tool-name rg \
  --arguments-json "{\"pattern\":\"MENTIONS\",\"path\":\"src\"}" \
  --result-text "Found the short-term query." \
  --auto-observation
```

### Complete The Trace

```bash
neo4j-agent-memory memory --local-embedder complete-trace \
  --trace-id <trace-uuid> \
  --outcome "Confirmed the persisted entity id must be reused after MERGE." \
  --success
```

## 5. Long-Term Candidate Review

Use the review block before any durable write.

### High Confidence Preference

```text
[Long-term candidate]
type: preference
scope: repo
content: Use one session_id per active coding task
why: Explicit workflow decision and reusable across future coding tasks.
source: user_explicit
confidence: high
evidence: Confirmed directly during integration planning.
suggested_action: remember_preference
decision_needed: persist | ignore
```

### High Confidence Fact

```text
[Long-term candidate]
type: fact
scope: repo
content: Short-term extraction must use the persisted entity id returned after Neo4j MERGE.
why: Stable implementation rule that prevents missing MENTIONS links.
source: test_verified
confidence: high
evidence: Reproduced bug, fixed it, and validated with targeted integration coverage.
suggested_action: remember_fact
decision_needed: persist | ignore
```

### Medium Confidence Entity

```text
[Long-term candidate]
type: entity
scope: repo
content: GLiNER
why: Relevant extraction component observed repeatedly in the local workflow.
source: run_observation
confidence: medium
evidence: Seen in the active extraction setup during the current run.
suggested_action: remember_entity
decision_needed: persist | ignore
```

This stays review-only by default because an observation alone is not enough for automatic durable storage.

## 6. Durable Writes

### Add A Fact

```bash
neo4j-agent-memory memory --local-embedder add-fact \
  --repo agent-memory \
  --task "debug extraction" \
  --subject "Short-term extraction" \
  --predicate "linking_rule" \
  --object-value "must use persisted entity id returned after Neo4j MERGE"
```

### Add A Preference

```bash
neo4j-agent-memory memory --local-embedder add-preference \
  --repo agent-memory \
  --task "skill design" \
  --category workflow \
  --preference "Prefer explicit CLI CRUD operations" \
  --context "agent-memory skill"
```

### Add Or Reuse An Entity

```bash
neo4j-agent-memory memory --local-embedder add-entity \
  --repo agent-memory \
  --task "skill design" \
  --name "GLiNER" \
  --type OBJECT \
  --description "Local entity extraction component"
```

Exact same-name same-type entity writes should reuse the existing entity.

## 7. Durable Modification

### Replace A Fact

```bash
neo4j-agent-memory memory --local-embedder replace-fact \
  --id <fact-uuid> \
  --object-value "must use the persisted entity id returned by Neo4j after MERGE"
```

This creates a new active fact and supersedes the old one. This is the normal path when a durable fact changes or becomes obsolete.

### Replace A Preference

```bash
neo4j-agent-memory memory --local-embedder replace-preference \
  --id <preference-uuid> \
  --preference "Prefer explicit CLI memory CRUD commands"
```

This creates a new active preference and supersedes the old one. This is the normal path when a durable preference changes or becomes obsolete.

### Update An Entity

Use this when the entity identity stays the same and you are correcting canonical fields:

```bash
neo4j-agent-memory memory --local-embedder update-entity \
  --id <entity-uuid> \
  --name "Neo4j Agent Memory" \
  --description "Graph-native agent memory package"
```

This preserves the entity id and graph links. If the name changes, the old name becomes an alias.

### Add An Alias

Use this when you discover another valid name for the same entity:

```bash
neo4j-agent-memory memory --local-embedder alias-entity \
  --id <entity-uuid> \
  --alias "agent-memory"
```

This is idempotent. If the alias already belongs to another entity, stop and inspect before changing anything else.

### Merge Duplicate Entities

Use this when two entity nodes represent the same real thing:

```bash
neo4j-agent-memory memory --local-embedder merge-entity \
  --source-id <duplicate-entity-uuid> \
  --target-id <canonical-entity-uuid>
```

The target stays canonical. Useful links and aliases are transferred from the source.

### Delete A Bad Entity

Use `delete --kind entity --id <entity-uuid>` only if the entity is clearly wrong, duplicate test noise, or otherwise needs cleanup rather than correction.

## 8. Retrieval

### Startup Recall For Coding Work

```bash
neo4j-agent-memory memory --local-embedder recall \
  --repo agent-memory \
  --task "debug extraction" \
  --session-id "coding/agent-memory/debug-extraction/run-1" \
  --query "debug extraction"
```

### Inspect One Entry

```bash
neo4j-agent-memory memory --local-embedder inspect --kind fact --id <fact-uuid>
```

### Search Facts

```bash
neo4j-agent-memory memory --local-embedder search \
  --kind fact \
  --query "persisted entity id" \
  --threshold 0.0
```

### Search Preferences

```bash
neo4j-agent-memory memory --local-embedder search \
  --kind preference \
  --query "CLI CRUD" \
  --threshold 0.0
```

### Search Messages In One Session

```bash
neo4j-agent-memory memory --local-embedder search \
  --kind message \
  --session-id "coding/agent-memory/debug-extraction/run-1" \
  --query "entity linking" \
  --threshold 0.0
```

### Assemble Generic Combined Context

```bash
neo4j-agent-memory memory --local-embedder get-context \
  --session-id "coding/agent-memory/debug-extraction/run-1" \
  --query "How should I handle durable coding-agent memory from the shell?" \
  --max-items 5
```

Use `get-context` when you want the lower-level generic assembly. Use `recall`
when you want the coding-oriented startup view.

## 9. Delete By UUID

### Delete Durable Memory

```bash
neo4j-agent-memory memory --local-embedder delete --kind fact --id <fact-uuid>
```

### Delete A Preference

```bash
neo4j-agent-memory memory --local-embedder delete --kind preference --id <preference-uuid>
```

### Delete An Entity

```bash
neo4j-agent-memory memory --local-embedder delete --kind entity --id <entity-uuid>
```

Delete only after inspection and only when delete is the right outcome.

For durable memory:
- use `replace-fact` and `replace-preference` when something becomes obsolete but should remain historically traceable
- use `delete` only for cleanup of clearly wrong, duplicate, parasite, or test-only entries

## 10. Confidence Heuristics

### `high`

Use `high` when the candidate is:
- durable
- reusable
- backed by a strong source

Typical sources:
- `user_explicit`
- `code_verified`
- `docs_verified`
- `test_verified`

### `medium`

Use `medium` when the candidate is:
- probably durable
- probably reusable
- still based mainly on observation or early discovery

Typical source:
- `run_observation`

### `low`

Use `low` when the candidate is:
- temporary
- ambiguous
- not reusable enough

Do not propose `low` candidates in V1.

## 11. Empirical Discovery Patterns

### Bug Reproduced And Fixed

This can become `high` when all are true:
- the bug was reproduced
- the fix was applied
- the behavior was verified by rerun or test

### Pattern Better Than The Docs

This starts as `medium` and becomes `high` only after the real repo behavior is confirmed.

### Discovery Across Multiple Runs

This is stronger than a single observation and can justify a durable candidate review.
