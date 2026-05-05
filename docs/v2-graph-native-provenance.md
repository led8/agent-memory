# V2 Graph-Native Provenance & Durable Linking

This document describes the V2 extensions to the neo4j-agent-memory graph model.
V2 adds provenance tracking, reasoning-to-durable linking, candidate persistence,
and confidence-gated relations — all without breaking V1 behavior.

## Design Principles

1. **Provenance is automatic when context exists** — no opt-in required
2. **Candidate persistence is opt-in** — V1 in-memory behavior unchanged by default
3. **Confidence gates default to permissive** — `min_confidence=0.0` means everything passes
4. **No auto-promotion** — short-term never auto-promotes to long-term
5. **Review-first** — low-confidence relations and candidates require explicit review

## Graph Model

```
┌─────────────────────────────────────────────────────────────────────┐
│ PROVENANCE EDGES (Phase A)                                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  (Fact) ─── SUPPORTED_BY ───► (Message | ReasoningTrace | ToolCall) │
│  (Preference) ─── DERIVED_FROM ───► (Message | ReasoningTrace)      │
│  (Fact) ─── ABOUT ───► (Entity)                                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ REASONING-TO-DURABLE LINKING (Phase B)                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  (ReasoningTrace) ─── PRODUCED ───► (Fact | Preference | Entity)    │
│  (ReasoningStep)  ─── ABOUT ───► (Entity)                           │
│  (ToolCall) ─── OBSERVED ───► (Fact)                                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ CANDIDATE PERSISTENCE (Phase C)                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  (:LongTermCandidate) ─── PROPOSED_BY ───► (ReasoningTrace | Msg)   │
│                                                                     │
│  Status flow: proposed → accepted → ignored → expired               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ RELATION PROVENANCE (Phase D)                                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  (Entity) ─── RELATED_TO ───► (Entity)                              │
│    Properties:                                                       │
│      status: active | pending_review | rejected                     │
│      source_message_id, extractor_name, extracted_at                │
│      reviewed_at, reviewed_by                                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Phase A — Durable Provenance Edges

When `CodingAgentMemory.remember_fact()` or `remember_preference()` is called:

1. If an active reasoning trace exists → `SUPPORTED_BY` / `DERIVED_FROM` edge to trace
2. If a last user message exists → `SUPPORTED_BY` / `DERIVED_FROM` edge to message
3. Explicit `evidence_ids` parameter overrides automatic detection
4. `remember_fact()` auto-links to entities matching `subject`/`object` via `ABOUT`

### Retrieval API

```python
provenance = await client.long_term.get_fact_provenance(fact_id)
# Returns: {"fact": {...}, "traces": [...], "messages": [...]}

provenance = await client.long_term.get_preference_provenance(preference_id)
# Returns: {"preference": {...}, "traces": [...], "messages": [...]}

facts = await client.long_term.get_entity_facts(entity_id)
# Returns: [{"fact": {...}, "link_type": "subject", "linked_at": ...}]
```

## Phase B — Reasoning-to-Durable Linking

When a reasoning trace is active and `remember_*()` creates a durable memory:

- `PRODUCED` edge is automatically created from the active trace to the new node
- No extra opt-in needed

### Retrieval API

```python
outcomes = await client.reasoning.get_trace_outcomes(trace_id)
# Returns: {"facts": [...], "preferences": [...], "entities": [...]}

reasoning = await client.reasoning.get_memory_reasoning(fact_id)
# Returns: {"traces": [...], "steps": [...], "tool_calls": [...]}
```

## Phase C — Candidate Persistence

Long-term memory candidates can optionally be persisted as Neo4j nodes:

```python
# Opt-in via persist_candidate=True
candidate = await coding_memory.propose_fact_candidate(
    subject="ruff", predicate="replaces", object_value="flake8",
    persist_candidate=True,  # stores in Neo4j
)

# Review from CLI
neo4j-agent-memory memory list-candidates --status proposed
neo4j-agent-memory memory accept-candidate <id>
neo4j-agent-memory memory ignore-candidate <id>
```

### LongTermCandidate Node

```
(:LongTermCandidate {
    id, type, scope_kind, content, why_candidate, source,
    confidence, evidence, suggested_action, payload,
    status, created_at, reviewed_at, reviewed_by
})
```

When `remember_candidate()` is called and the candidate was persisted, its status
is automatically updated to `accepted`.

## Phase D — Confidence-Gated Relations

Relations below a configurable confidence threshold get `status: pending_review`:

```python
# Via LongTermMemory
await client.long_term.add_relationship(
    source_id, target_id, "WORKS_AT",
    confidence=0.4,
    min_confidence=0.7,  # → status: pending_review
    source_message_id=msg_id,
    extractor_name="GLiRELExtractor",
)

# Review
pending = await client.long_term.list_pending_relations(limit=50)
await client.long_term.review_relation(source_id, target_id, "WORKS_AT", accept=True)

# Provenance
prov = await client.long_term.get_relation_provenance(source_id, target_id, "WORKS_AT")
```

The extraction pipeline (`ShortTermMemory._store_relations`) automatically passes
`source_message_id` and `extractor_name` when storing extracted relations.

## Phase E — Surface Updates

### CLI Commands Added

| Command | Purpose |
|---------|---------|
| `list-candidates` | List pending/accepted/ignored candidates |
| `accept-candidate <id>` | Accept and persist a candidate |
| `ignore-candidate <id>` | Mark candidate as ignored |
| `get-candidate <id>` | Inspect candidate details |
| `list-pending-relations` | List relations awaiting review |
| `review-relation` | Accept or reject a pending relation |
| `get-provenance <kind> <id>` | Get evidence chain for fact/preference/relation |
| `recall --include-provenance` | Annotate recall output with evidence sources |

### Schema Indexes

Three indexes added for `LongTermCandidate`:
- `candidate_id_idx` on `id`
- `candidate_status_idx` on `status`
- `candidate_type_idx` on `type`

### Provenance-Annotated Recall

```bash
neo4j-agent-memory memory recall --repo myrepo --task mytask \
    --session-id my-session --include-provenance
```

When enabled, facts and preferences in recall output include annotations like:
- `[trace:setup linting]` — evidence from a reasoning trace
- `[msg:user]` — evidence from a user message

## Migration Notes

### Breaking Changes

- `propose_*_candidate()` methods are now `async` (all existing callers were already async)
- `add_relationship()` signature gained new optional kwargs (`min_confidence`, `source_message_id`, `extractor_name`)

### Backward Compatibility

- All new behavior is additive — no V1 data or behavior is affected
- `persist_candidate=False` default preserves in-memory-only candidate behavior
- `min_confidence=0.0` default means all relations remain `active` unless threshold is set
- `include_provenance=False` default keeps recall output unchanged
- Provenance edges are created automatically when context exists, but retrieval is opt-in
