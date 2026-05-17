"""Unit tests for GraphLinker — cross-layer semantic neighborhood linking."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from neo4j_agent_memory.graph.linker import (
    GraphLinker,
    LinkerConfig,
    LinkResult,
    VECTOR_INDEX_REGISTRY,
)


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.vector_search = AsyncMock(return_value=[])
    client.execute_write = AsyncMock(return_value=[])
    client.execute_read = AsyncMock(return_value=[])
    return client


@pytest.fixture
def linker(mock_client):
    return GraphLinker(mock_client, LinkerConfig())


@pytest.fixture
def disabled_linker(mock_client):
    return GraphLinker(mock_client, LinkerConfig(enabled=False))


@pytest.fixture
def fake_embedding():
    return [0.1] * 384


class TestLinkerConfig:
    """Tests for LinkerConfig defaults and validation."""

    def test_defaults(self):
        cfg = LinkerConfig()
        assert cfg.enabled is True
        assert cfg.max_neighbors == 5
        assert cfg.min_similarity == 0.75
        assert cfg.cross_label is True
        assert cfg.exclude_labels == []
        assert cfg.link_method == "embedding_similarity"

    def test_custom_config(self):
        cfg = LinkerConfig(
            enabled=False,
            max_neighbors=3,
            min_similarity=0.8,
            cross_label=False,
            exclude_labels=["Message"],
        )
        assert cfg.enabled is False
        assert cfg.max_neighbors == 3
        assert cfg.min_similarity == 0.8
        assert cfg.cross_label is False
        assert cfg.exclude_labels == ["Message"]


class TestLinkToNeighborhood:
    """Tests for the core link_to_neighborhood method."""

    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self, disabled_linker, fake_embedding):
        results = await disabled_linker.link_to_neighborhood(
            node_id="abc", node_label="Fact", embedding=fake_embedding
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_empty_embedding_returns_empty(self, linker):
        results = await linker.link_to_neighborhood(
            node_id="abc", node_label="Fact", embedding=[]
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_no_neighbors_found(self, linker, mock_client, fake_embedding):
        mock_client.vector_search.return_value = []
        results = await linker.link_to_neighborhood(
            node_id="abc", node_label="Fact", embedding=fake_embedding
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_self_match_excluded(self, linker, mock_client, fake_embedding):
        """Node should not link to itself."""
        node_id = str(uuid4())
        mock_client.vector_search.return_value = [
            {"id": node_id, "score": 0.99},  # self
        ]
        results = await linker.link_to_neighborhood(
            node_id=node_id, node_label="Fact", embedding=fake_embedding
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_creates_edges_for_neighbors(self, mock_client, fake_embedding):
        """Should create RELATES_TO edges for qualifying neighbors."""
        # Use cross_label=False to test with a single index
        linker = GraphLinker(mock_client, LinkerConfig(cross_label=False))
        node_id = str(uuid4())
        neighbor1 = str(uuid4())
        neighbor2 = str(uuid4())

        mock_client.vector_search.return_value = [
            {"id": neighbor1, "score": 0.90},
            {"id": neighbor2, "score": 0.85},
        ]
        # Simulate edge creation success
        mock_client.execute_write.return_value = [{"r": {}}]

        results = await linker.link_to_neighborhood(
            node_id=node_id, node_label="Fact", embedding=fake_embedding
        )

        assert len(results) == 2
        assert results[0].target_id == neighbor1
        assert results[0].similarity == 0.90
        assert results[0].created is True
        assert results[1].target_id == neighbor2
        assert results[1].similarity == 0.85

    @pytest.mark.asyncio
    async def test_respects_max_neighbors(self, mock_client, fake_embedding):
        """Should cap at max_neighbors even if more candidates exist."""
        linker = GraphLinker(mock_client, LinkerConfig(max_neighbors=2))
        node_id = str(uuid4())

        # Return many neighbors across multiple indexes
        mock_client.vector_search.return_value = [
            {"id": str(uuid4()), "score": 0.95},
            {"id": str(uuid4()), "score": 0.90},
            {"id": str(uuid4()), "score": 0.85},
        ]
        mock_client.execute_write.return_value = [{"r": {}}]

        results = await linker.link_to_neighborhood(
            node_id=node_id, node_label="Fact", embedding=fake_embedding
        )

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_cross_label_searches_all_indexes(self, linker, mock_client, fake_embedding):
        """When cross_label=True, should search all vector indexes."""
        node_id = str(uuid4())
        mock_client.vector_search.return_value = []

        await linker.link_to_neighborhood(
            node_id=node_id, node_label="Fact", embedding=fake_embedding
        )

        # Should have called vector_search once per index in VECTOR_INDEX_REGISTRY
        assert mock_client.vector_search.call_count == len(VECTOR_INDEX_REGISTRY)

    @pytest.mark.asyncio
    async def test_same_label_only(self, mock_client, fake_embedding):
        """When cross_label=False, should search only same-label index."""
        linker = GraphLinker(mock_client, LinkerConfig(cross_label=False))
        node_id = str(uuid4())
        mock_client.vector_search.return_value = []

        await linker.link_to_neighborhood(
            node_id=node_id, node_label="Fact", embedding=fake_embedding
        )

        assert mock_client.vector_search.call_count == 1
        call_args = mock_client.vector_search.call_args
        assert call_args[1]["index_name"] == "fact_embedding_idx"

    @pytest.mark.asyncio
    async def test_exclude_labels(self, mock_client, fake_embedding):
        """Excluded labels should not be searched."""
        linker = GraphLinker(
            mock_client, LinkerConfig(exclude_labels=["Message", "ReasoningTrace"])
        )
        node_id = str(uuid4())
        mock_client.vector_search.return_value = []

        await linker.link_to_neighborhood(
            node_id=node_id, node_label="Fact", embedding=fake_embedding
        )

        # Only Fact and Preference indexes should be queried
        assert mock_client.vector_search.call_count == 2

    @pytest.mark.asyncio
    async def test_edge_already_exists_returns_created_false(
        self, mock_client, fake_embedding
    ):
        """If edge already exists, created should be False."""
        linker = GraphLinker(mock_client, LinkerConfig(cross_label=False))
        node_id = str(uuid4())
        neighbor = str(uuid4())

        mock_client.vector_search.return_value = [{"id": neighbor, "score": 0.88}]
        # Empty result means WHERE NOT clause prevented creation
        mock_client.execute_write.return_value = []

        results = await linker.link_to_neighborhood(
            node_id=node_id, node_label="Fact", embedding=fake_embedding
        )

        assert len(results) == 1
        assert results[0].created is False

    @pytest.mark.asyncio
    async def test_override_params(self, linker, mock_client, fake_embedding):
        """Call-site overrides should take precedence over config."""
        node_id = str(uuid4())
        neighbor = str(uuid4())
        mock_client.vector_search.return_value = [{"id": neighbor, "score": 0.95}]
        mock_client.execute_write.return_value = [{"r": {}}]

        results = await linker.link_to_neighborhood(
            node_id=node_id,
            node_label="Fact",
            embedding=fake_embedding,
            max_neighbors=1,
            min_similarity=0.9,
            cross_label=False,
        )

        # cross_label=False means only one index searched
        assert mock_client.vector_search.call_count == 1
        # min_similarity=0.9 passed as threshold
        call_kwargs = mock_client.vector_search.call_args[1]
        assert call_kwargs["threshold"] == 0.9


class TestBackfill:
    """Tests for the backfill method."""

    @pytest.mark.asyncio
    async def test_backfill_processes_orphan_nodes(self, linker, mock_client, fake_embedding):
        """Backfill should find orphan nodes and link them."""
        orphan_id = str(uuid4())
        neighbor_id = str(uuid4())

        # First call: find orphans
        mock_client.execute_read.return_value = [
            {"id": orphan_id, "embedding": fake_embedding}
        ]
        # Vector search returns a neighbor
        mock_client.vector_search.return_value = [
            {"id": neighbor_id, "score": 0.88}
        ]
        # Edge creation succeeds
        mock_client.execute_write.return_value = [{"r": {}}]

        total = await linker.backfill(label="Fact", batch_size=10)

        assert total >= 1

    @pytest.mark.asyncio
    async def test_backfill_no_orphans(self, linker, mock_client):
        """Backfill with no orphans creates no edges."""
        mock_client.execute_read.return_value = []

        total = await linker.backfill(label="Fact")

        assert total == 0

    @pytest.mark.asyncio
    async def test_backfill_respects_exclude_labels(self, mock_client, fake_embedding):
        """Excluded labels should be skipped during backfill."""
        linker = GraphLinker(
            mock_client, LinkerConfig(exclude_labels=["Message"])
        )
        mock_client.execute_read.return_value = []

        await linker.backfill()

        # Should NOT query for Message orphans
        queries_made = [
            call[0][0] for call in mock_client.execute_read.call_args_list
        ]
        for q in queries_made:
            assert "Message" not in q


class TestResolveIndexes:
    """Tests for _resolve_indexes helper."""

    def test_cross_label_returns_all(self):
        linker = GraphLinker(AsyncMock(), LinkerConfig())
        indexes = linker._resolve_indexes("Fact", cross_label=True)
        assert len(indexes) == len(VECTOR_INDEX_REGISTRY)

    def test_same_label_returns_one(self):
        linker = GraphLinker(AsyncMock(), LinkerConfig())
        indexes = linker._resolve_indexes("Fact", cross_label=False)
        assert len(indexes) == 1
        assert indexes[0] == ("Fact", "fact_embedding_idx")

    def test_unknown_label_same_label_returns_empty(self):
        linker = GraphLinker(AsyncMock(), LinkerConfig())
        indexes = linker._resolve_indexes("UnknownLabel", cross_label=False)
        assert indexes == []

    def test_exclude_labels_filtered(self):
        linker = GraphLinker(AsyncMock(), LinkerConfig(exclude_labels=["Fact", "Message"]))
        indexes = linker._resolve_indexes("Preference", cross_label=True)
        labels = [label for label, _ in indexes]
        assert "Fact" not in labels
        assert "Message" not in labels
        assert "Preference" in labels


class TestCreateRelatesToEdge:
    """Tests for _create_relates_to_edge."""

    @pytest.mark.asyncio
    async def test_creates_edge_with_metadata(self, linker, mock_client):
        mock_client.execute_write.return_value = [{"r": {}}]

        created = await linker._create_relates_to_edge(
            source_id="src-1",
            source_label="Fact",
            target_id="tgt-1",
            target_label="Preference",
            similarity=0.87,
        )

        assert created is True
        call_args = mock_client.execute_write.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert "RELATES_TO" in query
        assert "similarity" in query
        assert params["source_id"] == "src-1"
        assert params["target_id"] == "tgt-1"
        assert params["similarity"] == 0.87
        assert params["link_method"] == "embedding_similarity"

    @pytest.mark.asyncio
    async def test_returns_false_when_edge_exists(self, linker, mock_client):
        mock_client.execute_write.return_value = []

        created = await linker._create_relates_to_edge(
            source_id="src-1",
            source_label="Fact",
            target_id="tgt-1",
            target_label="Fact",
            similarity=0.92,
        )

        assert created is False
