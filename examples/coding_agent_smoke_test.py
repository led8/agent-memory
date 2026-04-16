#!/usr/bin/env python3
"""
Minimal local smoke test for integrating neo4j-agent-memory into coding workflows.

This script intentionally keeps the first pass simple:
- real Neo4j backend
- real MemoryClient
- local deterministic embedder (no external API keys)
- local GLiNER extraction on user messages
- no LLM fallback
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import re
from dataclasses import dataclass
from typing import Iterable
from uuid import uuid4

from pydantic import SecretStr

from neo4j_agent_memory import (
    EmbeddingConfig,
    EmbeddingProvider,
    ExtractionConfig,
    ExtractorType,
    MemoryClient,
    MemorySettings,
    MessageRole,
    Neo4jConfig,
    ResolverStrategy,
    ResolutionConfig,
    ToolCallStatus,
)


TOKEN_RE = re.compile(r"[a-z0-9_]+")


@dataclass
class LocalHashedEmbedder:
    """Small deterministic embedder with useful lexical overlap behavior.

    This is not a semantic model. It is only meant to make local smoke tests
    meaningful enough to exercise vector search and context assembly without
    requiring external providers or heavy local ML installs.
    """

    dimensions: int = 384

    def _tokenize(self, text: str) -> list[str]:
        return TOKEN_RE.findall(text.lower())

    def _bucket(self, token: str) -> int:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % self.dimensions

    async def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = self._tokenize(text)
        if not tokens:
            return vector

        for token in tokens:
            vector[self._bucket(token)] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector

        return [value / norm for value in vector]

    async def embed_batch(self, texts: Iterable[str]) -> list[list[float]]:
        return [await self.embed(text) for text in texts]


def build_settings() -> MemorySettings:
    """Build a local-only settings object for the first integration spike."""
    dimensions = 384
    return MemorySettings(
        neo4j=Neo4jConfig(
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            username=os.getenv("NEO4J_USERNAME", "neo4j"),
            password=SecretStr(os.getenv("NEO4J_PASSWORD", "test-password")),
            database=os.getenv("NEO4J_DATABASE", "neo4j"),
        ),
        embedding=EmbeddingConfig(
            provider=EmbeddingProvider.CUSTOM,
            model="local-hashed-overlap",
            dimensions=dimensions,
        ),
        extraction=ExtractionConfig(
            extractor_type=ExtractorType.GLINER,
            enable_spacy=False,
            enable_gliner=True,
            enable_llm_fallback=False,
            gliner_model=os.getenv("NAM_GLINER_MODEL", "gliner-community/gliner_medium-v2.5"),
            gliner_threshold=float(os.getenv("NAM_GLINER_THRESHOLD", "0.3")),
            gliner_device=os.getenv("NAM_GLINER_DEVICE", "cpu"),
            extract_relations=False,
            extract_preferences=False,
        ),
        resolution=ResolutionConfig(
            strategy=ResolverStrategy.NONE,
        ),
    )


async def main() -> None:
    session_id = os.getenv("NAM_SMOKE_SESSION_ID", f"coding-agent-smoke-{uuid4().hex[:8]}")
    embedder = LocalHashedEmbedder(dimensions=384)
    settings = build_settings()

    async with MemoryClient(settings, embedder=embedder) as memory:
        print("Connected to Neo4j Agent Memory")
        print(f"Session ID: {session_id}")

        user_message = await memory.short_term.add_message(
            session_id,
            MessageRole.USER,
            (
                "I am Adhuy. I am integrating Neo4j Agent Memory in Paris for coding agents. "
                "I care about local iteration, explicit memory layers, and concise technical guidance."
            ),
            extract_entities=True,
            extract_relations=False,
        )
        await memory.short_term.add_message(
            session_id,
            MessageRole.ASSISTANT,
            (
                "Start with a small Python API smoke test against local Neo4j, "
                "then layer GLiNER extraction and richer recall after the base flow works."
            ),
            extract_entities=False,
        )

        person, _ = await memory.long_term.add_entity(
            name="voidm",
            entity_type="OBJECT",
            description="Existing local memory CLI kept in parallel during the Neo4j Agent Memory spike.",
            resolve=False,
            deduplicate=False,
            enrich=False,
            geocode=False,
        )
        await memory.long_term.add_preference(
            category="workflow",
            preference="Prefers incremental integration spikes before enabling heavier NLP extraction.",
            context="Neo4j Agent Memory integration for coding workflows",
        )
        await memory.long_term.add_fact(
            subject="Neo4j Agent Memory",
            predicate="best_start",
            obj="Python API smoke test with local Neo4j and local deterministic embeddings",
        )

        trace = await memory.reasoning.start_trace(
            session_id,
            task="Start Neo4j Agent Memory integration for coding workflows",
            triggered_by_message_id=user_message.id,
        )
        step = await memory.reasoning.add_step(
            trace.id,
            thought="Validate the base memory flow locally before adding any LLM fallback.",
            action="create local smoke test",
            observation="A deterministic local embedder removes API dependencies while GLiNER provides local extraction.",
        )
        await memory.reasoning.record_tool_call(
            step.id,
            tool_name="docker compose",
            arguments={"service": "neo4j", "file": "docker-compose.test.yml"},
            result={"status": "ready"},
            status=ToolCallStatus.SUCCESS,
            duration_ms=100,
            message_id=user_message.id,
        )
        await memory.reasoning.complete_trace(
            trace.id,
            outcome="Local Neo4j-backed smoke test created for coding workflow integration.",
            success=True,
        )

        summary = await memory.short_term.get_conversation_summary(
            session_id,
            include_entities=True,
        )
        query = "How should I start Neo4j Agent Memory integration for coding workflows?"
        context = await memory.get_context(
            query,
            session_id=session_id,
            max_items=5,
        )
        stats = await memory.get_stats()

        print("\nStored entity:")
        print(f"- {person.display_name} ({person.full_type})")

        print("\nExtracted short-term entities:")
        for entity_name in summary.key_entities or []:
            print(f"- {entity_name}")

        print("\nDatabase-wide memory stats:")
        for key in sorted(stats):
            print(f"- {key}: {stats[key]}")

        print("\nCombined context:")
        print(context or "(empty)")


if __name__ == "__main__":
    asyncio.run(main())
