"""Unit tests for V2 provenance wiring in CodingAgentMemory."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from neo4j_agent_memory.integrations.coding_agent import CodingAgentMemory


@pytest.fixture
def mock_memory_client() -> MagicMock:
    client = MagicMock()
    client.short_term = MagicMock()
    client.long_term = MagicMock()
    client.reasoning = MagicMock()
    client.long_term.get_preferences_by_category = AsyncMock(return_value=[])
    client.long_term.get_facts_about = AsyncMock(return_value=[])
    client.long_term.add_fact = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    client.long_term.add_preference = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    client.long_term.update_preference_metadata = AsyncMock()
    client.long_term.update_fact_metadata = AsyncMock()
    client.long_term.link_preference_supersession = AsyncMock(return_value=True)
    client.long_term.link_fact_supersession = AsyncMock(return_value=True)
    client.long_term.link_fact_to_evidence = AsyncMock(return_value=True)
    client.long_term.link_preference_to_evidence = AsyncMock(return_value=True)
    client.long_term.auto_link_fact_to_entities = AsyncMock(return_value=[])
    client.reasoning.link_trace_to_outcome = AsyncMock(return_value=True)
    # V2 candidate mocks
    client.long_term.store_candidate = AsyncMock(return_value={"id": "cand-123", "status": "proposed"})
    client.long_term.accept_candidate = AsyncMock(return_value={"id": "cand-123", "status": "accepted"})
    client.short_term.add_message = AsyncMock(
        return_value=SimpleNamespace(id=uuid4())
    )
    client.reasoning.start_trace = AsyncMock(
        return_value=SimpleNamespace(id=uuid4())
    )
    return client


@pytest.mark.asyncio
async def test_remember_fact_links_to_active_trace(mock_memory_client):
    """When a trace is active, remember_fact creates SUPPORTED_BY -> trace."""
    trace_id = uuid4()
    mock_memory_client.reasoning.start_trace = AsyncMock(
        return_value=SimpleNamespace(id=trace_id)
    )

    memory = CodingAgentMemory(mock_memory_client, repo="test", task="test-task")
    await memory.start_trace(task="test-task")

    fact = SimpleNamespace(id=uuid4())
    mock_memory_client.long_term.add_fact = AsyncMock(return_value=fact)

    await memory.remember_fact("Neo4j", "is", "a graph database")

    mock_memory_client.long_term.link_fact_to_evidence.assert_awaited_once_with(
        fact.id, trace_id, evidence_type="reasoning_trace"
    )


@pytest.mark.asyncio
async def test_remember_fact_links_to_last_user_message(mock_memory_client):
    """When no trace but a message exists, remember_fact links to message."""
    message_id = uuid4()
    mock_memory_client.short_term.add_message = AsyncMock(
        return_value=SimpleNamespace(id=message_id)
    )

    memory = CodingAgentMemory(mock_memory_client, repo="test", task="test-task")
    await memory.add_user_message("tell me about Neo4j")

    fact = SimpleNamespace(id=uuid4())
    mock_memory_client.long_term.add_fact = AsyncMock(return_value=fact)

    await memory.remember_fact("Neo4j", "is", "a graph database")

    mock_memory_client.long_term.link_fact_to_evidence.assert_awaited_once_with(
        fact.id, message_id, evidence_type="message"
    )


@pytest.mark.asyncio
async def test_remember_fact_no_provenance_when_no_context(mock_memory_client):
    """When no trace or message exists, no provenance link is created."""
    memory = CodingAgentMemory(mock_memory_client, repo="test", task="test-task")

    fact = SimpleNamespace(id=uuid4())
    mock_memory_client.long_term.add_fact = AsyncMock(return_value=fact)

    await memory.remember_fact("Neo4j", "is", "a graph database")

    mock_memory_client.long_term.link_fact_to_evidence.assert_not_awaited()


@pytest.mark.asyncio
async def test_remember_fact_explicit_evidence_ids(mock_memory_client):
    """Explicit evidence_ids override automatic provenance."""
    memory = CodingAgentMemory(mock_memory_client, repo="test", task="test-task")
    # Set a message to verify it's NOT used when evidence_ids are explicit
    msg_id = uuid4()
    mock_memory_client.short_term.add_message = AsyncMock(
        return_value=SimpleNamespace(id=msg_id)
    )
    await memory.add_user_message("context")

    fact = SimpleNamespace(id=uuid4())
    mock_memory_client.long_term.add_fact = AsyncMock(return_value=fact)

    evidence_1 = str(uuid4())
    evidence_2 = str(uuid4())
    await memory.remember_fact(
        "Neo4j", "is", "a graph database",
        evidence_ids=[evidence_1, evidence_2],
    )

    assert mock_memory_client.long_term.link_fact_to_evidence.await_count == 2
    calls = mock_memory_client.long_term.link_fact_to_evidence.await_args_list
    assert calls[0].args == (fact.id, evidence_1)
    assert calls[1].args == (fact.id, evidence_2)


@pytest.mark.asyncio
async def test_remember_fact_auto_links_entities(mock_memory_client):
    """remember_fact auto-links to entities by default."""
    memory = CodingAgentMemory(mock_memory_client, repo="test", task="test-task")

    fact = SimpleNamespace(id=uuid4())
    mock_memory_client.long_term.add_fact = AsyncMock(return_value=fact)

    await memory.remember_fact("Neo4j", "uses", "Cypher")

    mock_memory_client.long_term.auto_link_fact_to_entities.assert_awaited_once_with(
        fact.id
    )


@pytest.mark.asyncio
async def test_remember_fact_skip_auto_link_entities(mock_memory_client):
    """auto_link_entities=False disables entity linking."""
    memory = CodingAgentMemory(mock_memory_client, repo="test", task="test-task")

    fact = SimpleNamespace(id=uuid4())
    mock_memory_client.long_term.add_fact = AsyncMock(return_value=fact)

    await memory.remember_fact("Neo4j", "uses", "Cypher", auto_link_entities=False)

    mock_memory_client.long_term.auto_link_fact_to_entities.assert_not_awaited()


@pytest.mark.asyncio
async def test_remember_preference_links_to_active_trace(mock_memory_client):
    """When a trace is active, remember_preference creates DERIVED_FROM -> trace."""
    trace_id = uuid4()
    mock_memory_client.reasoning.start_trace = AsyncMock(
        return_value=SimpleNamespace(id=trace_id)
    )

    memory = CodingAgentMemory(mock_memory_client, repo="test", task="test-task")
    await memory.start_trace(task="test-task")

    pref = SimpleNamespace(id=uuid4())
    mock_memory_client.long_term.add_preference = AsyncMock(return_value=pref)

    await memory.remember_preference("coding", "Prefer Python")

    mock_memory_client.long_term.link_preference_to_evidence.assert_awaited_once_with(
        pref.id, trace_id, evidence_type="reasoning_trace"
    )


@pytest.mark.asyncio
async def test_remember_preference_links_to_last_user_message(mock_memory_client):
    """When no trace but a message exists, links to message."""
    message_id = uuid4()
    mock_memory_client.short_term.add_message = AsyncMock(
        return_value=SimpleNamespace(id=message_id)
    )

    memory = CodingAgentMemory(mock_memory_client, repo="test", task="test-task")
    await memory.add_user_message("I prefer Python")

    pref = SimpleNamespace(id=uuid4())
    mock_memory_client.long_term.add_preference = AsyncMock(return_value=pref)

    await memory.remember_preference("coding", "Prefer Python")

    mock_memory_client.long_term.link_preference_to_evidence.assert_awaited_once_with(
        pref.id, message_id, evidence_type="message"
    )


@pytest.mark.asyncio
async def test_remember_preference_no_provenance_when_no_context(mock_memory_client):
    """When no trace or message exists, no provenance link is created."""
    memory = CodingAgentMemory(mock_memory_client, repo="test", task="test-task")

    pref = SimpleNamespace(id=uuid4())
    mock_memory_client.long_term.add_preference = AsyncMock(return_value=pref)

    await memory.remember_preference("coding", "Prefer Python")

    mock_memory_client.long_term.link_preference_to_evidence.assert_not_awaited()


@pytest.mark.asyncio
async def test_remember_preference_explicit_evidence_ids(mock_memory_client):
    """Explicit evidence_ids override automatic provenance."""
    memory = CodingAgentMemory(mock_memory_client, repo="test", task="test-task")

    pref = SimpleNamespace(id=uuid4())
    mock_memory_client.long_term.add_preference = AsyncMock(return_value=pref)

    evidence = str(uuid4())
    await memory.remember_preference(
        "coding", "Prefer Python", evidence_ids=[evidence]
    )

    mock_memory_client.long_term.link_preference_to_evidence.assert_awaited_once_with(
        pref.id, evidence, evidence_type="message"
    )
