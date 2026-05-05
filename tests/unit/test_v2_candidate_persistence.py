"""Unit tests for V2 candidate persistence (LongTermCandidate graph nodes)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from neo4j_agent_memory.integrations.coding_agent import (
    CodingAgentMemory,
    LongTermCandidateConfidence,
    LongTermCandidateSource,
    LongTermCandidateScopeKind,
    LongTermCandidateType,
    LongTermMemoryCandidate,
)
from neo4j_agent_memory.memory.long_term import LongTermMemory


# =============================================================================
# LongTermMemory.store_candidate / list / accept / ignore
# =============================================================================


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.execute_write = AsyncMock(return_value=[{"c": {
        "id": "cand-001",
        "type": "fact",
        "scope_kind": "repo",
        "content": "Neo4j uses Cypher",
        "why_candidate": "Durable repo truth",
        "source": "code_verified",
        "confidence": "high",
        "evidence": "Confirmed in codebase",
        "suggested_action": "remember_fact",
        "payload": '{"subject": "Neo4j", "predicate": "uses", "obj": "Cypher"}',
        "status": "proposed",
        "created_at": None,
        "reviewed_at": None,
        "reviewed_by": None,
    }}])
    client.execute_read = AsyncMock(return_value=[])
    return client


@pytest.fixture
def long_term(mock_client):
    return LongTermMemory(mock_client, embedder=None)


class TestStoreCandidate:
    @pytest.mark.asyncio
    async def test_store_candidate_creates_node(self, long_term, mock_client):
        result = await long_term.store_candidate(
            candidate_type="fact",
            scope_kind="repo",
            content="Neo4j uses Cypher",
            why_candidate="Durable repo truth",
            source="code_verified",
            confidence="high",
            evidence="Confirmed in codebase",
            suggested_action="remember_fact",
            payload={"subject": "Neo4j", "predicate": "uses", "obj": "Cypher"},
        )

        assert result["status"] == "proposed"
        # Verify CREATE_CANDIDATE query was called
        call_args = mock_client.execute_write.call_args_list[0]
        assert "LongTermCandidate" in call_args[0][0]
        params = call_args[0][1]
        assert params["type"] == "fact"
        assert params["confidence"] == "high"
        assert json.loads(params["payload"])["subject"] == "Neo4j"

    @pytest.mark.asyncio
    async def test_store_candidate_with_trace_provenance(self, long_term, mock_client):
        trace_id = str(uuid4())
        await long_term.store_candidate(
            candidate_type="fact",
            scope_kind="repo",
            content="test",
            why_candidate="test",
            source="code_verified",
            confidence="high",
            evidence="test",
            suggested_action="remember_fact",
            payload={},
            proposed_by_trace_id=trace_id,
        )

        # Should have two writes: CREATE + PROPOSED_BY
        assert mock_client.execute_write.await_count == 2
        second_call = mock_client.execute_write.call_args_list[1]
        assert "PROPOSED_BY" in second_call[0][0]
        assert "ReasoningTrace" in second_call[0][0]

    @pytest.mark.asyncio
    async def test_store_candidate_with_message_provenance(self, long_term, mock_client):
        msg_id = str(uuid4())
        await long_term.store_candidate(
            candidate_type="preference",
            scope_kind="personal",
            content="test",
            why_candidate="test",
            source="user_explicit",
            confidence="high",
            evidence="test",
            suggested_action="remember_preference",
            payload={},
            proposed_by_message_id=msg_id,
        )

        assert mock_client.execute_write.await_count == 2
        second_call = mock_client.execute_write.call_args_list[1]
        assert "PROPOSED_BY" in second_call[0][0]
        assert "Message" in second_call[0][0]


class TestListCandidates:
    @pytest.mark.asyncio
    async def test_list_candidates_with_filters(self, long_term, mock_client):
        mock_client.execute_read = AsyncMock(return_value=[
            {"c": {"id": "c1", "type": "fact", "status": "proposed",
                   "scope_kind": "repo", "content": "test", "why_candidate": "why",
                   "source": "code_verified", "confidence": "high",
                   "evidence": "ev", "suggested_action": "remember_fact",
                   "payload": "{}", "created_at": None, "reviewed_at": None,
                   "reviewed_by": None}},
        ])

        candidates = await long_term.list_candidates(
            status="proposed", candidate_type="fact", limit=10
        )

        assert len(candidates) == 1
        assert candidates[0]["status"] == "proposed"
        params = mock_client.execute_read.call_args[0][1]
        assert params["status"] == "proposed"
        assert params["type"] == "fact"

    @pytest.mark.asyncio
    async def test_list_candidates_empty(self, long_term, mock_client):
        mock_client.execute_read = AsyncMock(return_value=[])
        candidates = await long_term.list_candidates()
        assert candidates == []


class TestAcceptIgnoreExpire:
    @pytest.mark.asyncio
    async def test_accept_candidate(self, long_term, mock_client):
        mock_client.execute_write = AsyncMock(return_value=[{"c": {
            "id": "c1", "status": "accepted", "type": "fact",
            "scope_kind": "repo", "content": "test", "why_candidate": "why",
            "source": "code_verified", "confidence": "high",
            "evidence": "ev", "suggested_action": "remember_fact",
            "payload": "{}", "created_at": None, "reviewed_at": None,
            "reviewed_by": "agent",
        }}])

        result = await long_term.accept_candidate("c1", reviewed_by="agent")
        assert result["status"] == "accepted"
        params = mock_client.execute_write.call_args[0][1]
        assert params["status"] == "accepted"
        assert params["reviewed_by"] == "agent"

    @pytest.mark.asyncio
    async def test_ignore_candidate(self, long_term, mock_client):
        mock_client.execute_write = AsyncMock(return_value=[{"c": {
            "id": "c1", "status": "ignored", "type": "fact",
            "scope_kind": "repo", "content": "test", "why_candidate": "why",
            "source": "code_verified", "confidence": "high",
            "evidence": "ev", "suggested_action": "remember_fact",
            "payload": "{}", "created_at": None, "reviewed_at": None,
            "reviewed_by": None,
        }}])

        result = await long_term.ignore_candidate("c1")
        assert result["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_expire_candidate(self, long_term, mock_client):
        mock_client.execute_write = AsyncMock(return_value=[{"c": {
            "id": "c1", "status": "expired", "type": "fact",
            "scope_kind": "repo", "content": "test", "why_candidate": "why",
            "source": "code_verified", "confidence": "high",
            "evidence": "ev", "suggested_action": "remember_fact",
            "payload": "{}", "created_at": None, "reviewed_at": None,
            "reviewed_by": None,
        }}])

        result = await long_term.expire_candidate("c1")
        assert result["status"] == "expired"

    @pytest.mark.asyncio
    async def test_accept_not_found(self, long_term, mock_client):
        mock_client.execute_write = AsyncMock(return_value=[])
        result = await long_term.accept_candidate("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_candidate(self, long_term, mock_client):
        mock_client.execute_write = AsyncMock(return_value=[{"deleted": 1}])
        result = await long_term.delete_candidate("c1")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_candidate_not_found(self, long_term, mock_client):
        mock_client.execute_write = AsyncMock(return_value=[{"deleted": 0}])
        result = await long_term.delete_candidate("nonexistent")
        assert result is False


# =============================================================================
# CodingAgentMemory.propose_*_candidate(persist_candidate=True)
# =============================================================================


@pytest.fixture
def mock_coding_client():
    client = MagicMock()
    client.short_term = MagicMock()
    client.long_term = MagicMock()
    client.reasoning = MagicMock()
    client.long_term.get_preferences_by_category = AsyncMock(return_value=[])
    client.long_term.get_facts_about = AsyncMock(return_value=[])
    client.long_term.store_candidate = AsyncMock(return_value={"id": "stored-001", "status": "proposed"})
    client.long_term.accept_candidate = AsyncMock(return_value={"id": "stored-001", "status": "accepted"})
    client.long_term.add_fact = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    client.long_term.add_preference = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    client.long_term.link_fact_to_evidence = AsyncMock(return_value=True)
    client.long_term.link_preference_to_evidence = AsyncMock(return_value=True)
    client.long_term.auto_link_fact_to_entities = AsyncMock(return_value=[])
    client.reasoning.link_trace_to_outcome = AsyncMock(return_value=True)
    return client


class TestPersistCandidate:
    @pytest.mark.asyncio
    async def test_propose_fact_persist_false_does_not_store(self, mock_coding_client):
        memory = CodingAgentMemory(mock_coding_client, repo="test", task="test")

        candidate = await memory.propose_fact_candidate(
            subject="X", predicate="is", obj="Y",
            source=LongTermCandidateSource.CODE_VERIFIED,
            evidence="test",
            persist_candidate=False,
        )

        assert candidate is not None
        assert candidate.stored_candidate_id is None
        mock_coding_client.long_term.store_candidate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_propose_fact_persist_true_stores(self, mock_coding_client):
        memory = CodingAgentMemory(mock_coding_client, repo="test", task="test")

        candidate = await memory.propose_fact_candidate(
            subject="Neo4j", predicate="uses", obj="Cypher",
            source=LongTermCandidateSource.CODE_VERIFIED,
            evidence="Confirmed in code",
            persist_candidate=True,
        )

        assert candidate is not None
        assert candidate.stored_candidate_id == "stored-001"
        mock_coding_client.long_term.store_candidate.assert_awaited_once()
        call_kwargs = mock_coding_client.long_term.store_candidate.call_args.kwargs
        assert call_kwargs["candidate_type"] == "fact"
        assert call_kwargs["confidence"] == "high"

    @pytest.mark.asyncio
    async def test_propose_preference_persist_true(self, mock_coding_client):
        memory = CodingAgentMemory(mock_coding_client, repo="test", task="test")

        candidate = await memory.propose_preference_candidate(
            category="workflow",
            preference="Use short sessions",
            source=LongTermCandidateSource.USER_EXPLICIT,
            evidence="User said so",
            persist_candidate=True,
        )

        assert candidate is not None
        assert candidate.stored_candidate_id == "stored-001"
        mock_coding_client.long_term.store_candidate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_propose_entity_persist_true(self, mock_coding_client):
        memory = CodingAgentMemory(mock_coding_client, repo="test", task="test")

        candidate = await memory.propose_entity_candidate(
            name="Neo4j",
            entity_type="TECHNOLOGY",
            source=LongTermCandidateSource.CODE_VERIFIED,
            evidence="Used throughout the project",
            persist_candidate=True,
        )

        assert candidate is not None
        assert candidate.stored_candidate_id == "stored-001"

    @pytest.mark.asyncio
    async def test_persist_candidate_with_active_trace(self, mock_coding_client):
        memory = CodingAgentMemory(mock_coding_client, repo="test", task="test")
        memory._active_trace_id = uuid4()

        candidate = await memory.propose_fact_candidate(
            subject="X", predicate="is", obj="Y",
            source=LongTermCandidateSource.CODE_VERIFIED,
            evidence="test",
            persist_candidate=True,
        )

        call_kwargs = mock_coding_client.long_term.store_candidate.call_args.kwargs
        assert call_kwargs["proposed_by_trace_id"] == memory._active_trace_id
        assert call_kwargs["proposed_by_message_id"] is None

    @pytest.mark.asyncio
    async def test_persist_candidate_with_last_user_message(self, mock_coding_client):
        memory = CodingAgentMemory(mock_coding_client, repo="test", task="test")
        memory._last_user_message_id = uuid4()

        candidate = await memory.propose_fact_candidate(
            subject="X", predicate="is", obj="Y",
            source=LongTermCandidateSource.CODE_VERIFIED,
            evidence="test",
            persist_candidate=True,
        )

        call_kwargs = mock_coding_client.long_term.store_candidate.call_args.kwargs
        assert call_kwargs["proposed_by_message_id"] == memory._last_user_message_id

    @pytest.mark.asyncio
    async def test_remember_candidate_updates_stored_status(self, mock_coding_client):
        memory = CodingAgentMemory(mock_coding_client, repo="test", task="test")

        candidate = await memory.propose_fact_candidate(
            subject="Neo4j", predicate="uses", obj="Cypher",
            source=LongTermCandidateSource.CODE_VERIFIED,
            evidence="Confirmed",
            persist_candidate=True,
        )

        assert candidate.stored_candidate_id == "stored-001"
        await memory.remember_candidate(candidate)

        mock_coding_client.long_term.accept_candidate.assert_awaited_once_with("stored-001")

    @pytest.mark.asyncio
    async def test_remember_candidate_without_stored_id_skips_accept(self, mock_coding_client):
        memory = CodingAgentMemory(mock_coding_client, repo="test", task="test")

        candidate = await memory.propose_fact_candidate(
            subject="X", predicate="is", obj="Y",
            source=LongTermCandidateSource.CODE_VERIFIED,
            evidence="test",
            persist_candidate=False,
        )

        await memory.remember_candidate(candidate)
        mock_coding_client.long_term.accept_candidate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_propose_low_confidence_returns_none_no_storage(self, mock_coding_client):
        memory = CodingAgentMemory(mock_coding_client, repo="test", task="test")

        candidate = await memory.propose_fact_candidate(
            subject="Maybe", predicate="could be", obj="wrong",
            source=LongTermCandidateSource.RUN_OBSERVATION,
            evidence="One incomplete run",
            durable=False,
            reusable=False,
            persist_candidate=True,  # Should still not store because candidate is None
        )

        assert candidate is None
        mock_coding_client.long_term.store_candidate.assert_not_awaited()
