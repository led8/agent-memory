"""Unit tests for coding-agent workflow helpers."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest

from neo4j_agent_memory import (
    LongTermCandidateConfidence,
    LongTermCandidateScopeKind,
    LongTermCandidateSource,
    LongTermCandidateType,
    ToolCallStatus,
)
from neo4j_agent_memory.integrations import CodingAgentMemory, build_coding_session_id


@pytest.fixture
def mock_memory_client() -> MagicMock:
    """Create a mock MemoryClient."""
    client = MagicMock()
    client.short_term = MagicMock()
    client.long_term = MagicMock()
    client.reasoning = MagicMock()
    client.long_term.get_preferences_by_category = AsyncMock(return_value=[])
    client.long_term.get_facts_about = AsyncMock(return_value=[])
    client.long_term.list_preferences = AsyncMock(return_value=[])
    client.long_term.list_facts = AsyncMock(return_value=[])
    client.long_term.list_entities = AsyncMock(return_value=[])
    client.long_term.update_preference_metadata = AsyncMock()
    client.long_term.update_fact_metadata = AsyncMock()
    client.long_term.link_preference_supersession = AsyncMock(return_value=True)
    client.long_term.link_fact_supersession = AsyncMock(return_value=True)
    client.get_context = AsyncMock(return_value="context")
    client.reasoning.get_session_traces = AsyncMock(return_value=[])
    client.reasoning.get_trace = AsyncMock(return_value=None)
    return client


def test_build_coding_session_id_slugifies_parts() -> None:
    """Session ids should be task-scoped and normalized."""
    session_id = build_coding_session_id(
        "Agent Memory",
        "GLiNER smoke test",
        run_id="Run 42",
    )

    assert session_id == "coding/agent-memory/gliner-smoke-test/run-42"


def test_build_coding_session_id_rejects_empty_values() -> None:
    """Empty session-id parts should fail fast."""
    with pytest.raises(ValueError, match="repo must contain"):
        build_coding_session_id("///", "task")


def test_initialization_uses_explicit_session_id(mock_memory_client: MagicMock) -> None:
    """Explicit session ids should be preserved."""
    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="helper integration",
        session_id="coding/custom/session",
    )

    assert memory.session_id == "coding/custom/session"
    assert memory.repo == "agent-memory"
    assert memory.task == "helper integration"


@pytest.mark.asyncio
async def test_add_user_message_tracks_last_user_message(mock_memory_client: MagicMock) -> None:
    """User messages should use task metadata and remember the triggering message id."""
    message_id = uuid4()
    mock_memory_client.short_term.add_message = AsyncMock(
        return_value=SimpleNamespace(id=message_id)
    )
    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="GLiNER smoke test",
        session_id="coding/agent-memory/gliner-smoke-test/test",
    )

    message = await memory.add_user_message("Need a local GLiNER spike")

    assert message.id == message_id
    mock_memory_client.short_term.add_message.assert_awaited_once()
    kwargs = mock_memory_client.short_term.add_message.await_args.kwargs
    assert kwargs["session_id"] == memory.session_id
    assert kwargs["role"] == "user"
    assert kwargs["extract_entities"] is True
    assert kwargs["metadata"]["repo"] == "agent-memory"
    assert kwargs["metadata"]["task"] == "GLiNER smoke test"


@pytest.mark.asyncio
async def test_add_assistant_message_disables_extraction_by_default(
    mock_memory_client: MagicMock,
) -> None:
    """Assistant messages should not extract entities by default."""
    mock_memory_client.short_term.add_message = AsyncMock(
        return_value=SimpleNamespace(id=uuid4())
    )
    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="helper integration",
    )

    await memory.add_assistant_message("Use the Python API first.")

    kwargs = mock_memory_client.short_term.add_message.await_args.kwargs
    assert kwargs["role"] == "assistant"
    assert kwargs["extract_entities"] is False


@pytest.mark.asyncio
async def test_start_trace_uses_last_user_message_id(mock_memory_client: MagicMock) -> None:
    """Reasoning traces should link back to the last user turn by default."""
    last_message_id = uuid4()
    trace_id = uuid4()
    mock_memory_client.short_term.add_message = AsyncMock(
        return_value=SimpleNamespace(id=last_message_id)
    )
    mock_memory_client.reasoning.start_trace = AsyncMock(return_value=SimpleNamespace(id=trace_id))
    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="trace helper",
    )

    await memory.add_user_message("Please investigate the extraction flow.")
    trace = await memory.start_trace()

    assert trace.id == trace_id
    kwargs = mock_memory_client.reasoning.start_trace.await_args.kwargs
    assert kwargs["session_id"] == memory.session_id
    assert kwargs["task"] == "trace helper"
    assert kwargs["triggered_by_message_id"] == last_message_id
    assert kwargs["metadata"]["repo"] == "agent-memory"


@pytest.mark.asyncio
async def test_record_tool_call_uses_active_step_and_last_user_message(
    mock_memory_client: MagicMock,
) -> None:
    """Tool calls should default to the active step and triggering user message."""
    last_message_id = uuid4()
    trace_id = uuid4()
    step_id = uuid4()
    tool_call_id = uuid4()

    mock_memory_client.short_term.add_message = AsyncMock(
        return_value=SimpleNamespace(id=last_message_id)
    )
    mock_memory_client.reasoning.start_trace = AsyncMock(return_value=SimpleNamespace(id=trace_id))
    mock_memory_client.reasoning.add_step = AsyncMock(return_value=SimpleNamespace(id=step_id))
    mock_memory_client.reasoning.record_tool_call = AsyncMock(
        return_value=SimpleNamespace(id=tool_call_id)
    )

    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="record tool call",
    )

    await memory.add_user_message("Inspect the short-term extraction path.")
    await memory.start_trace()
    await memory.add_trace_step(action="inspect code")
    tool_call = await memory.record_tool_call(
        "rg",
        {"query": "extract_entities"},
        result={"matches": 2},
        status=ToolCallStatus.SUCCESS,
    )

    assert tool_call.id == tool_call_id
    args = mock_memory_client.reasoning.record_tool_call.await_args.args
    kwargs = mock_memory_client.reasoning.record_tool_call.await_args.kwargs
    assert args[0] == step_id
    assert kwargs["tool_name"] == "rg"
    assert kwargs["message_id"] == last_message_id


@pytest.mark.asyncio
async def test_complete_trace_resets_active_trace_state(mock_memory_client: MagicMock) -> None:
    """Completing a trace should clear active step/trace ids."""
    trace_id = uuid4()
    mock_memory_client.reasoning.start_trace = AsyncMock(return_value=SimpleNamespace(id=trace_id))
    mock_memory_client.reasoning.complete_trace = AsyncMock(
        return_value=SimpleNamespace(id=trace_id, success=True)
    )
    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="complete trace",
    )

    await memory.start_trace()
    result = await memory.complete_trace(outcome="done", success=True)

    assert result.id == trace_id
    assert memory._active_trace_id is None
    assert memory._active_step_id is None


@pytest.mark.asyncio
async def test_get_context_defaults_to_task_query(mock_memory_client: MagicMock) -> None:
    """Context lookup should default to the task label when no query is supplied."""
    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="helper integration",
        session_id="coding/agent-memory/helper-integration/test",
    )

    result = await memory.get_context()

    assert result == "context"
    mock_memory_client.get_context.assert_awaited_once_with(
        query="helper integration",
        session_id=memory.session_id,
        include_short_term=True,
        include_long_term=True,
        include_reasoning=True,
        max_items=10,
    )


@pytest.mark.asyncio
async def test_get_startup_recall_assembles_coding_sections(mock_memory_client: MagicMock) -> None:
    """Startup recall should build a sharper coding-oriented context."""
    mock_memory_client.short_term.get_conversation = AsyncMock(
        return_value=SimpleNamespace(
            messages=[
                SimpleNamespace(role=SimpleNamespace(value="user"), content="Investigate extraction."),
                SimpleNamespace(
                    role=SimpleNamespace(value="assistant"),
                    content="I will inspect the short-term linking flow.",
                ),
            ]
        )
    )
    mock_memory_client.long_term.search_preferences = AsyncMock(
        return_value=[
            SimpleNamespace(
                category="workflow",
                preference="Prefer explicit CLI CRUD operations",
                context="agent-memory skill",
                metadata={"repo": "agent-memory", "scope_kind": "repo"},
            ),
            SimpleNamespace(
                category="workflow",
                preference="Other repo preference",
                context=None,
                metadata={"repo": "other-repo", "scope_kind": "repo"},
            ),
        ]
    )
    mock_memory_client.long_term.search_facts = AsyncMock(
        return_value=[
            SimpleNamespace(
                subject="Short-term extraction",
                predicate="linking_rule",
                object="must reuse the persisted entity id after MERGE",
                metadata={"repo": "agent-memory", "scope_kind": "repo"},
            )
        ]
    )
    mock_memory_client.long_term.search_entities = AsyncMock(
        return_value=[
            SimpleNamespace(
                name="GLiNER",
                type="OBJECT",
                description="Local extraction component",
                metadata={"repo": "agent-memory", "scope_kind": "repo"},
            )
        ]
    )
    mock_memory_client.reasoning.get_context = AsyncMock(
        return_value="**Task**: Validate shell-first memory workflow\n- Tools: rg"
    )

    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="debug extraction",
        session_id="coding/agent-memory/debug-extraction/test",
    )

    result = await memory.get_startup_recall("How should I debug extraction?")

    assert "## Task Frame" in result
    assert "## Active Task Stream" in result
    assert "## Durable Preferences" in result
    assert "## Durable Facts" in result
    assert "## Relevant Entities" in result
    assert "## Similar Past Tasks" in result
    assert "Prefer explicit CLI CRUD operations" in result
    assert "Other repo preference" not in result
    assert "must reuse the persisted entity id after MERGE" in result
    assert "GLiNER [OBJECT]" in result
    mock_memory_client.long_term.search_preferences.assert_awaited_once_with(
        "How should I debug extraction?",
        limit=5,
        threshold=0.0,
    )
    mock_memory_client.long_term.search_facts.assert_awaited_once_with(
        "How should I debug extraction?",
        limit=5,
        threshold=0.0,
    )
    mock_memory_client.long_term.search_entities.assert_awaited_once_with(
        "How should I debug extraction?",
        limit=5,
        threshold=0.0,
    )
    mock_memory_client.reasoning.get_context.assert_awaited_once_with(
        "How should I debug extraction?",
        max_traces=3,
    )


@pytest.mark.asyncio
async def test_get_startup_recall_falls_back_to_repo_list_when_search_is_empty(
    mock_memory_client: MagicMock,
) -> None:
    """Startup recall should still surface repo durable memory when embeddings are missing."""
    mock_memory_client.short_term.get_conversation = AsyncMock(
        return_value=SimpleNamespace(messages=[])
    )
    mock_memory_client.long_term.search_preferences = AsyncMock(return_value=[])
    mock_memory_client.long_term.search_facts = AsyncMock(return_value=[])
    mock_memory_client.long_term.search_entities = AsyncMock(return_value=[])
    mock_memory_client.long_term.list_preferences = AsyncMock(
        return_value=[
            SimpleNamespace(
                id=uuid4(),
                category="workflow",
                preference="Prefer explicit CLI CRUD operations",
                context="agent-memory skill",
                metadata={"repo": "agent-memory", "scope_kind": "repo"},
            )
        ]
    )
    mock_memory_client.long_term.list_facts = AsyncMock(
        return_value=[
            SimpleNamespace(
                id=uuid4(),
                subject="Short-term extraction",
                predicate="linking_rule",
                object="must reuse the persisted entity id after MERGE",
                metadata={"repo": "agent-memory", "scope_kind": "repo"},
            )
        ]
    )
    mock_memory_client.long_term.list_entities = AsyncMock(
        return_value=[
            SimpleNamespace(
                id=uuid4(),
                name="GLiNER",
                type="OBJECT",
                description="Local extraction component",
                metadata={"repo": "agent-memory", "scope_kind": "repo"},
            )
        ]
    )
    mock_memory_client.reasoning.get_context = AsyncMock(return_value="")

    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="debug extraction",
        session_id="coding/agent-memory/debug-extraction/test",
    )

    result = await memory.get_startup_recall("How should I debug extraction?")

    assert "Prefer explicit CLI CRUD operations" in result
    assert "must reuse the persisted entity id after MERGE" in result
    assert "GLiNER [OBJECT]" in result
    mock_memory_client.long_term.list_preferences.assert_awaited_once_with(
        repo="agent-memory",
        include_personal=True,
        limit=5,
    )
    mock_memory_client.long_term.list_facts.assert_awaited_once_with(
        repo="agent-memory",
        include_personal=True,
        limit=5,
    )
    mock_memory_client.long_term.list_entities.assert_awaited_once_with(
        repo="agent-memory",
        include_personal=True,
        limit=5,
    )


@pytest.mark.asyncio
async def test_get_startup_recall_falls_back_to_session_reasoning_when_similarity_is_empty(
    mock_memory_client: MagicMock,
) -> None:
    """Startup recall should still expose current-session reasoning details."""
    trace_id = uuid4()
    mock_memory_client.short_term.get_conversation = AsyncMock(
        return_value=SimpleNamespace(messages=[])
    )
    mock_memory_client.long_term.search_preferences = AsyncMock(return_value=[])
    mock_memory_client.long_term.search_facts = AsyncMock(return_value=[])
    mock_memory_client.long_term.search_entities = AsyncMock(return_value=[])
    mock_memory_client.reasoning.get_context = AsyncMock(return_value="")
    mock_memory_client.reasoning.get_session_traces = AsyncMock(
        return_value=[
            SimpleNamespace(
                id=trace_id,
                task="Validate shell-first memory workflow",
                outcome="Shell-first workflow works.",
                success=True,
                steps=[],
            )
        ]
    )
    mock_memory_client.reasoning.get_trace = AsyncMock(
        return_value=SimpleNamespace(
            id=trace_id,
            task="Validate shell-first memory workflow",
            outcome="Shell-first workflow works.",
            success=True,
            steps=[
                SimpleNamespace(
                    action="inspect short-term linking flow",
                    observation="Confirmed the persisted entity id must be reused.",
                    tool_calls=[SimpleNamespace(tool_name="rg")],
                )
            ],
        )
    )

    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="debug extraction",
        session_id="coding/agent-memory/debug-extraction/test",
    )

    result = await memory.get_startup_recall("How should I debug extraction?")

    assert "## Similar Past Tasks" in result
    assert "Validate shell-first memory workflow" in result
    assert "Tools: rg" in result
    mock_memory_client.reasoning.get_session_traces.assert_awaited_once_with(
        "coding/agent-memory/debug-extraction/test",
        limit=3,
    )
    mock_memory_client.reasoning.get_trace.assert_awaited_once_with(trace_id)


def test_propose_preference_candidate_marks_explicit_user_input_as_high_confidence(
    mock_memory_client: MagicMock,
) -> None:
    """Explicit durable preferences should become high-confidence review candidates."""
    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="policy review",
    )

    candidate = memory.propose_preference_candidate(
        category="workflow",
        preference="Use one session_id per active coding task",
        context="Coding-agent integration",
        source=LongTermCandidateSource.USER_EXPLICIT,
        evidence="User explicitly requested task-scoped sessions.",
        scope_kind=LongTermCandidateScopeKind.REPO,
    )

    assert candidate is not None
    assert candidate.type == LongTermCandidateType.PREFERENCE
    assert candidate.confidence == LongTermCandidateConfidence.HIGH
    assert candidate.recommended is True
    assert candidate.payload["metadata"]["repo"] == "agent-memory"
    assert candidate.payload["metadata"]["task"] == "policy review"
    assert candidate.payload["metadata"]["scope_kind"] == "repo"
    assert candidate.payload["metadata"]["candidate_source"] == "user_explicit"


def test_propose_fact_candidate_returns_none_when_not_durable(
    mock_memory_client: MagicMock,
) -> None:
    """Low-confidence facts should not become long-term review candidates."""
    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="policy review",
    )

    candidate = memory.propose_fact_candidate(
        subject="Temporary debug note",
        predicate="status",
        obj="only relevant for this session",
        source=LongTermCandidateSource.RUN_OBSERVATION,
        evidence="Observed during an incomplete run.",
        durable=False,
        reusable=False,
    )

    assert candidate is None


@pytest.mark.asyncio
async def test_remember_candidate_persists_high_confidence_fact(
    mock_memory_client: MagicMock,
) -> None:
    """Reviewed high-confidence candidates should persist through the matching helper."""
    fact = SimpleNamespace(id=uuid4())
    mock_memory_client.long_term.add_fact = AsyncMock(return_value=fact)
    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="policy review",
    )

    candidate = memory.propose_fact_candidate(
        subject="Short-term extraction",
        predicate="linking_rule",
        obj="must use persisted entity id returned after Neo4j MERGE",
        source=LongTermCandidateSource.TEST_VERIFIED,
        evidence="Integration test reproduced and confirmed the fix.",
    )

    assert candidate is not None
    result = await memory.remember_candidate(candidate)

    assert result is fact
    mock_memory_client.long_term.add_fact.assert_awaited_once()
    kwargs = mock_memory_client.long_term.add_fact.await_args.kwargs
    assert kwargs["subject"] == "Short-term extraction"
    assert kwargs["metadata"]["candidate_confidence"] == "high"


@pytest.mark.asyncio
async def test_remember_candidate_rejects_medium_confidence_without_override(
    mock_memory_client: MagicMock,
) -> None:
    """Medium-confidence candidates require an explicit override before persistence."""
    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="policy review",
    )

    candidate = memory.propose_entity_candidate(
        name="GLiNER",
        entity_type="TECHNOLOGY",
        source=LongTermCandidateSource.RUN_OBSERVATION,
        evidence="Observed in one successful local run.",
    )

    assert candidate is not None
    assert candidate.confidence == LongTermCandidateConfidence.MEDIUM
    with pytest.raises(ValueError, match="allow_medium_confidence=True"):
        await memory.remember_candidate(candidate)


@pytest.mark.asyncio
async def test_remember_candidate_allows_medium_confidence_with_override(
    mock_memory_client: MagicMock,
) -> None:
    """Operators can still persist medium-confidence candidates after explicit review."""
    preference = SimpleNamespace(id=uuid4())
    mock_memory_client.long_term.add_preference = AsyncMock(return_value=preference)
    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="policy review",
    )

    candidate = memory.propose_preference_candidate(
        category="workflow",
        preference="Prefer GLiNER for local extraction during early integration",
        context="Observed during phase-1 setup",
        source=LongTermCandidateSource.RUN_OBSERVATION,
        evidence="Worked well in the initial local integration run.",
    )

    assert candidate is not None
    result = await memory.remember_candidate(candidate, allow_medium_confidence=True)

    assert result is preference
    mock_memory_client.long_term.add_preference.assert_awaited_once()


@pytest.mark.asyncio
async def test_remember_preference_returns_existing_duplicate(
    mock_memory_client: MagicMock,
) -> None:
    """Preference writes should be idempotent within the same durable scope."""
    existing = SimpleNamespace(
        id=uuid4(),
        preference="Use one session_id per active coding task",
        context="Coding-agent integration",
        metadata={"repo": "agent-memory", "scope_kind": "repo"},
    )
    mock_memory_client.long_term.get_preferences_by_category = AsyncMock(return_value=[existing])
    mock_memory_client.long_term.add_preference = AsyncMock()
    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="policy review",
    )

    result = await memory.remember_preference(
        category="workflow",
        preference="Use one session_id per active coding task",
        context="Coding-agent integration",
        metadata={"scope_kind": "repo"},
    )

    assert result is existing
    mock_memory_client.long_term.add_preference.assert_not_called()


@pytest.mark.asyncio
async def test_remember_fact_returns_existing_duplicate(
    mock_memory_client: MagicMock,
) -> None:
    """Fact writes should be idempotent within the same durable scope."""
    existing = SimpleNamespace(
        id=uuid4(),
        predicate="linking_rule",
        object="must use persisted entity id returned after Neo4j MERGE",
        metadata={"repo": "agent-memory", "scope_kind": "repo"},
    )
    mock_memory_client.long_term.get_facts_about = AsyncMock(return_value=[existing])
    mock_memory_client.long_term.add_fact = AsyncMock()
    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="policy review",
    )

    result = await memory.remember_fact(
        subject="Short-term extraction",
        predicate="linking_rule",
        obj="must use persisted entity id returned after Neo4j MERGE",
        metadata={"scope_kind": "repo"},
    )

    assert result is existing
    mock_memory_client.long_term.add_fact.assert_not_called()


@pytest.mark.asyncio
async def test_remember_preference_supersedes_conflicting_active_entry(
    mock_memory_client: MagicMock,
) -> None:
    """A conflicting preference in the same durable scope should be superseded."""
    existing = SimpleNamespace(
        id=uuid4(),
        preference="Prefer terse implementation summaries",
        context="When explaining coding changes",
        metadata={"repo": "agent-memory", "scope_kind": "repo", "status": "active"},
    )
    created = SimpleNamespace(id=uuid4())
    mock_memory_client.long_term.get_preferences_by_category = AsyncMock(return_value=[existing])
    mock_memory_client.long_term.add_preference = AsyncMock(return_value=created)
    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="policy review",
    )

    result = await memory.remember_preference(
        category="communication",
        preference="Include more implementation detail when reviewing memory policy changes",
        context="When explaining coding changes",
        metadata={"scope_kind": "repo"},
    )

    assert result is created
    add_kwargs = mock_memory_client.long_term.add_preference.await_args.kwargs
    assert add_kwargs["metadata"]["status"] == "active"
    assert add_kwargs["metadata"]["supersedes_ids"] == [str(existing.id)]
    update_args = mock_memory_client.long_term.update_preference_metadata.await_args.args
    update_metadata = mock_memory_client.long_term.update_preference_metadata.await_args.args[1]
    assert update_args[0] == existing.id
    assert update_metadata["status"] == "superseded"
    assert update_metadata["superseded_by"] == str(created.id)
    mock_memory_client.long_term.link_preference_supersession.assert_awaited_once_with(
        existing.id,
        created.id,
        reason=(
            "Superseded by a newer preference in the same category, context, "
            "and durable scope."
        ),
    )


@pytest.mark.asyncio
async def test_remember_fact_supersedes_conflicting_active_entry(
    mock_memory_client: MagicMock,
) -> None:
    """A conflicting fact in the same durable scope should be superseded."""
    existing = SimpleNamespace(
        id=uuid4(),
        predicate="long_term_policy",
        object="propose-only with explicit review",
        metadata={"repo": "agent-memory", "scope_kind": "repo", "status": "active"},
    )
    created = SimpleNamespace(id=uuid4())
    mock_memory_client.long_term.get_facts_about = AsyncMock(return_value=[existing])
    mock_memory_client.long_term.add_fact = AsyncMock(return_value=created)
    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="policy review",
    )

    result = await memory.remember_fact(
        subject="CodingAgentMemory",
        predicate="long_term_policy",
        obj="propose-only with explicit review and supersede conflicting durable entries",
        metadata={"scope_kind": "repo"},
    )

    assert result is created
    add_kwargs = mock_memory_client.long_term.add_fact.await_args.kwargs
    assert add_kwargs["metadata"]["status"] == "active"
    assert add_kwargs["metadata"]["supersedes_ids"] == [str(existing.id)]
    update_args = mock_memory_client.long_term.update_fact_metadata.await_args.args
    update_metadata = mock_memory_client.long_term.update_fact_metadata.await_args.args[1]
    assert update_args[0] == existing.id
    assert update_metadata["status"] == "superseded"
    assert update_metadata["superseded_by"] == str(created.id)
    mock_memory_client.long_term.link_fact_supersession.assert_awaited_once_with(
        existing.id,
        created.id,
        reason=(
            "Superseded by a newer fact with the same subject, predicate, "
            "and durable scope."
        ),
    )


@pytest.mark.asyncio
async def test_remember_entity_returns_existing_exact_match_same_type(
    mock_memory_client: MagicMock,
) -> None:
    """Exact same-type entity matches should be reused before deeper deduplication."""
    existing = SimpleNamespace(id=uuid4(), type="TECHNOLOGY")
    mock_memory_client.long_term.get_entity_by_name = AsyncMock(return_value=existing)
    mock_memory_client.long_term.add_entity = AsyncMock()
    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="entity discipline",
    )

    entity, dedup_result = await memory.remember_entity(
        name="GLiNER",
        entity_type="technology",
        metadata={"scope_kind": "repo"},
    )

    assert entity is existing
    assert dedup_result is None
    mock_memory_client.long_term.add_entity.assert_not_called()


@pytest.mark.asyncio
async def test_remember_entity_uses_resolution_and_deduplication_by_default(
    mock_memory_client: MagicMock,
) -> None:
    """New curated entities should use the store's resolve/deduplicate path by default."""
    created = SimpleNamespace(id=uuid4(), type="TECHNOLOGY")
    mock_memory_client.long_term.get_entity_by_name = AsyncMock(return_value=None)
    mock_memory_client.long_term.add_entity = AsyncMock(return_value=(created, None))
    memory = CodingAgentMemory(
        mock_memory_client,
        repo="agent-memory",
        task="entity discipline",
    )

    result = await memory.remember_entity(
        name="GLiNER",
        entity_type="TECHNOLOGY",
        metadata={"scope_kind": "repo"},
    )

    assert result == (created, None)
    kwargs = mock_memory_client.long_term.add_entity.await_args.kwargs
    assert kwargs["resolve"] is True
    assert kwargs["deduplicate"] is True
    assert kwargs["metadata"]["repo"] == "agent-memory"
