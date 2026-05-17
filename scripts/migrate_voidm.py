"""Migrate approved voidm memories into neo4j-agent-memory.

Usage:
    cd /Users/adhuy/code/led8/ai/spark/agent-memory
    uv run python scripts/migrate_voidm.py [--dry-run]

Reads reviewed entries from /tmp/voidm_to_migrate.json and imports them
as Facts or Preferences with full metadata traceability.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

from pydantic import SecretStr

from neo4j_agent_memory import MemoryClient, MemorySettings
from neo4j_agent_memory.cli.memory_ops import LocalHashedEmbedder


MIGRATE_FILE = Path("/tmp/voidm_to_migrate.json")

# Patterns to split content into subject/predicate/object
# e.g. "Architecture: the Strava web page derives..."
# e.g. "Decision: the Nutrition web chat now treats..."
PREFIX_RE = re.compile(
    r"^(Architecture|Decision|Constraint|Procedure|Workflow|Integration|"
    r"Deployment|Preference|Repository capability|Architecture pivot):\s*",
    re.IGNORECASE,
)


def parse_fact(content: str, voidm_type: str) -> tuple[str, str, str]:
    """Parse voidm content into (subject, predicate, object) triple."""
    m = PREFIX_RE.match(content)
    if m:
        prefix = m.group(1).lower()
        body = content[m.end():]
    else:
        prefix = voidm_type
        body = content

    # Map prefix to predicate
    predicate_map = {
        "architecture": "has architecture",
        "decision": "decided",
        "constraint": "has constraint",
        "procedure": "follows procedure",
        "workflow": "has workflow",
        "integration": "integrates",
        "deployment": "deploys via",
        "preference": "prefers",
        "repository capability": "has capability",
        "architecture pivot": "pivoted to",
    }
    predicate = predicate_map.get(prefix, "states")

    # Extract subject from first clause
    # Try to get the noun before the first verb
    first_sentence = body.split(".")[0] if "." in body else body
    # Simple heuristic: subject is up to first verb-like word
    subject_match = re.match(r"^(the\s+)?(.+?)\s+(now|is|uses|are|was|has|keeps|does|derives|normalizes|treats|exposes|resolves|stores|includes|lives|invokes|does not|setting)\s", body, re.IGNORECASE)
    if subject_match:
        subject = subject_match.group(2).strip().rstrip(",")
        # Cap subject length
        if len(subject) > 80:
            subject = subject[:77] + "..."
    else:
        # Fallback: first 60 chars
        subject = body[:60].rstrip()

    return subject, predicate, body


def parse_preference(content: str) -> tuple[str, str]:
    """Parse voidm content into (category, preference_text)."""
    m = PREFIX_RE.match(content)
    body = content[m.end():] if m else content
    # Infer category from content
    category = "workflow"  # default
    return category, body


async def main(dry_run: bool = False):
    with open(MIGRATE_FILE) as f:
        entries = json.load(f)

    print(f"Loaded {len(entries)} entries to migrate")
    if dry_run:
        print("=== DRY RUN ===\n")

    settings = MemorySettings(
        neo4j={
            "uri": "bolt://localhost:7687",
            "password": SecretStr("spark-agent-memory"),
            "username": "neo4j",
        },
        linker={"enabled": True, "min_similarity": 0.6},
    )
    embedder = LocalHashedEmbedder()

    facts_created = 0
    prefs_created = 0

    async with MemoryClient(settings, embedder=embedder) as client:
        for entry in entries:
            voidm_id = entry["id"]
            voidm_type = entry["type"]
            content = entry["content"]
            scopes = entry.get("scopes") or ""
            tags = json.loads(entry["tags"]) if entry.get("tags") else []
            target = entry.get("_target", "fact")

            metadata = {
                "migration_source": "voidm",
                "voidm_id": voidm_id,
                "voidm_type": voidm_type,
                "voidm_scope": scopes,
                "voidm_tags": tags,
                "voidm_created_at": entry.get("created_at", ""),
            }

            if target == "preference":
                category, pref_text = parse_preference(content)
                if dry_run:
                    print(f"  [PREF] category={category}")
                    print(f"         text={pref_text[:100]}...")
                    print()
                else:
                    p = await client.long_term.add_preference(
                        category=category,
                        preference=pref_text,
                        metadata=metadata,
                    )
                    print(f"  [PREF] {p.id} | {category}: {pref_text[:60]}...")
                prefs_created += 1

            else:
                subject, predicate, obj = parse_fact(content, voidm_type)
                if dry_run:
                    print(f"  [FACT] subject={subject}")
                    print(f"         predicate={predicate}")
                    print(f"         object={obj[:80]}...")
                    print()
                else:
                    f = await client.long_term.add_fact(
                        subject=subject,
                        predicate=predicate,
                        obj=obj,
                        confidence=0.8,
                        metadata=metadata,
                    )
                    print(f"  [FACT] {f.id} | {subject} | {predicate}")
                facts_created += 1

    print(f"\n{'Would create' if dry_run else 'Created'}: {facts_created} facts, {prefs_created} preferences")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(main(dry_run=dry_run))
