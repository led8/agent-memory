#!/usr/bin/env python
"""Backfill entities from existing facts' subjects.

Extracts entities from the 'subject' field of all active Fact nodes
and creates Entity nodes + MENTIONS relationships.

Usage:
    cd /Users/adhuy/code/led8/ai/spark/agent-memory
    .venv/bin/python scripts/backfill_entities_from_facts.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

import os

from pydantic import SecretStr

from neo4j_agent_memory import MemoryClient, MemorySettings, Neo4jConfig
from neo4j_agent_memory.config import EmbeddingConfig, EmbeddingProvider


# Subjects to skip (too generic)
SKIP_SUBJECTS = {
    "it", "this", "that", "the", "agent", "system", "user", "memory",
}


def is_entity_worthy(subject: str) -> bool:
    """Subject is entity-worthy if it's a proper noun or multi-token."""
    if subject.lower() in SKIP_SUBJECTS:
        return False
    if len(subject) <= 2:
        return False
    # Multi-token or starts with uppercase
    return len(subject.split()) >= 2 or subject[0].isupper()


async def main(dry_run: bool = False) -> None:
    settings = MemorySettings(
        neo4j=Neo4jConfig(
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            username=os.getenv("NEO4J_USERNAME", "neo4j"),
            password=SecretStr(os.getenv("NEO4J_PASSWORD", "")),
            database=os.getenv("NEO4J_DATABASE", "neo4j"),
        ),
        embedding=EmbeddingConfig(provider=EmbeddingProvider.SENTENCE_TRANSFORMERS),
    )
    async with MemoryClient(settings) as client:
        # Get all active facts
        results = await client.graph.execute_read(
            """
            MATCH (f:Fact)
            WHERE NOT EXISTS { (f)-[:SUPERSEDED_BY]->() }
            RETURN f.id AS id, f.subject AS subject, f.predicate AS predicate, f.object AS object
            """
        )

        facts = list(results)
        print(f"Found {len(facts)} active facts")

        created = 0
        skipped = 0

        for fact in facts:
            subject = fact["subject"]
            if not is_entity_worthy(subject):
                skipped += 1
                continue

            if dry_run:
                print(f"  [DRY-RUN] Would create entity: {subject}")
                created += 1
                continue

            # Check if entity already exists
            existing = await client.graph.execute_read(
                "MATCH (e:Entity {name: $name}) RETURN e.id AS id",
                {"name": subject},
            )
            existing_list = list(existing)

            if existing_list:
                entity_id = existing_list[0]["id"]
                print(f"  [REUSE] {subject} -> {entity_id}")
            else:
                # Create entity — add_entity returns (Entity, DeduplicationResult)
                description = f"{fact['predicate']}: {(fact['object'] or '')[:120]}"
                entity, _dedup = await client.long_term.add_entity(
                    name=subject,
                    entity_type="OBJECT",
                    subtype="CONCEPT",
                    description=description,
                    metadata={"source": "fact_backfill"},
                    generate_embedding=True,
                    deduplicate=True,
                    enrich=False,
                    geocode=False,
                )
                entity_id = str(entity.id)
                print(f"  [CREATE] {subject} -> {entity_id}")

            # Link fact to entity
            if entity_id:
                await client.graph.execute_write(
                    "MATCH (f:Fact {id: $fact_id}) "
                    "MATCH (e:Entity {id: $entity_id}) "
                    "MERGE (f)-[:MENTIONS]->(e)",
                    {"fact_id": fact["id"], "entity_id": str(entity_id)},
                )

            created += 1

        print(f"\nDone: {created} entities processed, {skipped} skipped")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(main(dry_run=dry_run))
