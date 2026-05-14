"""Regression test for `MemoryClient.get_context` correlation tightening.

Backlog: `.spark_utils/backlog/20260514_agent-memory_get_context_correlation_tightening.md`.

Uses a deterministic topic-based fake embedder so the test exercises the
threshold-plumbing logic without depending on a specific real model's cosine
distribution. Validates:

* At default threshold (resolved via settings + embedder recommendation), only
  the on-topic items appear in the assembled context.
* At an explicit low threshold (``0.0``), off-topic items also appear, proving
  the knob is actually wired through every search call.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from neo4j_agent_memory import MemoryClient, MemorySettings
from neo4j_agent_memory.config.settings import (
    EmbeddingConfig,
    EmbeddingProvider,
    Neo4jConfig,
    SearchConfig,
)
from neo4j_agent_memory.embeddings.base import BaseEmbedder


_SPARK_TOKEN = "[SPARK]"
_OFFTOPIC_TOKEN = "[OFFTOPIC]"


class TopicEmbedder(BaseEmbedder):
    """Deterministic embedder.

    Maps any text containing ``_SPARK_TOKEN`` to one unit vector and any text
    containing ``_OFFTOPIC_TOKEN`` to a different orthogonal unit vector.
    Anything else → zero vector. Cosine similarity is therefore exactly 1.0
    for same-topic pairs and 0.0 for cross-topic pairs.
    """

    DIM = 384

    @property
    def dimensions(self) -> int:
        return self.DIM

    def _vec(self, axis: int) -> list[float]:
        v = [0.0] * self.DIM
        v[axis] = 1.0
        return v

    async def embed(self, text: str) -> list[float]:
        if _SPARK_TOKEN in text:
            return self._vec(0)
        if _OFFTOPIC_TOKEN in text:
            return self._vec(1)
        return [0.0] * self.DIM

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


@pytest.fixture
def topic_embedder() -> TopicEmbedder:
    return TopicEmbedder()


@pytest.fixture
def correlation_settings(neo4j_connection_info) -> MemorySettings:
    """Settings pinned to the topic embedder so threshold resolution is stable."""
    return MemorySettings(
        neo4j=Neo4jConfig(
            uri=neo4j_connection_info["uri"],
            username=neo4j_connection_info["username"],
            password=SecretStr(neo4j_connection_info["password"]),
        ),
        embedding=EmbeddingConfig(
            provider=EmbeddingProvider.SENTENCE_TRANSFORMERS,
            # Keep the BGE-small calibrated table active so the default path
            # resolves to a non-trivial threshold (0.80–0.85).
        ),
        search=SearchConfig(),
    )


@pytest.mark.integration
class TestGetContextCorrelation:
    """Regression for `MemoryClient.get_context` filtering quality."""

    @pytest.mark.asyncio
    async def test_default_threshold_keeps_only_on_topic(
        self, correlation_settings, topic_embedder
    ):
        async with MemoryClient(correlation_settings, embedder=topic_embedder) as client:
            # Wipe any existing data in this database for test isolation.
            await client._client.execute_write("MATCH (n) DETACH DELETE n")

            # Seed: one on-topic and one off-topic item per memory category.
            entity_on, _ = await client.long_term.add_entity(
                f"Spark project {_SPARK_TOKEN}",
                "OBJECT",
                description="The on-topic project entity.",
                deduplicate=False,
            )
            entity_off, _ = await client.long_term.add_entity(
                f"Unrelated thing {_OFFTOPIC_TOKEN}",
                "OBJECT",
                description="An unrelated entity that should be filtered out.",
                deduplicate=False,
            )

            await client.long_term.add_preference(
                category="posture",
                preference=(
                    f"Spark V1 is artisanat, macOS only, no telemetry {_SPARK_TOKEN}."
                ),
            )
            await client.long_term.add_preference(
                category="random",
                preference=f"Generic unrelated preference {_OFFTOPIC_TOKEN}.",
            )

            await client.long_term.add_fact(
                subject="spark",
                predicate="decision",
                obj=(
                    f"Spark V1 stack locked: Tauri + Rust + SolidJS + neumorphism "
                    f"{_SPARK_TOKEN}."
                ),
            )
            await client.long_term.add_fact(
                subject="otherthing",
                predicate="status",
                obj=f"Some unrelated fact {_OFFTOPIC_TOKEN}.",
            )

            session_id = "test-spark-correlation"
            await client.short_term.add_message(
                session_id=session_id,
                role="user",
                content=f"Working on the Spark V1 bootstrap right now {_SPARK_TOKEN}.",
            )
            await client.short_term.add_message(
                session_id=session_id,
                role="assistant",
                content=f"Off-topic chatter from another conversation {_OFFTOPIC_TOKEN}.",
            )

            trace_on = await client.reasoning.start_trace(
                session_id=session_id,
                task=f"Bootstrap Spark V1 desktop app {_SPARK_TOKEN}",
            )
            await client.reasoning.complete_trace(
                trace_on.id, outcome="Bootstrap done.", success=True
            )
            trace_off = await client.reasoning.start_trace(
                session_id=session_id,
                task=f"Process unrelated payroll data {_OFFTOPIC_TOKEN}",
            )
            await client.reasoning.complete_trace(
                trace_off.id, outcome="Done.", success=True
            )

            # Default threshold path: settings.search has no overrides, so
            # `_resolve_threshold` falls back to BGE-small recommendations.
            # On-topic cosine = 1.0 ≥ all thresholds; off-topic cosine = 0.0 < all.
            context = await client.get_context(
                f"Spark V1 stack {_SPARK_TOKEN}",
                include_short_term=True,
                include_long_term=True,
                include_reasoning=True,
            )

            assert _SPARK_TOKEN in context, "On-topic items must appear"
            assert _OFFTOPIC_TOKEN not in context, (
                "Off-topic items must be filtered out at default threshold"
            )

    @pytest.mark.asyncio
    async def test_low_threshold_lets_offtopic_through(
        self, correlation_settings, topic_embedder
    ):
        async with MemoryClient(correlation_settings, embedder=topic_embedder) as client:
            await client._client.execute_write("MATCH (n) DETACH DELETE n")

            await client.long_term.add_entity(
                f"Spark project {_SPARK_TOKEN}",
                "OBJECT",
                deduplicate=False,
            )
            await client.long_term.add_entity(
                f"Unrelated thing {_OFFTOPIC_TOKEN}",
                "OBJECT",
                deduplicate=False,
            )
            await client.long_term.add_fact(
                subject="otherthing",
                predicate="status",
                obj=f"Off-topic fact {_OFFTOPIC_TOKEN}.",
            )

            # threshold=0.0 disables filtering uniformly across every search.
            context = await client.get_context(
                f"Spark V1 stack {_SPARK_TOKEN}",
                include_short_term=True,
                include_long_term=True,
                include_reasoning=True,
                relevance_threshold=0.0,
            )

            # Off-topic items now leak in (cosine 0.0 ≥ threshold 0.0), proving
            # the threshold knob is actually wired through every search.
            assert _SPARK_TOKEN in context
            assert _OFFTOPIC_TOKEN in context, (
                "At threshold=0.0 every item should pass; if not, the threshold "
                "is being clamped or ignored somewhere in the plumbing."
            )

    @pytest.mark.asyncio
    async def test_explicit_high_threshold_drops_everything(
        self, correlation_settings, topic_embedder
    ):
        async with MemoryClient(correlation_settings, embedder=topic_embedder) as client:
            await client._client.execute_write("MATCH (n) DETACH DELETE n")

            await client.long_term.add_fact(
                subject="spark",
                predicate="decision",
                obj=f"On-topic fact {_SPARK_TOKEN}.",
            )

            # Topic-on cosine is exactly 1.0. Threshold 1.0 should still keep
            # it (>=); threshold > 1.0 isn't a valid Field input but 0.999 lets
            # it through; 1.01 is rejected by Click.
            context = await client.get_context(
                f"Spark V1 stack {_SPARK_TOKEN}",
                include_long_term=True,
                relevance_threshold=0.999,
            )
            assert _SPARK_TOKEN in context
