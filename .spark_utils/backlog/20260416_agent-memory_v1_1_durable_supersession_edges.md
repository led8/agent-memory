# Task: Agent Memory V1.1 Durable Supersession Edges

Date: 2026-04-16
Repo: `agent-memory`

## 1. Plan

1. Define explicit supersession-edge semantics.
   Inputs: current metadata-driven supersession behavior for facts and preferences, `replace-*` flows, inspect/search behavior.
   Outputs: a precise contract for `SUPERSEDED_BY` edges that stays compatible with existing V1 behavior.
   Success criteria: metadata and edge semantics do not conflict.
   Checkpoint: edge truth rules are documented before code changes.

2. Implement supersession edges in the graph model.
   Inputs: `LongTermMemory`, graph queries, CLI service layer.
   Outputs: explicit `SUPERSEDED_BY` relationships created for fact and preference replacement flows.
   Success criteria: replacement creates the correct edge every time.
   Checkpoint: a real graph inspection shows the expected edge for one fact and one preference case.

3. Keep default reads stable.
   Inputs: current search, inspect, and `get_context` behavior.
   Outputs: unchanged default user-facing behavior with stronger graph structure underneath.
   Success criteria: active entries remain the default surface and superseded entries stay inspectable.
   Checkpoint: existing tests keep passing after the graph change.

4. Cover the feature with targeted tests and docs.
   Inputs: implemented edge behavior.
   Outputs: tests and docs that explain what the edges add without implying full provenance.
   Success criteria: the tranche is graph-native but still clearly below full V2 provenance.
   Checkpoint: targeted tests pass and docs reflect the limited scope.

## 2. Dependencies

### Mandatory runtime

- none
  Why: this tranche should fit into the existing graph backend and codebase.
  Minimal alternative: none.

### Optional runtime

- none

### Mandatory dev/test/tooling

- `pytest`
  Why: validate edge creation and compatibility with current reads.
  Minimal alternative: manual graph inspection only, insufficient.
- `uv`
  Why: repository-standard runner.
  Minimal alternative: direct `.venv` execution, less aligned.
- local Neo4j via Docker
  Why: edge behavior must be verified on the real backend.
  Minimal alternative: mocks only, insufficient.

### Optional dev/test/tooling

- none

## 3. Skills

- `[HAVE]` `voidm-memory`
  Why: preserve repo continuity and durable graph decisions.
- `[HAVE]` `python`
  Why: implement model/query/test changes cleanly.
- `[HAVE]` `general`
  Why: keep this tranche narrow and below full V2 provenance.

## 4. MCP Tools

- `[HAVE]` none
  Why: all work is local.
