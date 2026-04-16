#!/usr/bin/env python3
"""
Task-scoped coding-agent workflow example for neo4j-agent-memory.

This example builds on the local development setup used by the smoke test:
- real Neo4j backend
- local hashed embedder
- local GLiNER extraction
- no LLM fallback

It demonstrates the higher-level CodingAgentMemory helper rather than the raw
MemoryClient surface.
"""

from __future__ import annotations

import asyncio

from neo4j_agent_memory import (
    CodingAgentMemory,
    LongTermCandidateSource,
    MemoryClient,
    ToolCallStatus,
)

from coding_agent_smoke_test import LocalHashedEmbedder, build_settings


async def main() -> None:
    settings = build_settings()
    embedder = LocalHashedEmbedder(dimensions=384)

    async with MemoryClient(settings, embedder=embedder) as memory:
        coding_memory = CodingAgentMemory(
            memory,
            repo="agent-memory",
            task="debug short-term extraction",
        )

        print("Connected to Neo4j Agent Memory")
        print(f"Session ID: {coding_memory.session_id}")
        startup_recall = await coding_memory.get_startup_recall()
        print("\nStartup recall:")
        print(startup_recall or "(empty)")

        user_message = await coding_memory.add_user_message(
            (
                "Investigate why short-term extraction can miss MENTIONS links when "
                "Neo4j merges an existing entity node."
            )
        )
        await coding_memory.start_trace()
        await coding_memory.add_trace_step(
            thought="Compare the extractor output with the ids actually persisted by Neo4j.",
            action="inspect short-term extraction flow",
        )
        await coding_memory.record_tool_call(
            "rg",
            {"query": "LINK_MESSAGE_TO_ENTITY"},
            result={"matches": 1},
            status=ToolCallStatus.SUCCESS,
            message_id=user_message.id,
        )

        fact_candidate = coding_memory.propose_fact_candidate(
            subject="Short-term extraction",
            predicate="linking_rule",
            obj="must use persisted entity id returned after Neo4j MERGE",
            source=LongTermCandidateSource.TEST_VERIFIED,
            evidence="Confirmed by the targeted integration test for MENTIONS linking.",
        )
        preference_candidate = coding_memory.propose_preference_candidate(
            category="workflow",
            preference="Use one session_id per active coding task",
            context="Coding-agent integration",
            source=LongTermCandidateSource.USER_EXPLICIT,
            evidence="Workflow decision explicitly confirmed during integration planning.",
        )
        observed_entity_candidate = coding_memory.propose_entity_candidate(
            name="GLiNER",
            entity_type="TECHNOLOGY",
            source=LongTermCandidateSource.RUN_OBSERVATION,
            evidence="Observed in the current local extraction flow.",
        )

        print("\nReview candidates:")
        for candidate in [fact_candidate, preference_candidate, observed_entity_candidate]:
            if candidate is None:
                continue
            print(
                f"- {candidate.type.value} | confidence={candidate.confidence.value} | "
                f"recommended={candidate.recommended} | {candidate.content}"
            )

        if fact_candidate is not None:
            await coding_memory.remember_candidate(fact_candidate)
        if preference_candidate is not None:
            await coding_memory.remember_candidate(preference_candidate)
            await coding_memory.remember_candidate(preference_candidate)

        await coding_memory.add_assistant_message(
            (
                "The safe fix is to read the entity id returned by Neo4j after MERGE "
                "and use that id for the MENTIONS relationship."
            )
        )
        await coding_memory.complete_trace(
            outcome="Confirmed the linking bug and captured the corrected rule.",
            success=True,
        )

        context = await coding_memory.get_context(
            "How should I debug short-term entity extraction for coding workflows?"
        )

        print("\nCombined context:")
        print(context or "(empty)")
        print(
            "\nReplaying the same reviewed preference candidate does not create a duplicate "
            "because CodingAgentMemory now deduplicates long-term facts and preferences "
            "within the same durable scope."
        )
        if observed_entity_candidate is not None and not observed_entity_candidate.recommended:
            print(
                "\nGLiNER was kept as a review-only candidate because run observations stay "
                "medium-confidence by default in Policy V1.1."
            )


if __name__ == "__main__":
    asyncio.run(main())
