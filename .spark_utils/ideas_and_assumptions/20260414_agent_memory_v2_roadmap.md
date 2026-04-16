# Agent Memory V2 Roadmap

Status: idea and assumptions only  
Date: 2026-04-14  
Context: this note captures likely V2 directions after the current `agent-memory` V1 shell-first integration and skill work. It is not a validated backlog.

## Classification Key

- `V1`: should be part of the baseline usable product or skill contract without broad schema redesign
- `V1.1`: narrow post-V1 strengthening that stays compatible with the current model and shell-first contract
- `V2`: new graph structure, provenance model, governance model, or materially broader automation

## Why V2 Exists

V1 is already usable:
- shell-first CLI for `short-term`, `reasoning`, and curated `long-term`
- explicit durable review flow
- idempotence for facts and preferences
- supersession for facts and preferences
- entity maintenance with `update-entity`, `alias-entity`, `merge-entity`

V2 should push two things further:
- make the memory model more graph-native across all layers
- reduce ambiguity in when and how the agent writes memory

## Product Goals

1. Keep the current V1 safety guarantees.
2. Strengthen graph structure, not just node storage.
3. Improve retrieval quality before adding more automation.
4. Tighten write policy before enabling more automatic writes.
5. Keep the shell-first interface as the primary agent surface.

## Main Gaps In V1

### 1. Short-Term Write Cadence Is Still Too Broad

Classification: `V1`

Why:
- this is mostly a write-policy and skill-contract problem
- it improves retrieval quality without requiring a new graph model
- it should be decided before adding more automation

V1 says to record the active task stream, but it does not yet sharply define how selective the agent should be.

Likely V2 direction:
- store only meaningful external turns
- skip micro-turns and internal tool chatter
- define a stricter cadence for short-term writes

Target effect:
- less noisy session context
- better `get-context`
- lower storage churn

### 2. Facts And Preferences Are Still Only Partly Graph-Native

Classification:
- explicit supersession edges: `V1.1`
- explicit provenance edges: `V2`
- automatic fact-to-entity linking: `V2`

Why:
- explicit `SUPERSEDED_BY` edges are a narrow reinforcement of behavior already present in V1
- provenance edges and automatic linking materially extend the graph model and retrieval semantics

Today they are durable and well-managed, but their lifecycle is still mostly metadata-driven.

Likely V2 direction:
- add explicit graph edges for supersession
- consider explicit provenance edges from durable memory to messages, traces, or evidence sources
- optionally link facts to entities when subject or object matches an entity

Candidate additions:
- `(:Fact)-[:SUPERSEDED_BY]->(:Fact)` -> `V1.1`
- `(:Preference)-[:SUPERSEDED_BY]->(:Preference)` -> `V1.1`
- `(:Fact)-[:SUPPORTED_BY]->(:Message|:ReasoningTrace|:ToolCall)` -> `V2`
- `(:Fact)-[:ABOUT]->(:Entity)` -> `V2`
- `(:Preference)-[:DERIVED_FROM]->(:Message|:ReasoningTrace)` -> `V2`

Target effect:
- true graph traversal for durable memory evolution
- cleaner provenance and auditability
- better explainability for retrieval

### 3. Reasoning Memory Is Structured But Still Underlinked

Classification: `V2`

Why:
- V1 reasoning retrieval is now good enough to be useful
- the remaining gap here is not basic recall anymore, but graph linkage from reasoning into durable outcomes
- that is a schema and provenance extension, not a V1 finish-up

V1 has traces, steps, tools, and message triggers. That is good, but reasoning is not yet strongly connected to durable outcomes.

Likely V2 direction:
- link reasoning traces to durable memories they produced
- link successful traces to reusable procedures or facts
- support reasoning-to-entity references when a trace is about a stable component

Candidate additions:
- `(:ReasoningTrace)-[:PRODUCED]->(:Fact|:Preference|:Entity)` -> `V2`
- `(:ReasoningStep)-[:ABOUT]->(:Entity)` -> `V2`
- `(:ToolCall)-[:OBSERVED]->(:Fact)` -> `V2`

Target effect:
- durable memory can be explained by actual work history
- successful traces become reusable evidence instead of isolated logs

### 4. Long-Term Candidates Exist Logically But Not As First-Class Graph Objects

Classification: `V2`

Why:
- V1 already has a clear and tested review-first policy
- storing candidates as graph objects is governance/history infrastructure, not required for V1 usefulness
- this is valuable, but it should not block a clean V1

In V1, candidate review is a policy and interface pattern, not a stored graph structure.

Likely V2 direction:
- keep V1 review-first behavior
- optionally represent candidates explicitly as reviewable nodes or structured records

Candidate additions:
- `LongTermCandidate` as a lightweight node or review object -> `V2`
- status flow: `proposed -> accepted -> ignored` -> `V2`
- optional reviewer/source metadata -> `V2`

Target effect:
- better review history
- possible future UI or approval workflow
- less hidden logic in the agent prompt alone

### 5. Entity Graph Is Good, But Relationship Quality Is Still Limited

Classification: `V2`

Why:
- V1 entity identity and maintenance are already in a good place
- richer relation extraction is high-risk noise if added too early
- this belongs after retrieval, provenance, and policy are sharper

V1 entity maintenance is solid, but the graph is still stronger on entity identity than on rich semantics.

Likely V2 direction:
- improve relation extraction quality
- review entity-to-entity relations before promoting them
- consider GLiREL or a similar relation extractor only after the policy and retrieval model are stable

Candidate additions:
- reviewed relation ingestion pipeline -> `V2`
- confidence thresholds for `RELATED_TO` -> `V2`
- relation provenance -> `V2`

Target effect:
- richer graph without flooding it with weak links

## Proposed V2 Workstreams

### Workstream A: Retrieval Quality First

Classification:
- stricter short-term write policy: `V1`
- improved startup recall for coding work: `V1`
- more opinionated context assembly than raw `get-context`: `V1.1`

Priority: highest

Deliverables:
- stricter short-term write policy
- improved startup recall for coding work
- more opinionated context assembly than raw `get-context`

Reason:
- retrieval quality matters more than write volume
- the tool becomes useful faster if the returned context is sharper

### Workstream B: Durable Provenance And Supersession Edges

Classification:
- explicit supersession edges: `V1.1`
- explicit evidence/provenance edges: `V2`
- full durable explainability graph: `V2`

Priority: high

Deliverables:
- explicit supersession edges
- explicit evidence/provenance edges
- durable memory explainability

Reason:
- this is the cleanest path to becoming more graph-native without destabilizing V1

### Workstream C: Reasoning-To-Durable Linking

Classification: `V2`

Priority: high

Deliverables:
- links from traces/steps/tool calls to durable memories
- retrieval that can answer not just “what is true” but also “why we know this”

Reason:
- closes the loop between agent work and agent memory

### Workstream D: Richer Entity Semantics

Classification: `V2`

Priority: medium

Deliverables:
- reviewed relation extraction
- better same-as / alias / merge ergonomics
- more robust entity-centric graph retrieval

Reason:
- valuable, but only after provenance and retrieval are stronger

### Workstream E: Candidate Persistence And Review History

Classification: `V2`

Priority: medium

Deliverables:
- optional candidate storage model
- explicit accept / ignore trail
- future UI compatibility

Reason:
- useful for governance and explainability, but not required to make V1 useful

## Suggested Delivery Order

1. Tighten short-term cadence. `V1`
2. Build a stronger startup recall for coding workflows. `V1`
3. Add a more opinionated coding-oriented context assembler above raw `get-context`. `V1.1`
4. Add explicit supersession edges for facts and preferences. `V1.1`
5. Add provenance links from durable memories to messages, traces, or tool calls. `V2`
6. Link reasoning traces to durable outcomes. `V2`
7. Only then consider richer relation extraction such as GLiREL. `V2`
8. Consider candidate persistence after the retrieval model is stable. `V2`

## Non-Goals For Early V2

- full auto-promotion from short-term to long-term
- aggressive LLM fallback everywhere
- generic graph expansion without strong provenance
- replacing the shell-first interface with a hidden programmatic flow

Current reading:
- these remain correctly outside `V1`
- they should stay out of `V1.1` too

## Open Questions

1. Should `short-term` be persisted only for user/assistant turns, or also for selected tool summaries?
2. Should durable provenance be stored as edges, metadata, or both?
3. Should candidate review become a stored object or remain a prompt-time policy?
4. When facts reference named entities, should entity linking be automatic, assisted, or explicit only?
5. Should V2 introduce a dedicated `recall` command for coding-agent startup instead of relying mainly on `get-context`?

## Working Assumption

The safest V2 is not “more automation everywhere.”  
The safest V2 is:
- better graph links
- better provenance
- better retrieval
- then more automation only where the signal is already strong

## Practical Split

Move into the current V1 / V1.1 band:
- stricter short-term write cadence
- clearer startup recall contract for coding work
- more opinionated context assembly for coding tasks
- optional explicit `SUPERSEDED_BY` edges for facts and preferences

Keep in V2:
- durable provenance edges
- reasoning-to-durable graph links
- stored candidate review objects
- automatic durable-to-entity linking
- richer reviewed relation extraction and entity semantics
