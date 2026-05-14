# Database safety — protecting the agent-memory corpus

> **TL;DR**: Integration tests share `bolt://localhost:7687` with the production agent-memory CLI. A `MATCH (n) DETACH DELETE n` in a stray test fixture **will permanently destroy the corpus**. Several layers of guards now exist; understand them before running tests.

## Why this document exists

On 2026-05-14 the integration test suite wiped ~169 production memory nodes (3 messages, 24 entities, 6 preferences, 133 facts, 3 reasoning traces) when run against the user's local Neo4j container at `bolt://localhost:7687`. Neo4j Community Edition has no point-in-time recovery, no Time Machine snapshots existed, and no manual `neo4j-admin database dump` had been taken. The corpus was unrecoverable.

This document describes the four-layer prevention system added in response.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  agent-memory CLI ───── bolt://localhost:7687 ─────► Neo4j      │
│  (~/.local/bin/agent-memory)                       (Docker)     │
│                                                          │       │
│  pytest tests/integration ─── if NEO4J_URI=...   ───────┘       │
│  (when env set)                                                  │
│                                                                  │
│  pytest tests/integration ─── otherwise spawns ephemeral         │
│  (when env unset)            testcontainer                       │
└─────────────────────────────────────────────────────────────────┘
```

The danger: when `NEO4J_URI` points at the user's prod DB, integration tests share the same store as the CLI. Several test fixtures historically did `MATCH (n) DETACH DELETE n` to ensure isolation between tests.

## Layer 1 — Sentinel guard (tests/conftest.py)

Every DB used for integration testing must contain a `:_TestSentinel {id: 'singleton'}` node. Two choke-points enforce this:

### 1.1 Stamp guard (refuses to mark a real DB as test-safe)

The session-scoped `neo4j_connection_info` fixture tries to stamp the sentinel on the target DB. If the DB has any non-sentinel nodes AND no existing sentinel, the fixture aborts with:

```
RuntimeError: REFUSING TO STAMP SENTINEL: target Neo4j at bolt://localhost:7687
has 3 non-test nodes and no :_TestSentinel marker. This looks like a real
corpus...
```

A pristine testcontainer (count = 0) gets stamped automatically. A previously-stamped DB (sentinel already present) gets its `last_seen_at` refreshed.

### 1.2 Wipe guard (refuses to delete from un-stamped DB)

The helper `_safe_wipe_test_db(client)` is the only allowed entry point for `MATCH (n) DETACH DELETE n` operations. It checks for a `:_TestSentinel` first and raises `RuntimeError` if missing:

```python
async def _safe_wipe_test_db(client) -> None:
    rows = await raw.execute_read("MATCH (s:_TestSentinel) RETURN count(s) AS c")
    if rows[0]["c"] == 0:
        raise RuntimeError("REFUSING TO WIPE: target Neo4j has no :_TestSentinel...")
    await raw.execute_write("MATCH (n) WHERE NOT n:_TestSentinel DETACH DELETE n")
```

The helper also excludes the sentinel itself from deletion so it survives across tests.

All `clean_memory_client` and `unique_memory_client` fixtures use `_safe_wipe_test_db`. Custom integration tests must do the same (see `tests/integration/test_get_context_correlation.py` for the pattern).

## Layer 2 — Pre-test auto-backup

The `Makefile` targets `test-integration`, `test-integration-mcp`, `test-all`, and `test-e2e` all depend on `backup-agent-memory` and run an online APOC export before the tests start.

```makefile
test-integration: backup-agent-memory
    uv run pytest tests/integration -v --timeout=300
```

Backups land at `~/.agent-memory-backups/agent-memory-YYYYMMDD-HHMMSS.cypher` and the script keeps the 30 most recent (configurable via `RETENTION=N`). Skip the backup with `make test-integration-raw` if you know the target is throwaway.

The script `scripts/backup_agent_memory.sh` works standalone:

```bash
./scripts/backup_agent_memory.sh
NEO4J_CONTAINER=other-container ./scripts/backup_agent_memory.sh
```

## Layer 3 — Recurring snapshots (optional, opt-in)

`scripts/com.spark.agent-memory.backup.plist` is a launchd agent that runs `backup_agent_memory.sh` every 6 hours. Install:

```bash
cp scripts/com.spark.agent-memory.backup.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.spark.agent-memory.backup.plist
```

Logs at `~/.agent-memory-backups/launchd.{out,err}.log`.

This is opt-in because the user might not want background daemons. Manual `make backup-agent-memory` is sufficient for occasional use.

## Layer 4 — Restoring from backup

The Cypher exports are directly replayable (after stripping the index/constraint statements that already exist):

```bash
grep -v "^CREATE.*INDEX\|^CREATE CONSTRAINT" \
  ~/.agent-memory-backups/agent-memory-YYYYMMDD-HHMMSS.cypher \
  | docker exec -i neo4j-agent-memory-test cypher-shell \
      -u neo4j -p "$NEO4J_PASSWORD"
```

Or use `neo4j-admin database load` if the backup was made via `neo4j-admin database dump` (offline).

## What if I really want tests to share the prod DB?

You almost certainly don't, but if you do, you must opt in explicitly:

```cypher
MERGE (:_TestSentinel {id: 'singleton'})
```

After this, the wipe guard will allow `MATCH (n) WHERE NOT n:_TestSentinel DETACH DELETE n` — which **will delete every other node in your DB**. You have been warned.

The sane alternative is to point `NEO4J_URI` at a separate test container (e.g., spin up a second Neo4j on port 7688 with its own volume) or to leave `NEO4J_URI` unset so testcontainers spawns an ephemeral container per session.

## Decision log

| Date | Decision |
|---|---|
| 2026-05-14 | Sentinel + wipe guard introduced after data-loss incident; pre-test auto-backup wired into Makefile; launchd recurring backup made opt-in. Architectural separation (separate prod/test ports) deferred — sentinel system is sufficient. |
