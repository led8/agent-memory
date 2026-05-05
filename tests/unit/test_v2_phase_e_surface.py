"""Unit tests for V2 Phase E: CLI surface, schema indexes, provenance in recall."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from neo4j_agent_memory.cli.memory_ops import MemoryCliService, to_jsonable


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.long_term = AsyncMock()
    client.short_term = AsyncMock()
    client.reasoning = AsyncMock()
    client.graph = AsyncMock()
    return client


@pytest.fixture
def service(mock_client):
    svc = MemoryCliService.__new__(MemoryCliService)
    svc._client = mock_client
    return svc


class TestListPendingRelationsService:
    @pytest.mark.asyncio
    async def test_returns_relations(self, service):
        service.client.long_term.list_pending_relations = AsyncMock(return_value=[
            {"source_name": "A", "target_name": "B", "relation_type": "WORKS_AT", "confidence": 0.5}
        ])
        result = await service.list_pending_relations(limit=10)
        assert result["count"] == 1
        assert result["relations"][0]["source_name"] == "A"


class TestReviewRelationService:
    @pytest.mark.asyncio
    async def test_accept(self, service):
        service.client.long_term.review_relation = AsyncMock(return_value={
            "status": "active", "source_id": "s1", "target_id": "t1"
        })
        result = await service.review_relation("s1", "t1", "KNOWS", accept=True)
        assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_not_found(self, service):
        service.client.long_term.review_relation = AsyncMock(return_value=None)
        result = await service.review_relation("s1", "t1", "KNOWS")
        assert "error" in result


class TestGetRelationProvenanceService:
    @pytest.mark.asyncio
    async def test_returns_provenance(self, service):
        service.client.long_term.get_relation_provenance = AsyncMock(return_value={
            "source_name": "A", "extractor_name": "GLiREL", "status": "active"
        })
        result = await service.get_relation_provenance("s1", "t1", "WORKS_AT")
        assert result["extractor_name"] == "GLiREL"

    @pytest.mark.asyncio
    async def test_not_found(self, service):
        service.client.long_term.get_relation_provenance = AsyncMock(return_value=None)
        result = await service.get_relation_provenance("s1", "t1", "X")
        assert "error" in result


class TestGetProvenanceService:
    @pytest.mark.asyncio
    async def test_fact_provenance(self, service):
        service.client.long_term.get_fact_provenance = AsyncMock(return_value={
            "fact": {"id": "f1"}, "traces": [], "messages": []
        })
        result = await service.get_provenance("fact", "f1")
        assert "fact" in result

    @pytest.mark.asyncio
    async def test_preference_provenance(self, service):
        service.client.long_term.get_preference_provenance = AsyncMock(return_value={
            "preference": {"id": "p1"}, "traces": [], "messages": []
        })
        result = await service.get_provenance("preference", "p1")
        assert "preference" in result

    @pytest.mark.asyncio
    async def test_unsupported_kind(self, service):
        result = await service.get_provenance("entity", "e1")
        assert result["error"] == "unsupported kind: entity"


class TestSchemaIndexesIncludeCandidate:
    """Verify LongTermCandidate indexes are defined in schema."""

    def test_candidate_indexes_in_schema(self):
        from neo4j_agent_memory.graph.schema import SchemaManager

        import inspect
        source = inspect.getsource(SchemaManager.setup_indexes)
        assert "LongTermCandidate" in source
        assert "candidate_id_idx" in source
        assert "candidate_status_idx" in source
        assert "candidate_type_idx" in source


class TestRecallWithProvenance:
    """Test get_startup_recall with include_provenance=True."""

    @pytest.mark.asyncio
    async def test_recall_includes_provenance_annotation(self):
        from neo4j_agent_memory.integrations.coding_agent import CodingAgentMemory
        from neo4j_agent_memory.memory.long_term import Preference, Fact

        client = AsyncMock()
        conv_mock = MagicMock()
        conv_mock.messages = []
        client.short_term.get_conversation = AsyncMock(return_value=conv_mock)

        pref = Preference(
            id=uuid4(), category="coding", preference="Use ruff",
            confidence=1.0, metadata={"repo": "agent-memory"}
        )
        client.long_term.search_preferences = AsyncMock(return_value=[pref])
        client.long_term.get_preference_provenance = AsyncMock(return_value={
            "traces": [{"task": "setup linting"}],
            "messages": [],
        })

        fact = Fact(
            id=uuid4(), subject="ruff", predicate="replaces", object="flake8",
            confidence=1.0, metadata={"repo": "agent-memory"}
        )
        client.long_term.search_facts = AsyncMock(return_value=[fact])
        client.long_term.get_fact_provenance = AsyncMock(return_value={
            "traces": [],
            "messages": [{"role": "user"}],
        })

        client.long_term.search_entities = AsyncMock(return_value=[])
        client.long_term.list_entities = AsyncMock(return_value=[])
        client.reasoning.get_context = AsyncMock(return_value="")
        client.reasoning.get_session_traces = AsyncMock(return_value=[])

        coding_mem = CodingAgentMemory(
            memory_client=client,
            repo="agent-memory",
            task="test-task",
            session_id="test-session",
        )

        result = await coding_mem.get_startup_recall(include_provenance=True)

        assert "trace:setup linting" in result
        assert "msg:user" in result

    @pytest.mark.asyncio
    async def test_recall_without_provenance_has_no_annotation(self):
        from neo4j_agent_memory.integrations.coding_agent import CodingAgentMemory
        from neo4j_agent_memory.memory.long_term import Fact

        client = AsyncMock()
        conv_mock = MagicMock()
        conv_mock.messages = []
        client.short_term.get_conversation = AsyncMock(return_value=conv_mock)
        client.long_term.search_preferences = AsyncMock(return_value=[])
        client.long_term.list_preferences = AsyncMock(return_value=[])

        fact = Fact(
            id=uuid4(), subject="ruff", predicate="replaces", object="flake8",
            confidence=1.0, metadata={"repo": "agent-memory"}
        )
        client.long_term.search_facts = AsyncMock(return_value=[fact])
        client.long_term.search_entities = AsyncMock(return_value=[])
        client.long_term.list_entities = AsyncMock(return_value=[])
        client.reasoning.get_context = AsyncMock(return_value="")
        client.reasoning.get_session_traces = AsyncMock(return_value=[])

        coding_mem = CodingAgentMemory(
            memory_client=client, repo="agent-memory", task="test-task", session_id="test-session"
        )

        result = await coding_mem.get_startup_recall(include_provenance=False)

        assert "trace:" not in result
        assert "msg:" not in result
