"""Unit tests for V2 reasoning-to-durable linking (PRODUCED, ABOUT, OBSERVED)."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from neo4j_agent_memory.memory.reasoning import ReasoningMemory


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.execute_write = AsyncMock(return_value=[{"r": {}}])
    client.execute_read = AsyncMock(return_value=[])
    return client


@pytest.fixture
def reasoning(mock_client):
    return ReasoningMemory(mock_client, embedder=None)


class TestLinkTraceToOutcome:
    """Tests for link_trace_to_outcome (PRODUCED)."""

    @pytest.mark.asyncio
    async def test_link_trace_to_fact(self, reasoning, mock_client):
        trace_id = uuid4()
        fact_id = uuid4()

        result = await reasoning.link_trace_to_outcome(
            trace_id, fact_id, target_type="fact"
        )

        assert result is True
        call_args = mock_client.execute_write.call_args
        assert "PRODUCED" in call_args[0][0]
        assert "Fact" in call_args[0][0]
        params = call_args[0][1]
        assert params["trace_id"] == str(trace_id)
        assert params["target_id"] == str(fact_id)

    @pytest.mark.asyncio
    async def test_link_trace_to_preference(self, reasoning, mock_client):
        trace_id = uuid4()
        pref_id = uuid4()

        result = await reasoning.link_trace_to_outcome(
            trace_id, pref_id, target_type="preference"
        )

        assert result is True
        call_args = mock_client.execute_write.call_args
        assert "Preference" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_link_trace_to_entity(self, reasoning, mock_client):
        trace_id = uuid4()
        entity_id = uuid4()

        result = await reasoning.link_trace_to_outcome(
            trace_id, entity_id, target_type="entity"
        )

        assert result is True
        call_args = mock_client.execute_write.call_args
        assert "Entity" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_link_trace_with_step_number(self, reasoning, mock_client):
        result = await reasoning.link_trace_to_outcome(
            uuid4(), uuid4(), target_type="fact", step_number=3
        )

        assert result is True
        params = mock_client.execute_write.call_args[0][1]
        assert params["step_number"] == 3

    @pytest.mark.asyncio
    async def test_link_trace_invalid_target_type(self, reasoning):
        with pytest.raises(ValueError, match="Unsupported target_type"):
            await reasoning.link_trace_to_outcome(
                uuid4(), uuid4(), target_type="invalid"
            )

    @pytest.mark.asyncio
    async def test_link_trace_no_results_returns_false(self, reasoning, mock_client):
        mock_client.execute_write = AsyncMock(return_value=[])

        result = await reasoning.link_trace_to_outcome(
            uuid4(), uuid4(), target_type="fact"
        )

        assert result is False


class TestLinkStepToEntity:
    """Tests for link_step_to_entity (ABOUT)."""

    @pytest.mark.asyncio
    async def test_link_step_to_entity(self, reasoning, mock_client):
        step_id = uuid4()
        entity_id = uuid4()

        result = await reasoning.link_step_to_entity(step_id, entity_id)

        assert result is True
        call_args = mock_client.execute_write.call_args
        assert "ABOUT" in call_args[0][0]
        assert "ReasoningStep" in call_args[0][0]
        params = call_args[0][1]
        assert params["step_id"] == str(step_id)
        assert params["entity_id"] == str(entity_id)

    @pytest.mark.asyncio
    async def test_link_step_no_results(self, reasoning, mock_client):
        mock_client.execute_write = AsyncMock(return_value=[])

        result = await reasoning.link_step_to_entity(uuid4(), uuid4())

        assert result is False


class TestLinkToolCallToFact:
    """Tests for link_tool_call_to_fact (OBSERVED)."""

    @pytest.mark.asyncio
    async def test_link_tool_call_to_fact(self, reasoning, mock_client):
        tc_id = uuid4()
        fact_id = uuid4()

        result = await reasoning.link_tool_call_to_fact(tc_id, fact_id)

        assert result is True
        call_args = mock_client.execute_write.call_args
        assert "OBSERVED" in call_args[0][0]
        params = call_args[0][1]
        assert params["tool_call_id"] == str(tc_id)
        assert params["fact_id"] == str(fact_id)

    @pytest.mark.asyncio
    async def test_link_tool_call_no_results(self, reasoning, mock_client):
        mock_client.execute_write = AsyncMock(return_value=[])

        result = await reasoning.link_tool_call_to_fact(uuid4(), uuid4())

        assert result is False


class TestGetTraceOutcomes:
    """Tests for get_trace_outcomes."""

    @pytest.mark.asyncio
    async def test_get_trace_outcomes(self, reasoning, mock_client):
        trace_id = uuid4()
        mock_client.execute_read = AsyncMock(
            return_value=[
                {
                    "labels": ["Fact"],
                    "id": str(uuid4()),
                    "name": None,
                    "summary": "Neo4j",
                    "linked_at": None,
                    "step_number": 2,
                },
                {
                    "labels": ["Entity"],
                    "id": str(uuid4()),
                    "name": "Neo4j",
                    "summary": "Neo4j",
                    "linked_at": None,
                    "step_number": None,
                },
            ]
        )

        outcomes = await reasoning.get_trace_outcomes(trace_id)

        assert len(outcomes) == 2
        assert outcomes[0]["labels"] == ["Fact"]
        assert outcomes[0]["step_number"] == 2
        assert outcomes[1]["labels"] == ["Entity"]
        assert outcomes[1]["name"] == "Neo4j"

    @pytest.mark.asyncio
    async def test_get_trace_outcomes_empty(self, reasoning, mock_client):
        mock_client.execute_read = AsyncMock(return_value=[])

        outcomes = await reasoning.get_trace_outcomes(uuid4())

        assert outcomes == []


class TestGetMemoryReasoning:
    """Tests for get_memory_reasoning."""

    @pytest.mark.asyncio
    async def test_get_memory_reasoning(self, reasoning, mock_client):
        fact_id = uuid4()
        mock_client.execute_read = AsyncMock(
            return_value=[
                {
                    "trace_id": str(uuid4()),
                    "task": "Research Neo4j",
                    "outcome": "Found that Neo4j uses Cypher",
                    "success": True,
                    "started_at": None,
                    "linked_at": None,
                    "step_number": 1,
                }
            ]
        )

        traces = await reasoning.get_memory_reasoning(fact_id)

        assert len(traces) == 1
        assert traces[0]["task"] == "Research Neo4j"
        assert traces[0]["success"] is True
        assert traces[0]["step_number"] == 1

    @pytest.mark.asyncio
    async def test_get_memory_reasoning_empty(self, reasoning, mock_client):
        mock_client.execute_read = AsyncMock(return_value=[])

        traces = await reasoning.get_memory_reasoning(uuid4())

        assert traces == []
