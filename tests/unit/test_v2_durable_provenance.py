"""Unit tests for V2 durable provenance features (SUPPORTED_BY, DERIVED_FROM, ABOUT)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

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


class TestLinkFactToEvidence:
    """Tests for link_fact_to_evidence (SUPPORTED_BY)."""

    @pytest.mark.asyncio
    async def test_link_fact_to_message(self, long_term, mock_client):
        fact_id = uuid4()
        message_id = uuid4()

        result = await long_term.link_fact_to_evidence(
            fact_id, message_id, evidence_type="message", confidence=0.95
        )

        assert result is True
        mock_client.execute_write.assert_called_once()
        call_args = mock_client.execute_write.call_args
        assert "SUPPORTED_BY" in call_args[0][0]
        params = call_args[0][1]
        assert params["fact_id"] == str(fact_id)
        assert params["evidence_id"] == str(message_id)
        assert params["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_link_fact_to_reasoning_trace(self, long_term, mock_client):
        fact_id = uuid4()
        trace_id = uuid4()

        result = await long_term.link_fact_to_evidence(
            fact_id, trace_id, evidence_type="reasoning_trace", confidence=0.9
        )

        assert result is True
        call_args = mock_client.execute_write.call_args
        assert "ReasoningTrace" in call_args[0][0]
        assert call_args[0][1]["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_link_fact_to_tool_call(self, long_term, mock_client):
        fact_id = uuid4()
        tool_call_id = uuid4()

        result = await long_term.link_fact_to_evidence(
            fact_id, tool_call_id, evidence_type="tool_call", confidence=0.8
        )

        assert result is True
        call_args = mock_client.execute_write.call_args
        assert "ToolCall" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_link_fact_invalid_evidence_type(self, long_term):
        with pytest.raises(ValueError, match="Unsupported evidence_type"):
            await long_term.link_fact_to_evidence(
                uuid4(), uuid4(), evidence_type="invalid"
            )

    @pytest.mark.asyncio
    async def test_link_fact_no_results_returns_false(self, long_term, mock_client):
        mock_client.execute_write = AsyncMock(return_value=[])

        result = await long_term.link_fact_to_evidence(
            uuid4(), uuid4(), evidence_type="message"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_link_fact_accepts_string_ids(self, long_term, mock_client):
        fact_id = str(uuid4())
        message_id = str(uuid4())

        result = await long_term.link_fact_to_evidence(
            fact_id, message_id, evidence_type="message"
        )

        assert result is True
        params = mock_client.execute_write.call_args[0][1]
        assert params["fact_id"] == fact_id
        assert params["evidence_id"] == message_id

    @pytest.mark.asyncio
    async def test_link_fact_default_confidence(self, long_term, mock_client):
        await long_term.link_fact_to_evidence(uuid4(), uuid4(), evidence_type="message")

        params = mock_client.execute_write.call_args[0][1]
        assert params["confidence"] == 1.0


class TestLinkPreferenceToEvidence:
    """Tests for link_preference_to_evidence (DERIVED_FROM)."""

    @pytest.mark.asyncio
    async def test_link_preference_to_message(self, long_term, mock_client):
        pref_id = uuid4()
        message_id = uuid4()

        result = await long_term.link_preference_to_evidence(
            pref_id, message_id, evidence_type="message", confidence=0.9
        )

        assert result is True
        call_args = mock_client.execute_write.call_args
        assert "DERIVED_FROM" in call_args[0][0]
        params = call_args[0][1]
        assert params["preference_id"] == str(pref_id)
        assert params["evidence_id"] == str(message_id)

    @pytest.mark.asyncio
    async def test_link_preference_to_trace(self, long_term, mock_client):
        pref_id = uuid4()
        trace_id = uuid4()

        result = await long_term.link_preference_to_evidence(
            pref_id, trace_id, evidence_type="reasoning_trace"
        )

        assert result is True
        call_args = mock_client.execute_write.call_args
        assert "ReasoningTrace" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_link_preference_invalid_evidence_type(self, long_term):
        with pytest.raises(ValueError, match="Unsupported evidence_type"):
            await long_term.link_preference_to_evidence(
                uuid4(), uuid4(), evidence_type="tool_call"
            )

    @pytest.mark.asyncio
    async def test_link_preference_no_results_returns_false(self, long_term, mock_client):
        mock_client.execute_write = AsyncMock(return_value=[])

        result = await long_term.link_preference_to_evidence(
            uuid4(), uuid4(), evidence_type="message"
        )

        assert result is False


class TestLinkFactToEntity:
    """Tests for link_fact_to_entity and auto_link_fact_to_entities (ABOUT)."""

    @pytest.mark.asyncio
    async def test_link_fact_to_entity_manual(self, long_term, mock_client):
        fact_id = uuid4()
        entity_id = uuid4()

        result = await long_term.link_fact_to_entity(fact_id, entity_id)

        assert result is True
        call_args = mock_client.execute_write.call_args
        assert "ABOUT" in call_args[0][0]
        params = call_args[0][1]
        assert params["fact_id"] == str(fact_id)
        assert params["entity_id"] == str(entity_id)
        assert params["link_type"] == "manual"

    @pytest.mark.asyncio
    async def test_link_fact_to_entity_custom_link_type(self, long_term, mock_client):
        await long_term.link_fact_to_entity(
            uuid4(), uuid4(), link_type="subject_match"
        )

        params = mock_client.execute_write.call_args[0][1]
        assert params["link_type"] == "subject_match"

    @pytest.mark.asyncio
    async def test_auto_link_fact_to_entities(self, long_term, mock_client):
        fact_id = uuid4()
        entity_id_1 = str(uuid4())
        entity_id_2 = str(uuid4())

        mock_client.execute_read = AsyncMock(
            return_value=[
                {"entity_id": entity_id_1, "entity_name": "Neo4j", "match_role": "subject"},
                {"entity_id": entity_id_2, "entity_name": "Cypher", "match_role": "object"},
            ]
        )

        linked = await long_term.auto_link_fact_to_entities(fact_id)

        assert len(linked) == 2
        assert linked[0]["entity_name"] == "Neo4j"
        assert linked[0]["match_role"] == "subject"
        assert linked[1]["entity_name"] == "Cypher"
        assert linked[1]["match_role"] == "object"
        # Two link_fact_to_entity calls (writes)
        assert mock_client.execute_write.call_count == 2

    @pytest.mark.asyncio
    async def test_auto_link_no_matches(self, long_term, mock_client):
        mock_client.execute_read = AsyncMock(return_value=[])

        linked = await long_term.auto_link_fact_to_entities(uuid4())

        assert linked == []
        mock_client.execute_write.assert_not_called()


class TestGetFactProvenance:
    """Tests for get_fact_provenance."""

    @pytest.mark.asyncio
    async def test_get_fact_provenance_with_evidence(self, long_term, mock_client):
        fact_id = uuid4()
        mock_client.execute_read = AsyncMock(
            return_value=[
                {
                    "f": {
                        "id": str(fact_id),
                        "subject": "Neo4j",
                        "predicate": "uses",
                        "object": "Cypher",
                        "confidence": 1.0,
                        "created_at": None,
                    },
                    "messages": [
                        {"id": str(uuid4()), "content": "Neo4j uses Cypher", "role": "user", "confidence": 0.95, "linked_at": None}
                    ],
                    "traces": [
                        {"id": str(uuid4()), "task": "Research Neo4j", "outcome": "Done", "confidence": 0.9, "linked_at": None}
                    ],
                    "tool_calls": [],
                    "entities": [
                        {"id": str(uuid4()), "name": "Neo4j", "type": "OBJECT"}
                    ],
                }
            ]
        )

        provenance = await long_term.get_fact_provenance(fact_id)

        assert provenance["fact"] is not None
        assert provenance["fact"].subject == "Neo4j"
        assert len(provenance["messages"]) == 1
        assert len(provenance["traces"]) == 1
        assert len(provenance["tool_calls"]) == 0
        assert len(provenance["entities"]) == 1

    @pytest.mark.asyncio
    async def test_get_fact_provenance_not_found(self, long_term, mock_client):
        mock_client.execute_read = AsyncMock(return_value=[])

        provenance = await long_term.get_fact_provenance(uuid4())

        assert provenance["fact"] is None
        assert provenance["messages"] == []
        assert provenance["traces"] == []
        assert provenance["tool_calls"] == []
        assert provenance["entities"] == []


class TestGetPreferenceProvenance:
    """Tests for get_preference_provenance."""

    @pytest.mark.asyncio
    async def test_get_preference_provenance_with_evidence(self, long_term, mock_client):
        pref_id = uuid4()
        mock_client.execute_read = AsyncMock(
            return_value=[
                {
                    "p": {
                        "id": str(pref_id),
                        "category": "coding",
                        "preference": "Prefer Python",
                        "confidence": 1.0,
                        "created_at": None,
                    },
                    "messages": [
                        {"id": str(uuid4()), "content": "I prefer Python", "role": "user", "confidence": 1.0, "linked_at": None}
                    ],
                    "traces": [],
                    "entities": [],
                }
            ]
        )

        provenance = await long_term.get_preference_provenance(pref_id)

        assert provenance["preference"] is not None
        assert provenance["preference"].category == "coding"
        assert len(provenance["messages"]) == 1
        assert len(provenance["traces"]) == 0

    @pytest.mark.asyncio
    async def test_get_preference_provenance_not_found(self, long_term, mock_client):
        mock_client.execute_read = AsyncMock(return_value=[])

        provenance = await long_term.get_preference_provenance(uuid4())

        assert provenance["preference"] is None
        assert provenance["messages"] == []


class TestGetEntityFacts:
    """Tests for get_entity_facts."""

    @pytest.mark.asyncio
    async def test_get_entity_facts(self, long_term, mock_client):
        entity_id = uuid4()
        fact_id = uuid4()
        mock_client.execute_read = AsyncMock(
            return_value=[
                {
                    "f": {
                        "id": str(fact_id),
                        "subject": "Neo4j",
                        "predicate": "is",
                        "object": "a graph database",
                        "confidence": 1.0,
                        "created_at": None,
                    },
                    "link_type": "subject_match",
                    "linked_at": None,
                }
            ]
        )

        facts = await long_term.get_entity_facts(entity_id)

        assert len(facts) == 1
        assert facts[0]["fact"].subject == "Neo4j"
        assert facts[0]["link_type"] == "subject_match"

    @pytest.mark.asyncio
    async def test_get_entity_facts_empty(self, long_term, mock_client):
        mock_client.execute_read = AsyncMock(return_value=[])

        facts = await long_term.get_entity_facts(uuid4())

        assert facts == []

    @pytest.mark.asyncio
    async def test_get_entity_facts_respects_limit(self, long_term, mock_client):
        mock_client.execute_read = AsyncMock(return_value=[])

        await long_term.get_entity_facts(uuid4(), limit=5)

        params = mock_client.execute_read.call_args[0][1]
        assert params["limit"] == 5
