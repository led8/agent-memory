"""Integration tests for the task-scoped coding-agent helper."""

import pytest

from neo4j_agent_memory import (
    CodingAgentMemory,
    LongTermCandidateScopeKind,
    LongTermCandidateSource,
    ToolCallStatus,
)


@pytest.mark.integration
class TestCodingAgentMemoryLongTermIdempotence:
    """Verify durable-write guarantees provided by CodingAgentMemory."""

    @pytest.mark.asyncio
    async def test_replaying_reviewed_preference_candidate_is_idempotent(
        self,
        clean_memory_client,
    ):
        """Persisting the same reviewed preference twice should reuse one node."""
        coding_memory = CodingAgentMemory(
            clean_memory_client,
            repo="agent-memory",
            task="idempotent preference writes",
        )

        candidate = coding_memory.propose_preference_candidate(
            category="workflow",
            preference="Use one session_id per active coding task",
            context="Coding-agent integration",
            source=LongTermCandidateSource.USER_EXPLICIT,
            evidence="Workflow decision explicitly confirmed during planning.",
            scope_kind=LongTermCandidateScopeKind.REPO,
            generate_embedding=False,
        )

        assert candidate is not None

        first = await coding_memory.remember_candidate(candidate)
        second = await coding_memory.remember_candidate(candidate)
        stored = await clean_memory_client.long_term.get_preferences_by_category("workflow")

        matching = [
            pref
            for pref in stored
            if pref.preference == "Use one session_id per active coding task"
            and pref.context == "Coding-agent integration"
            and pref.metadata.get("scope_kind") == "repo"
            and pref.metadata.get("repo") == "agent-memory"
        ]

        assert first.id == second.id
        assert len(matching) == 1

    @pytest.mark.asyncio
    async def test_replaying_reviewed_fact_candidate_is_idempotent(
        self,
        clean_memory_client,
    ):
        """Persisting the same reviewed fact twice should reuse one node."""
        coding_memory = CodingAgentMemory(
            clean_memory_client,
            repo="agent-memory",
            task="idempotent fact writes",
        )

        candidate = coding_memory.propose_fact_candidate(
            subject="Short-term extraction",
            predicate="linking_rule",
            obj="must use persisted entity id returned after Neo4j MERGE",
            source=LongTermCandidateSource.TEST_VERIFIED,
            evidence="Targeted integration test confirmed the linking fix.",
            scope_kind=LongTermCandidateScopeKind.REPO,
            generate_embedding=False,
        )

        assert candidate is not None

        first = await coding_memory.remember_candidate(candidate)
        second = await coding_memory.remember_candidate(candidate)
        stored = await clean_memory_client.long_term.get_facts_about("Short-term extraction")

        matching = [
            fact
            for fact in stored
            if fact.predicate == "linking_rule"
            and fact.object == "must use persisted entity id returned after Neo4j MERGE"
            and fact.metadata.get("scope_kind") == "repo"
            and fact.metadata.get("repo") == "agent-memory"
        ]

        assert first.id == second.id
        assert len(matching) == 1


@pytest.mark.integration
class TestCodingAgentMemoryLongTermSupersession:
    """Verify conflicting durable writes keep history but mark the old entry inactive."""

    @pytest.mark.asyncio
    async def test_new_preference_supersedes_previous_active_preference(
        self,
        clean_memory_client,
    ):
        """A newer preference in the same category/context should supersede the old one."""
        coding_memory = CodingAgentMemory(
            clean_memory_client,
            repo="agent-memory",
            task="preference supersession",
        )

        first = await coding_memory.remember_preference(
            category="communication",
            preference="Prefer terse implementation summaries",
            context="When explaining coding changes",
            metadata={"scope_kind": "repo"},
            generate_embedding=False,
        )
        second = await coding_memory.remember_preference(
            category="communication",
            preference="Include more implementation detail when reviewing memory policy changes",
            context="When explaining coding changes",
            metadata={"scope_kind": "repo"},
            generate_embedding=False,
        )

        active = await clean_memory_client.long_term.get_preferences_by_category("communication")
        all_entries = await clean_memory_client.long_term.get_preferences_by_category(
            "communication",
            include_superseded=True,
        )
        first_entry = next(pref for pref in all_entries if pref.id == first.id)
        second_entry = next(pref for pref in all_entries if pref.id == second.id)

        assert len(active) == 1
        assert active[0].id == second.id
        assert first_entry.metadata["status"] == "superseded"
        assert first_entry.metadata["superseded_by"] == str(second.id)
        assert second_entry.metadata["status"] == "active"
        assert second_entry.metadata["supersedes_ids"] == [str(first.id)]
        edge_rows = await clean_memory_client._client.execute_read(
            """
            MATCH (:Preference {id: $old_id})-[:SUPERSEDED_BY]->(:Preference {id: $new_id})
            RETURN count(*) AS edge_count
            """,
            {"old_id": str(first.id), "new_id": str(second.id)},
        )
        assert edge_rows[0]["edge_count"] == 1


@pytest.mark.integration
class TestCodingAgentMemoryEntityDiscipline:
    """Verify curated entity writes reuse exact matches before adding new nodes."""

    @pytest.mark.asyncio
    async def test_replaying_same_entity_name_and_type_reuses_existing_entity(
        self,
        clean_memory_client,
    ):
        """Exact same-type entity matches should not create duplicate nodes."""
        first, _ = await clean_memory_client.long_term.add_entity(
            name="GLiNER",
            entity_type="TECHNOLOGY",
            metadata={"repo": "agent-memory", "scope_kind": "repo"},
            resolve=False,
            deduplicate=False,
            enrich=False,
            geocode=False,
            generate_embedding=False,
        )

        coding_memory = CodingAgentMemory(
            clean_memory_client,
            repo="agent-memory",
            task="entity discipline",
        )

        second, _ = await coding_memory.remember_entity(
            name="GLiNER",
            entity_type="TECHNOLOGY",
            metadata={"scope_kind": "repo"},
        )

        rows = await clean_memory_client._client.execute_read(
            """
            MATCH (e:Entity {name: $name, type: $type})
            RETURN count(e) AS entity_count
            """,
            {"name": "GLiNER", "type": "TECHNOLOGY"},
        )

        assert first.id == second.id
        assert rows[0]["entity_count"] == 1

    @pytest.mark.asyncio
    async def test_new_fact_supersedes_previous_active_fact(
        self,
        clean_memory_client,
    ):
        """A newer fact with the same subject/predicate should supersede the old one."""
        coding_memory = CodingAgentMemory(
            clean_memory_client,
            repo="agent-memory",
            task="fact supersession",
        )

        first = await coding_memory.remember_fact(
            subject="CodingAgentMemory",
            predicate="long_term_policy",
            obj="propose-only with explicit review",
            metadata={"scope_kind": "repo"},
            generate_embedding=False,
        )
        second = await coding_memory.remember_fact(
            subject="CodingAgentMemory",
            predicate="long_term_policy",
            obj="propose-only with explicit review and supersede conflicting active durable entries",
            metadata={"scope_kind": "repo"},
            generate_embedding=False,
        )

        active = await clean_memory_client.long_term.get_facts_about("CodingAgentMemory")
        all_entries = await clean_memory_client.long_term.get_facts_about(
            "CodingAgentMemory",
            include_superseded=True,
        )
        first_entry = next(fact for fact in all_entries if fact.id == first.id)
        second_entry = next(fact for fact in all_entries if fact.id == second.id)

        assert len(active) == 1
        assert active[0].id == second.id
        assert first_entry.metadata["status"] == "superseded"
        assert first_entry.metadata["superseded_by"] == str(second.id)
        assert second_entry.metadata["status"] == "active"
        assert second_entry.metadata["supersedes_ids"] == [str(first.id)]
        edge_rows = await clean_memory_client._client.execute_read(
            """
            MATCH (:Fact {id: $old_id})-[:SUPERSEDED_BY]->(:Fact {id: $new_id})
            RETURN count(*) AS edge_count
            """,
            {"old_id": str(first.id), "new_id": str(second.id)},
        )
        assert edge_rows[0]["edge_count"] == 1


@pytest.mark.integration
class TestCodingAgentMemoryRecall:
    """Verify coding-oriented startup recall stays repo-focused and useful."""

    @pytest.mark.asyncio
    async def test_startup_recall_includes_repo_scoped_memory_and_reasoning(
        self,
        clean_memory_client,
    ):
        coding_memory = CodingAgentMemory(
            clean_memory_client,
            repo="agent-memory",
            task="debug extraction",
            session_id="coding/agent-memory/debug-extraction/test",
        )

        await coding_memory.save_interaction(
            user_message="Investigate why extracted entities are not linked.",
            assistant_message="I am checking the short-term linking flow.",
        )

        await coding_memory.remember_preference(
            category="workflow",
            preference="Prefer explicit CLI CRUD operations",
            context="agent-memory skill",
            metadata={"scope_kind": "repo"},
            generate_embedding=False,
        )
        await clean_memory_client.long_term.add_preference(
            category="workflow",
            preference="Prefer another repo workflow",
            context="agent-memory skill",
            metadata={"scope_kind": "repo", "repo": "other-repo"},
            generate_embedding=False,
        )
        await coding_memory.remember_fact(
            subject="Short-term extraction",
            predicate="linking_rule",
            obj="must use the persisted entity id returned after Neo4j MERGE",
            metadata={"scope_kind": "repo"},
            generate_embedding=False,
        )

        entity, _ = await coding_memory.remember_entity(
            name="GLiNER",
            entity_type="OBJECT",
            description="Local extraction component",
            metadata={"scope_kind": "repo"},
            resolve=False,
            deduplicate=False,
            enrich=False,
            geocode=False,
        )

        await coding_memory.start_trace(task="Validate shell-first memory workflow")
        await coding_memory.add_trace_step(
            action="inspect short-term linking flow",
            observation="Confirmed the persisted entity id must be reused.",
            generate_embedding=False,
        )
        await coding_memory.record_tool_call(
            "rg",
            {"pattern": "MENTIONS"},
            result="Found the short-term linking query.",
            status=ToolCallStatus.SUCCESS,
        )
        await coding_memory.complete_trace(
            outcome="Shell-first durable coding-agent memory workflow works.",
            success=True,
        )

        recall = await coding_memory.get_startup_recall(
            "How should I debug extraction for agent-memory?",
        )

        assert "## Task Frame" in recall
        assert "## Active Task Stream" in recall
        assert "## Durable Preferences" in recall
        assert "## Durable Facts" in recall
        assert "## Relevant Entities" in recall
        assert "## Similar Past Tasks" in recall
        assert "Prefer explicit CLI CRUD operations" in recall
        assert "Prefer another repo workflow" not in recall
        assert "must use the persisted entity id returned after Neo4j MERGE" in recall
        assert f"{entity.name} [{entity.type}]" in recall
        assert "Tools: rg" in recall
