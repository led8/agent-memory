# Task: Agent Memory Skill Forward Test

Date: 2026-04-14
Repo: `agent-memory`

## 1. Plan

1. Reconfirm the actual skill surface and local runtime assumptions.
   Inputs: installed skill under `~/.codex/skills/agent-memory`, CLI help, current Neo4j local workflow.
   Outputs: a stable test baseline for what the agent is supposed to do from the shell.
   Success criteria: no mismatch between the skill text and the actual CLI commands.

2. Define a small set of realistic forward-test scenarios.
   Inputs: current skill contract and the coding-agent workflow already implemented.
   Outputs: 2-3 scenarios that cover:
   - short-term + reasoning
   - long-term candidate persistence and retrieval
   - entity maintenance
   Success criteria: the scenarios cover the main V1 promises without being synthetic noise.

3. Execute the scenarios exactly through the shell-first skill interface.
   Inputs: local Neo4j, `neo4j-agent-memory memory ...` commands, installed skill guidance.
   Outputs: concrete command transcripts and observed behavior.
   Success criteria: each scenario can be completed using the skill as written, without hidden object-level access.
   Checkpoint: all commands run successfully or fail in a way that is clearly attributable.

4. Evaluate the outcome from a product perspective.
   Inputs: observed results from the scenarios.
   Outputs:
   - what worked cleanly
   - what was ambiguous in the skill
   - what was missing in the CLI
   - what is not a V1 problem
   Success criteria: clear separation between skill ambiguity, product gap, and acceptable V1 rough edges.

5. Record the results for follow-up.
   Inputs: final observations.
   Outputs: a forward-test note under `.spark_utils` and an updated todo.
   Success criteria: the next improvement cycle starts from concrete evidence, not recollection.

## 2. Dependencies

### Mandatory runtime

- `neo4j`
  Why: the full skill relies on the live graph backend.
  Minimal alternative: none.
- `neo4j-agent-memory` CLI via `uv run`
  Why: the forward-test must use the same shell surface the skill teaches.
  Minimal alternative: none, because object-level testing would defeat the purpose.

### Optional runtime

- local embedder mode
  Why: stable local test path without external providers.
  Minimal alternative: real embedding provider, but not needed for this validation.

### Mandatory dev/test/tooling

- `uv`
  Why: repo-standard execution path for the CLI and validation scripts.
  Minimal alternative: direct environment invocation, but it would diverge from the repo workflow.
- Docker or Neo4j Desktop
  Why: local Neo4j runtime for the forward-test.
  Minimal alternative: none practical.

### Optional dev/test/tooling

- none

## 3. Skills

- `[HAVE]` `voidm-memory`
  Why: keep continuity and capture durable repo-level outcomes if the forward-test exposes stable product decisions.
- `[HAVE]` `general`
  Why: keep the evaluation strict and product-focused.

## 4. MCP Tools

- `[HAVE]` none
  Why: this forward-test is purely local and shell-first.
