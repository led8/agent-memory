"""Unit tests for V2 relation review, confidence gates, and provenance."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from neo4j_agent_memory.memory.long_term import LongTermMemory


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.execute_write = AsyncMock(return_value=[{"r": {}}])
    client.execute_read = AsyncMock(return_value=[])
    return client


@pytest.fixture
def long_term(mock_client):
    return LongTermMemory(mock_client, embedder=None)


class TestAddRelationshipWithProvenance:
    """Tests for add_relationship with V2 provenance parameters."""

    @pytest.mark.asyncio
    async def test_add_relationship_passes_provenance(self, long_term, mock_client):
        source_id = uuid4()
        target_id = uuid4()
        msg_id = str(uuid4())

        rel = await long_term.add_relationship(
            source_id,
            target_id,
            "WORKS_AT",
            confidence=0.9,
            min_confidence=0.7,
            source_message_id=msg_id,
            extractor_name="GLiRELExtractor",
        )

        assert rel.type == "WORKS_AT"
        assert rel.confidence == 0.9
        params = mock_client.execute_write.call_args[0][1]
        assert params["min_confidence"] == 0.7
        assert params["source_message_id"] == msg_id
        assert params["extractor_name"] == "GLiRELExtractor"

    @pytest.mark.asyncio
    async def test_add_relationship_default_provenance_is_none(self, long_term, mock_client):
        rel = await long_term.add_relationship(
            uuid4(), uuid4(), "KNOWS", confidence=1.0
        )

        params = mock_client.execute_write.call_args[0][1]
        assert params["min_confidence"] == 0.0
        assert params["source_message_id"] is None
        assert params["extractor_name"] is None


class TestListPendingRelations:
    """Tests for list_pending_relations."""

    @pytest.mark.asyncio
    async def test_list_pending_relations(self, long_term, mock_client):
        mock_client.execute_read = AsyncMock(return_value=[
            {
                "source_id": "s1",
                "source_name": "John",
                "target_id": "t1",
                "target_name": "Acme",
                "relation_type": "WORKS_AT",
                "confidence": 0.4,
                "source_message_id": "msg-1",
                "extractor_name": "GLiREL",
                "extracted_at": None,
                "created_at": None,
                "type": "WORKS_AT",
            }
        ])

        results = await long_term.list_pending_relations(limit=10)

        assert len(results) == 1
        assert results[0]["source_name"] == "John"
        assert results[0]["target_name"] == "Acme"
        assert results[0]["confidence"] == 0.4
        assert results[0]["extractor_name"] == "GLiREL"
        params = mock_client.execute_read.call_args[0][1]
        assert params["limit"] == 10

    @pytest.mark.asyncio
    async def test_list_pending_empty(self, long_term, mock_client):
        mock_client.execute_read = AsyncMock(return_value=[])
        results = await long_term.list_pending_relations()
        assert results == []


class TestReviewRelation:
    """Tests for review_relation (accept/reject)."""

    @pytest.mark.asyncio
    async def test_accept_relation(self, long_term, mock_client):
        mock_client.execute_write = AsyncMock(return_value=[{
            "r": {}, "source_id": "s1", "target_id": "t1"
        }])

        result = await long_term.review_relation(
            "s1", "t1", "WORKS_AT", accept=True, reviewed_by="agent"
        )

        assert result is not None
        assert result["status"] == "active"
        assert result["reviewed_by"] == "agent"
        query = mock_client.execute_write.call_args[0][0]
        assert "active" in query

    @pytest.mark.asyncio
    async def test_reject_relation(self, long_term, mock_client):
        mock_client.execute_write = AsyncMock(return_value=[{
            "r": {}, "source_id": "s1", "target_id": "t1"
        }])

        result = await long_term.review_relation(
            "s1", "t1", "WORKS_AT", accept=False
        )

        assert result is not None
        assert result["status"] == "rejected"
        query = mock_client.execute_write.call_args[0][0]
        assert "rejected" in query

    @pytest.mark.asyncio
    async def test_review_not_found(self, long_term, mock_client):
        mock_client.execute_write = AsyncMock(return_value=[])
        result = await long_term.review_relation("s1", "t1", "WORKS_AT")
        assert result is None


class TestGetRelationProvenance:
    """Tests for get_relation_provenance."""

    @pytest.mark.asyncio
    async def test_get_relation_provenance(self, long_term, mock_client):
        mock_client.execute_read = AsyncMock(return_value=[{
            "source_id": "s1",
            "source_name": "John",
            "target_id": "t1",
            "target_name": "Acme",
            "relation_type": "WORKS_AT",
            "confidence": 0.95,
            "status": "active",
            "source_message_id": "msg-123",
            "extractor_name": "GLiRELExtractor",
            "extracted_at": None,
            "reviewed_at": None,
            "reviewed_by": "agent",
            "created_at": None,
        }])

        result = await long_term.get_relation_provenance("s1", "t1", "WORKS_AT")

        assert result is not None
        assert result["source_name"] == "John"
        assert result["extractor_name"] == "GLiRELExtractor"
        assert result["source_message_id"] == "msg-123"
        assert result["status"] == "active"
        assert result["reviewed_by"] == "agent"

    @pytest.mark.asyncio
    async def test_get_relation_provenance_not_found(self, long_term, mock_client):
        mock_client.execute_read = AsyncMock(return_value=[])
        result = await long_term.get_relation_provenance("s1", "t1", "UNKNOWN")
        assert result is None


class TestStoreRelationsWithProvenance:
    """Tests for _store_relations passing provenance to Cypher."""

    @pytest.mark.asyncio
    async def test_store_relations_passes_provenance(self, mock_client):
        from neo4j_agent_memory.memory.short_term import ShortTermMemory
        from types import SimpleNamespace

        st = ShortTermMemory(mock_client, embedder=None)

        relation = SimpleNamespace(
            source="John",
            target="Acme",
            relation_type="WORKS_AT",
            confidence=0.4,
        )
        entity_map = {"john": "id-1", "acme": "id-2"}

        count = await st._store_relations(
            [relation],
            entity_map,
            source_message_id="msg-1",
            extractor_name="GLiREL",
            min_confidence=0.7,
        )

        assert count == 1
        params = mock_client.execute_write.call_args[0][1]
        assert params["source_message_id"] == "msg-1"
        assert params["extractor_name"] == "GLiREL"
        assert params["min_confidence"] == 0.7
        assert params["confidence"] == 0.4

    @pytest.mark.asyncio
    async def test_store_relations_name_fallback_passes_provenance(self, mock_client):
        from neo4j_agent_memory.memory.short_term import ShortTermMemory
        from types import SimpleNamespace

        mock_client.execute_write = AsyncMock(return_value=[{"r": {}}])
        st = ShortTermMemory(mock_client, embedder=None)

        relation = SimpleNamespace(
            source="Jane",
            target="Google",
            relation_type="EMPLOYED_BY",
            confidence=0.8,
        )
        # Empty map forces name-based lookup
        entity_map = {}

        count = await st._store_relations(
            [relation],
            entity_map,
            source_message_id="msg-2",
            extractor_name="LLMExtractor",
        )

        assert count == 1
        params = mock_client.execute_write.call_args[0][1]
        assert params["source_message_id"] == "msg-2"
        assert params["extractor_name"] == "LLMExtractor"
