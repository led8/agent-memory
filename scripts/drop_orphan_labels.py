#!/usr/bin/env python
"""Drop orphan constraints and indexes (Concept, Memory).

These labels were created by a previous schema version and have no nodes
or active code references. Removing them cleans up db.labels().

Usage:
    cd /Users/adhuy/code/led8/ai/spark/agent-memory
    uv run python scripts/drop_orphan_labels.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv

# Load the tool repo .env for NEO4J credentials
load_dotenv()

import os
from pydantic import SecretStr

from neo4j_agent_memory import MemorySettings, Neo4jConfig
from neo4j_agent_memory.graph.client import Neo4jClient


ORPHAN_CONSTRAINTS = ["concept_id", "memory_id"]
ORPHAN_INDEXES = ["concept_id", "memory_id"]


async def main(dry_run: bool = False) -> None:
    config = Neo4jConfig(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        username=os.getenv("NEO4J_USERNAME", "neo4j"),
        password=SecretStr(os.getenv("NEO4J_PASSWORD", "")),
        database=os.getenv("NEO4J_DATABASE", "neo4j"),
    )
    client = Neo4jClient(config)
    await client.connect()

    try:
        for name in ORPHAN_CONSTRAINTS:
            query = f"DROP CONSTRAINT {name} IF EXISTS"
            if dry_run:
                print(f"  [DRY-RUN] {query}")
            else:
                await client.execute_write(query)
                print(f"  [DROPPED] constraint: {name}")

        # After dropping constraints, check if matching indexes still exist
        for name in ORPHAN_INDEXES:
            exists = await client.check_index_exists(name)
            if exists:
                query = f"DROP INDEX {name} IF EXISTS"
                if dry_run:
                    print(f"  [DRY-RUN] {query}")
                else:
                    await client.execute_write(query)
                    print(f"  [DROPPED] index: {name}")
            else:
                print(f"  [SKIP] index {name} not found (already gone with constraint)")

        # Verify
        if not dry_run:
            result = await client.execute_read(
                "SHOW CONSTRAINTS YIELD name WHERE name IN $names RETURN name",
                {"names": ORPHAN_CONSTRAINTS},
            )
            remaining = [r["name"] for r in result]
            if remaining:
                print(f"\n  WARNING: constraints still present: {remaining}")
            else:
                print("\n  All orphan constraints/indexes removed.")

    finally:
        await client.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(main(dry_run=dry_run))
