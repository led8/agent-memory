# Agent Memory Coding-Agent Usage Model

Date: 2026-04-10
Scope: `agent-memory`

## Goal

Define the minimal, concrete way to use `neo4j-agent-memory` for coding-agent workflows without turning the first integration into a full product redesign.

## Working Position

- `agent-memory` is the active memory backend for the spike.
- The integration surface is the Python API, not MCP.
- Local extraction starts with `GLiNER`.
- LLM fallback stays out of phase 1.
- `voidm` stays in parallel until the new workflow proves it can cover the practical startup and learning loop.

## Session Model

Use one `session_id` per active coding task, not one global session forever.

Recommended shape:

- `coding/<repo>/<task-slug>/<timestamp-or-short-id>`

Examples:

- `coding/agent-memory/gliner-smoke-test/20260410-a1b2`
- `coding/spark/neo4j-memory-integration/20260410-c3d4`

Why:

- keeps short-term memory focused
- avoids bloated conversation history
- makes reasoning traces attributable to one task

## Memory Layer Mapping

### Short-Term Memory

Store:

- the actual user requests for the current task
- the actual assistant replies for the current task
- a few key tool-facing observations during the active session
- message metadata when it helps retrieval later

Do not treat as durable knowledge:

- raw repo facts that should outlive the session
- stable preferences
- reusable tactics from past tasks

Coding-agent rule:

- add the actual interaction stream for the current task
- keep short-term selective rather than exhaustive
- do not dump every shell command, raw terminal output, or scratch note
- enable local entity extraction on user messages by default
- keep relation extraction off in phase 1

### Long-Term Memory

Store only things that should survive the current task.

Use `entities` for:

- repositories
- tools and services
- frameworks and libraries
- important project nouns worth linking to messages

Use `preferences` for:

- communication style
- workflow preferences
- personal coding habits
- durable repo-local conventions when they read naturally as preferences

Use `facts` for:

- stable project constraints
- setup truths
- design decisions expressed as declarative triples
- known environment or repo truths that should be searchable later

Coding-agent rule:

- do not rely on auto-extracted entities alone for durable project knowledge
- explicitly add high-value facts and preferences when they become clear
- treat long-term writes as curated, not as a dump of every message
- for curated entities, reuse exact same-type matches first
- let entity resolution and deduplication handle fuzzy or near-duplicate variants
- do not use fact/preference-style supersession for entities; entity ambiguity should flow through resolution, aliases, or `SAME_AS` review instead

### Reasoning Memory

Store:

- traces for non-trivial tasks
- steps with concise, externalizable reasoning summaries
- tool calls, arguments, results, and duration
- success or failure outcome

Do not store:

- every tiny edit
- raw hidden chain-of-thought
- noisy intermediate notes that would not help future retrieval

Coding-agent rule:

- start a trace when the task is multi-step, uncertain, or tool-heavy
- record only the reasoning that would still make sense if another agent reused it later
- complete every trace with a useful outcome summary

## Automatic vs Explicit Ingestion

### Automatic in phase 1

- short-term messages
- GLiNER entity extraction from user messages
- reasoning trace structure when the agent decides a task warrants it

### Explicit in phase 1

- long-term preferences
- long-term facts
- manually curated entities that matter to the repo or workflow
- explicit review and persistence of long-term candidates

### Deferred

- LLM extraction fallback
- relation extraction via `GLiREL`
- automatic promotion from short-term observations into long-term facts/preferences

## Minimal Workflow Contract

For a coding task:

1. Create a task-scoped `session_id`.
2. Run structured startup recall for that task session.
3. Store the task conversation and a few key observations in short-term memory.
4. Let `GLiNER` extract obvious entities from user messages.
5. Start a reasoning trace if the task is non-trivial.
6. When a stable preference or fact becomes clear, first propose it as a reviewed long-term candidate.
7. Persist only reviewed high-confidence candidates explicitly to long-term memory.
8. Keep medium-confidence candidates as review-only unless an operator overrides them on purpose.
9. Use `get_context()` for generic assembly, or coding-oriented startup recall when the task needs the opinionated view.

## Policy V1.1: Long-Term Candidate Review

Long-term memory remains `propose-only` in phase 1.

### Automatic

- short-term message storage
- reasoning traces for non-trivial work

### Never automatic in phase 1

- long-term facts
- long-term preferences
- long-term entities

### Idempotence rule

- reviewed long-term facts and preferences must be idempotent inside the same durable scope
- replaying the same reviewed candidate should return the existing memory instead of creating a duplicate
- the minimal phase-1 duplicate key is:
  - facts: `subject + predicate + object + scope_kind + repo`
  - preferences: `category + preference + context + scope_kind + repo`

### Candidate gate

The agent may propose a long-term candidate only when all of the following are true:

- the source is identifiable
- the information looks durable beyond the current task
- the information is reusable by a future coding run
- the memory type is clear: `fact`, `preference`, or `entity`

Supported sources:

- `user_explicit`
- `code_verified`
- `docs_verified`
- `test_verified`
- `run_observation`

Confidence rule:

- `high`: durable + reusable + strong source
- `medium`: durable + reusable but based only on run observation
- `low`: not durable enough or not reusable enough

Phase-1 decision rule:

- `high` => candidate can be recommended for explicit persistence
- `medium` => candidate stays review-only unless explicitly overridden
- `low` => candidate should not be proposed

Recommended candidate fields:

- `type`
- `scope_kind`
- `content`
- `why_candidate`
- `source`
- `confidence`
- `evidence`
- `suggested_action`

Scope rule:

- use `scope_kind=repo` for project and workflow knowledge
- use `scope_kind=personal` only for durable personal preferences that clearly affect coding work

Contradiction rule:

- do not overwrite durable memories automatically
- preserve provenance
- prefer later supersession over silent replacement
- when a newer active preference conflicts with an older active preference in the same `category + context + scope_kind + repo`, supersede the older one
- when a newer active fact conflicts with an older active fact in the same `subject + predicate + scope_kind + repo`, supersede the older one
- mark older entries with `status=superseded`, `superseded_by`, and `superseded_at`
- add an explicit `SUPERSEDED_BY` edge from the older durable entry to the newer active one
- keep only active entries in default long-term retrieval; superseded entries stay available for audit

## Future Skill Guidance

The future `agent-memory` skill should enforce the same discipline:

- run startup recall at task start
- write to short-term memory selectively for the active task
- open reasoning traces only for non-trivial work
- propose long-term memories as structured candidates first
- persist only reviewed candidates, with `high` confidence by default
- require an explicit override before persisting `medium` confidence candidates
- keep repo-scoped durable knowledge separate from personal durable preferences

## What To Carry Over From `voidm`

### Keep

1. Structured startup recall

- `agent-memory` now has a coding-oriented startup recall on top of raw `get_context()`:
  - `CodingAgentMemory.get_startup_recall()`
  - `neo4j-agent-memory memory recall`
- the same mental model still matters for coding work:
  - architecture
  - constraints
  - decisions
  - procedures
  - preferences

2. Durable knowledge discipline

- `voidm` is strict about not storing task logs as durable memory.
- That rule should stay.

3. Trajectory distillation

- `agent-memory` reasoning traces are useful, but `voidm`'s best idea is distilling traces into reusable tactics.
- This should become a later phase on top of reasoning memory, not during phase 1.

4. Provenance and staleness mindset

- durable memories need source, confidence, and eventually review/supersession behavior

5. Narrow task sessions instead of one giant rolling memory stream

- this maps cleanly onto `agent-memory` short-term sessions

### Do Not Carry Over Yet

1. Full `voidm` memory type taxonomy

- `semantic / procedural / conceptual / contextual / episodic` is useful, but too much for phase 1
- for now, keep the three native `agent-memory` layers and express finer semantics through facts, preferences, metadata, and later conventions

2. Ontology-heavy workflows

- useful later, but not necessary for the first usable coding-agent memory loop

3. Broad CLI-first workflow design

- this spike is explicitly centered on the Python API

## Current Decisions

- Keep `voidm` in parallel temporarily: yes
- Replace `voidm-memory` skill now: no
- Create a new `agent-memory` skill now: yes

Reason:

- the usage model is now stable enough for a shell-first coding workflow skill
- `voidm` still stays useful in parallel for continuity and reusable tactic recall
