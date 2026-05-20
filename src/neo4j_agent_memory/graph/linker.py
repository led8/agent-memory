"""Cross-layer semantic neighborhood linking.

When a node with an embedding is created (Fact, Preference, Message,
ReasoningTrace), the GraphLinker finds its top-N semantic neighbors across
all vector indexes and creates RELATES_TO edges with scored metadata.

This transforms an isolated vector store into a true knowledge graph where
related knowledge forms meaningful clusters regardless of node type.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j_agent_memory.graph.client import Neo4jClient

logger = logging.getLogger(__name__)

# Vector index registry: label -> index name
VECTOR_INDEX_REGISTRY: dict[str, str] = {
    "Fact": "fact_embedding_idx",
    "Preference": "preference_embedding_idx",
    "Message": "message_embedding_idx",
    "ReasoningTrace": "task_embedding_idx",
}


@dataclass(frozen=True)
class LinkerConfig:
    """Configuration for semantic neighborhood linking.

    Attributes:
        enabled: Whether linking is active (default True)
        max_neighbors: Maximum edges to create per node (default 5)
        min_similarity: Minimum cosine similarity to create an edge (default 0.75)
        cross_label: Search across all node types, not just same-label (default True)
        exclude_labels: Labels to skip during neighborhood search
        link_method: Label stored on edges to identify origin
    """

    enabled: bool = True
    max_neighbors: int = 5
    min_similarity: float = 0.80
    cross_label: bool = True
    exclude_labels: list[str] = field(default_factory=list)
    link_method: str = "embedding_similarity"


@dataclass
class LinkResult:
    """Result of a single neighborhood link creation."""

    target_id: str
    target_label: str
    similarity: float
    created: bool  # False if edge already existed


class GraphLinker:
    """Cross-layer semantic neighborhood linker.

    Queries vector indexes to find semantically similar nodes and creates
    scored RELATES_TO edges between them.
    """

    def __init__(self, client: "Neo4jClient", config: LinkerConfig | None = None):
        self._client = client
        self._config = config or LinkerConfig()

    @property
    def config(self) -> LinkerConfig:
        return self._config

    async def link_to_neighborhood(
        self,
        node_id: str,
        node_label: str,
        embedding: list[float],
        *,
        max_neighbors: int | None = None,
        min_similarity: float | None = None,
        cross_label: bool | None = None,
    ) -> list[LinkResult]:
        """Find semantic neighbors and create RELATES_TO edges.

        Args:
            node_id: ID of the source node
            node_label: Label of the source node (e.g., 'Fact', 'Preference')
            embedding: Embedding vector of the source node
            max_neighbors: Override config max_neighbors
            min_similarity: Override config min_similarity
            cross_label: Override config cross_label

        Returns:
            List of LinkResult for each edge created or skipped.
        """
        if not self._config.enabled:
            return []

        if not embedding:
            return []

        max_n = max_neighbors if max_neighbors is not None else self._config.max_neighbors
        threshold = min_similarity if min_similarity is not None else self._config.min_similarity
        do_cross = cross_label if cross_label is not None else self._config.cross_label

        # Determine which indexes to search
        indexes_to_search = self._resolve_indexes(node_label, do_cross)

        if not indexes_to_search:
            return []

        # Collect candidates from all relevant indexes
        candidates: list[dict[str, Any]] = []
        for label, index_name in indexes_to_search:
            # Query more than max_n per index to allow cross-index ranking
            hits = await self._client.vector_search(
                index_name=index_name,
                query_embedding=embedding,
                limit=max_n + 1,  # +1 to account for self-match
                threshold=threshold,
                return_properties=["id"],
            )
            for hit in hits:
                hit_id = hit.get("id")
                if hit_id and hit_id != node_id:
                    candidates.append(
                        {
                            "id": hit_id,
                            "label": label,
                            "score": hit["score"],
                        }
                    )

        # Rank by similarity and take top N
        candidates.sort(key=lambda c: c["score"], reverse=True)
        top_candidates = candidates[:max_n]

        # Create edges
        results: list[LinkResult] = []
        for candidate in top_candidates:
            created = await self._create_relates_to_edge(
                source_id=node_id,
                source_label=node_label,
                target_id=candidate["id"],
                target_label=candidate["label"],
                similarity=candidate["score"],
            )
            results.append(
                LinkResult(
                    target_id=candidate["id"],
                    target_label=candidate["label"],
                    similarity=candidate["score"],
                    created=created,
                )
            )

        if results:
            created_count = sum(1 for r in results if r.created)
            logger.debug(
                "Linked %s:%s to %d neighbors (%d new edges)",
                node_label,
                node_id[:8],
                len(results),
                created_count,
            )

        return results

    async def backfill(
        self,
        label: str | None = None,
        *,
        batch_size: int = 50,
        max_neighbors: int | None = None,
        min_similarity: float | None = None,
    ) -> int:
        """Backfill neighborhood links for existing nodes that have no RELATES_TO edges.

        Args:
            label: Restrict to a specific label (None = all linkable labels)
            batch_size: Number of nodes to process per batch
            max_neighbors: Override config max_neighbors
            min_similarity: Override config min_similarity

        Returns:
            Total number of edges created.
        """
        labels_to_process = (
            [label] if label else list(VECTOR_INDEX_REGISTRY.keys())
        )

        total_created = 0
        for target_label in labels_to_process:
            if target_label in self._config.exclude_labels:
                continue

            # Find nodes with embeddings but no RELATES_TO edges
            orphans = await self._client.execute_read(
                f"""
                MATCH (n:{target_label})
                WHERE n.embedding IS NOT NULL
                  AND NOT (n)-[:RELATES_TO]-()
                RETURN n.id AS id, n.embedding AS embedding
                LIMIT $batch_size
                """,
                {"batch_size": batch_size},
            )

            for orphan in orphans:
                results = await self.link_to_neighborhood(
                    node_id=orphan["id"],
                    node_label=target_label,
                    embedding=orphan["embedding"],
                    max_neighbors=max_neighbors,
                    min_similarity=min_similarity,
                )
                total_created += sum(1 for r in results if r.created)

        logger.info("Backfill complete: %d edges created", total_created)
        return total_created

    def _resolve_indexes(
        self, source_label: str, cross_label: bool
    ) -> list[tuple[str, str]]:
        """Determine which vector indexes to search."""
        if cross_label:
            return [
                (label, idx)
                for label, idx in VECTOR_INDEX_REGISTRY.items()
                if label not in self._config.exclude_labels
            ]
        else:
            idx = VECTOR_INDEX_REGISTRY.get(source_label)
            if idx and source_label not in self._config.exclude_labels:
                return [(source_label, idx)]
            return []

    async def _create_relates_to_edge(
        self,
        source_id: str,
        source_label: str,
        target_id: str,
        target_label: str,
        similarity: float,
    ) -> bool:
        """Create a RELATES_TO edge if it doesn't exist. Returns True if created."""
        result = await self._client.execute_write(
            f"""
            MATCH (a:{source_label} {{id: $source_id}})
            MATCH (b:{target_label} {{id: $target_id}})
            WHERE NOT (a)-[:RELATES_TO]-(b)
            CREATE (a)-[r:RELATES_TO {{
                similarity: $similarity,
                link_method: $link_method,
                linked_at: datetime()
            }}]->(b)
            RETURN r
            """,
            {
                "source_id": source_id,
                "target_id": target_id,
                "similarity": similarity,
                "link_method": self._config.link_method,
            },
        )
        return len(result) > 0
