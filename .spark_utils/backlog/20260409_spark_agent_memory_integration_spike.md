# Task: Agent Memory Integration Spike

Validated on 2026-04-09.

## Step 1 - Establish a minimal local integration baseline

1. Inspect the local `agent-memory` repo, its Python entry points, and the minimum docs needed for setup.
Inputs: local repository source, `README.md`, `CLAUDE.md`, docs navigation, local Neo4j availability assumptions.
Outputs: a confirmed starting path using `MemoryClient` + `MemorySettings`, plus the exact docs/pages needed.
Success criteria: the integration target is clear and does not depend on MCP or framework wrappers.

Checkpoint:
- Confirm the first integration path is Python API, not MCP.
- Confirm the initial extraction path is local extraction via `GLiNER`, with LLM fallback deferred.

## Step 2 - Prepare the local runtime and configuration

2. Verify the development workflow, dependency manager, and local Neo4j requirements.
Inputs: `pyproject.toml`, make/uv workflow, local Docker/Desktop Neo4j assumptions.
Outputs: a concrete local setup path and the minimum configuration required to connect.
Success criteria: there is a deterministic setup path for running a first memory workflow locally.

Checkpoint:
- Confirm Docker or Neo4j Desktop is the local runtime path.
- Confirm which optional extras are actually required for phase 1.

## Step 3 - Implement a smoke-test integration

3. Create a minimal Python integration example that connects to Neo4j and exercises short-term, long-term, and reasoning memory through `MemoryClient`.
Inputs: `MemoryClient`, `MemorySettings`, local configuration, selected extraction path.
Outputs: one runnable local spike script or example module.
Success criteria: the script can connect, store representative memory items, and call `get_context()` successfully.

Checkpoint:
- Validate connection and basic write/read.
- Validate that `get_context()` returns useful combined context.

## Step 4 - Enable local GLiNER extraction

4. Enable `GLiNER` as the first extraction layer for user messages and validate the resulting entity flow.
Inputs: local Python environment, `gliner` extra, extraction settings, smoke-test script.
Outputs: a working local extraction path using `ExtractorType.GLINER` or a GLiNER-based pipeline.
Success criteria: at least one meaningful entity extraction path works locally without external API keys.

Checkpoint:
- Confirm model install/runtime works locally.
- Decide whether relation extraction stays off until `GLiREL` is intentionally added.

## Step 5 - Define the coding-agent usage model

5. Define a minimal mapping for how this project should use short-term, long-term, and reasoning memory.
Inputs: working spike, current user goals, `agent-memory` concepts, selected phase-1 feature set.
Outputs: a concise usage contract for what goes into each memory layer.
Success criteria: a coding workflow can store conversations, project facts/preferences, and reasoning traces without ambiguity.

Checkpoint:
- Confirm what should be extracted automatically from messages versus written explicitly.
- Confirm whether reasoning traces are part of the first usable workflow or phase 1.5.

## Step 6 - Evaluate what to carry over from `voidm`

6. Identify the specific `voidm` concepts worth porting into the `agent-memory` usage model.
Inputs: `voidm` concepts and docs, working `agent-memory` spike.
Outputs: a short list of carry-over concepts with rationale.
Success criteria: only high-value ideas are retained, without importing `voidm` complexity wholesale.

Checkpoint:
- Decide whether to keep `voidm` in parallel temporarily.
- Decide whether a new skill is warranted after the workflow stabilizes.

## Required Libraries / Dependencies

### Mandatory runtime

- `neo4j`
Why: primary graph backend for `agent-memory`.
Minimal alternative: none if using `agent-memory` as intended.

- `pydantic`, `pydantic-settings`
Why: settings and configuration model used by the package.
Minimal alternative: none practical without forking the package interface.

- `gliner`
Why: chosen local extraction engine for phase 1.
Minimal alternative: `spacy`, but this plan now standardizes on `GLiNER` first.

### Optional runtime

- `glirel`
Why: only needed later if relation extraction is enabled from GLiNER outputs.
Minimal alternative: keep relation extraction disabled initially.

- LLM provider extras such as `openai`
Why: phase-2 fallback extraction and richer extraction pipelines.
Minimal alternative: remain on local extraction only.

### Mandatory dev / test / tooling

- `uv`
Why: repository-standard dependency and execution workflow.
Minimal alternative: `pip`, but it diverges from repo conventions.

- Docker or Neo4j Desktop
Why: local Neo4j runtime.
Minimal alternative: none, a running Neo4j instance is required.

### Optional dev / test / tooling

- Framework integration extras
Why: only needed if the spike targets a specific framework wrapper.
Minimal alternative: Python API only.

## Skills

- `[HAVE]` `voidm-memory`
Why: continuity and selective capture of durable learnings during a non-trivial integration task.

- `[HAVE]` `python`
Why: implementation and validation of the Python API integration.

- `[HAVE]` `general`
Why: keep the integration minimal and avoid premature abstraction.

- `[MAY NEED]` `skill-creator`
Why: create a new `agent-memory` skill only after the workflow stabilizes.

## MCP Tools

- `[HAVE]` Local repo inspection tools
Why: enough to inspect code, docs, examples, and configuration.

- `[MAY NEED]` Web access to official `neo4j.com/labs/agent-memory` docs
Why: useful for exact wording and up-to-date API/config guidance when repo files are not enough.

## Approved Direction

- Start with the Python API, not MCP.
- Keep `voidm` in parallel for now; do not replace it yet.
- Do not replace the `voidm-memory` skill yet.
- Delay any new `agent-memory` skill until the first workflow is proven.
- Prefer local extraction first via `GLiNER`, with LLM fallback kept in view for a later phase.

## Related Sub-Backlogs

- First skill readiness checkpoint: [20260410_agent-memory_first_skill_readiness_checkpoint.md](/Users/adhuy/code/led8/ai/spark/agent-memory/.spark_utils/backlog/20260410_agent-memory_first_skill_readiness_checkpoint.md)
