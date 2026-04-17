"""Integration tests for the memory CLI surface."""

from __future__ import annotations

import json
from uuid import uuid4

from click.testing import CliRunner
from neo4j import GraphDatabase
import pytest

from neo4j_agent_memory.cli.main import cli
from neo4j_agent_memory.graph import queries


def _memory_args(neo4j_connection_info: dict[str, str]) -> list[str]:
    return [
        "memory",
        "--uri",
        neo4j_connection_info["uri"],
        "--user",
        neo4j_connection_info["username"],
        "--password",
        neo4j_connection_info["password"],
        "--hashed-local-embedder",
    ]


@pytest.fixture(autouse=True)
def clean_cli_graph(neo4j_connection_info: dict[str, str]):
    """Keep CLI integration tests isolated."""
    driver = GraphDatabase.driver(
        neo4j_connection_info["uri"],
        auth=(neo4j_connection_info["username"], neo4j_connection_info["password"]),
    )
    try:
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        yield
    finally:
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        driver.close()


@pytest.mark.integration
def test_memory_cli_add_fact_is_idempotent(neo4j_connection_info: dict[str, str]) -> None:
    runner = CliRunner()
    args = _memory_args(neo4j_connection_info)
    command = args + [
        "add-fact",
        "--repo",
        "agent-memory",
        "--task",
        "cli test",
        "--subject",
        "CLI memory",
        "--predicate",
        "best_start",
        "--object-value",
        "real shell commands",
    ]

    first = runner.invoke(cli, command)
    second = runner.invoke(cli, command)

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert json.loads(first.output)["fact"]["id"] == json.loads(second.output)["fact"]["id"]


@pytest.mark.integration
def test_memory_cli_replace_fact_supersedes_previous_fact(
    neo4j_connection_info: dict[str, str],
) -> None:
    runner = CliRunner()
    args = _memory_args(neo4j_connection_info)

    created = runner.invoke(
        cli,
        args
        + [
            "add-fact",
            "--repo",
            "agent-memory",
            "--task",
            "cli test",
            "--subject",
            "CLI memory",
            "--predicate",
            "best_start",
            "--object-value",
            "real shell commands",
        ],
    )
    assert created.exit_code == 0, created.output
    created_id = json.loads(created.output)["fact"]["id"]

    replaced = runner.invoke(
        cli,
        args
        + [
            "replace-fact",
            "--id",
            created_id,
            "--object-value",
            "real CLI CRUD commands",
        ],
    )
    assert replaced.exit_code == 0, replaced.output
    new_id = json.loads(replaced.output)["fact"]["id"]
    assert new_id != created_id

    inspected = runner.invoke(
        cli,
        args + ["inspect", "--kind", "fact", "--id", created_id],
    )
    assert inspected.exit_code == 0, inspected.output
    metadata = json.loads(inspected.output)["entry"]["metadata"]
    assert metadata["status"] == "superseded"
    assert metadata["superseded_by"] == new_id
    driver = GraphDatabase.driver(
        neo4j_connection_info["uri"],
        auth=(neo4j_connection_info["username"], neo4j_connection_info["password"]),
    )
    try:
        with driver.session() as session:
            edge_count = session.run(
                """
                MATCH (:Fact {id: $old_id})-[:SUPERSEDED_BY]->(:Fact {id: $new_id})
                RETURN count(*) AS edge_count
                """,
                {"old_id": created_id, "new_id": new_id},
            ).single()["edge_count"]
    finally:
        driver.close()
    assert edge_count == 1


@pytest.mark.integration
def test_memory_cli_add_preference_is_idempotent(neo4j_connection_info: dict[str, str]) -> None:
    runner = CliRunner()
    args = _memory_args(neo4j_connection_info)
    command = args + [
        "add-preference",
        "--repo",
        "agent-memory",
        "--task",
        "cli test",
        "--category",
        "workflow",
        "--preference",
        "Prefer CLI-first memory operations",
        "--context",
        "Skill design",
    ]

    first = runner.invoke(cli, command)
    second = runner.invoke(cli, command)

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert json.loads(first.output)["preference"]["id"] == json.loads(second.output)["preference"]["id"]


@pytest.mark.integration
def test_memory_cli_replace_preference_supersedes_previous_preference(
    neo4j_connection_info: dict[str, str],
) -> None:
    runner = CliRunner()
    args = _memory_args(neo4j_connection_info)

    created = runner.invoke(
        cli,
        args
        + [
            "add-preference",
            "--repo",
            "agent-memory",
            "--task",
            "cli test",
            "--category",
            "workflow",
            "--preference",
            "Prefer CLI-first memory operations",
            "--context",
            "Skill design",
        ],
    )
    assert created.exit_code == 0, created.output
    created_id = json.loads(created.output)["preference"]["id"]

    replaced = runner.invoke(
        cli,
        args
        + [
            "replace-preference",
            "--id",
            created_id,
            "--preference",
            "Prefer explicit CLI CRUD operations",
        ],
    )
    assert replaced.exit_code == 0, replaced.output
    new_id = json.loads(replaced.output)["preference"]["id"]
    assert new_id != created_id

    inspected = runner.invoke(
        cli,
        args + ["inspect", "--kind", "preference", "--id", created_id],
    )
    assert inspected.exit_code == 0, inspected.output
    metadata = json.loads(inspected.output)["entry"]["metadata"]
    assert metadata["status"] == "superseded"
    assert metadata["superseded_by"] == new_id
    driver = GraphDatabase.driver(
        neo4j_connection_info["uri"],
        auth=(neo4j_connection_info["username"], neo4j_connection_info["password"]),
    )
    try:
        with driver.session() as session:
            edge_count = session.run(
                """
                MATCH (:Preference {id: $old_id})-[:SUPERSEDED_BY]->(:Preference {id: $new_id})
                RETURN count(*) AS edge_count
                """,
                {"old_id": created_id, "new_id": new_id},
            ).single()["edge_count"]
    finally:
        driver.close()
    assert edge_count == 1


@pytest.mark.integration
def test_memory_cli_add_entity_reuses_exact_same_name_and_type(
    neo4j_connection_info: dict[str, str],
) -> None:
    runner = CliRunner()
    args = _memory_args(neo4j_connection_info)
    command = args + [
        "add-entity",
        "--repo",
        "agent-memory",
        "--task",
        "cli test",
        "--name",
        "agent-memory",
        "--type",
        "OBJECT",
        "--description",
        "Neo4j Agent Memory repo",
    ]

    first = runner.invoke(cli, command)
    second = runner.invoke(cli, command)

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert json.loads(first.output)["entity"]["id"] == json.loads(second.output)["entity"]["id"]


@pytest.mark.integration
def test_memory_cli_update_entity_preserves_identity_and_old_name_as_alias(
    neo4j_connection_info: dict[str, str],
) -> None:
    runner = CliRunner()
    args = _memory_args(neo4j_connection_info)

    created = runner.invoke(
        cli,
        args
        + [
            "add-entity",
            "--repo",
            "agent-memory",
            "--task",
            "entity update test",
            "--name",
            "agent-memory",
            "--type",
            "OBJECT",
        ],
    )
    assert created.exit_code == 0, created.output
    entity_id = json.loads(created.output)["entity"]["id"]

    updated = runner.invoke(
        cli,
        args
        + [
            "update-entity",
            "--id",
            entity_id,
            "--name",
            "Neo4j Agent Memory",
            "--description",
            "The repository and package for agent memory.",
        ],
    )
    assert updated.exit_code == 0, updated.output
    payload = json.loads(updated.output)
    assert payload["entity"]["id"] == entity_id
    assert payload["entity"]["name"] == "Neo4j Agent Memory"
    assert payload["entity"]["canonical_name"] == "Neo4j Agent Memory"
    assert "agent-memory" in payload["entity"]["aliases"]


@pytest.mark.integration
def test_memory_cli_alias_entity_is_idempotent_and_detects_conflicts(
    neo4j_connection_info: dict[str, str],
) -> None:
    runner = CliRunner()
    args = _memory_args(neo4j_connection_info)

    first = runner.invoke(
        cli,
        args
        + [
            "add-entity",
            "--repo",
            "agent-memory",
            "--task",
            "entity alias test",
            "--name",
            "Neo4j Agent Memory",
            "--type",
            "OBJECT",
        ],
    )
    assert first.exit_code == 0, first.output
    first_id = json.loads(first.output)["entity"]["id"]

    alias_once = runner.invoke(
        cli,
        args + ["alias-entity", "--id", first_id, "--alias", "agent-memory"],
    )
    alias_twice = runner.invoke(
        cli,
        args + ["alias-entity", "--id", first_id, "--alias", "agent-memory"],
    )
    assert alias_once.exit_code == 0, alias_once.output
    assert alias_twice.exit_code == 0, alias_twice.output
    aliases = json.loads(alias_twice.output)["entity"]["aliases"]
    assert aliases.count("agent-memory") == 1

    second = runner.invoke(
        cli,
        args
        + [
            "add-entity",
            "--repo",
            "agent-memory",
            "--task",
            "entity alias test",
            "--name",
            "GLiNER",
            "--type",
            "OBJECT",
        ],
    )
    assert second.exit_code == 0, second.output
    second_id = json.loads(second.output)["entity"]["id"]

    conflict = runner.invoke(
        cli,
        args + ["alias-entity", "--id", second_id, "--alias", "agent-memory"],
    )
    assert conflict.exit_code != 0
    assert "already resolves to entity" in conflict.output


@pytest.mark.integration
def test_memory_cli_merge_entity_transfers_relationships_and_aliases(
    neo4j_connection_info: dict[str, str],
) -> None:
    runner = CliRunner()
    args = _memory_args(neo4j_connection_info)

    source = runner.invoke(
        cli,
        args
        + [
            "add-entity",
            "--repo",
            "agent-memory",
            "--task",
            "entity merge test",
            "--name",
            "agent-memory",
            "--type",
            "OBJECT",
            "--description",
            "Short repo name",
        ],
    )
    target = runner.invoke(
        cli,
        args
        + [
            "add-entity",
            "--repo",
            "agent-memory",
            "--task",
            "entity merge test",
            "--name",
            "Neo4j Agent Memory",
            "--type",
            "OBJECT",
            "--description",
            "Canonical repo name",
        ],
    )
    other = runner.invoke(
        cli,
        args
        + [
            "add-entity",
            "--repo",
            "agent-memory",
            "--task",
            "entity merge test",
            "--name",
            "GLiNER",
            "--type",
            "OBJECT",
        ],
    )

    assert source.exit_code == 0, source.output
    assert target.exit_code == 0, target.output
    assert other.exit_code == 0, other.output

    source_id = json.loads(source.output)["entity"]["id"]
    target_id = json.loads(target.output)["entity"]["id"]
    other_id = json.loads(other.output)["entity"]["id"]

    alias = runner.invoke(
        cli,
        args + ["alias-entity", "--id", source_id, "--alias", "agent-memory-repo"],
    )
    assert alias.exit_code == 0, alias.output

    driver = GraphDatabase.driver(
        neo4j_connection_info["uri"],
        auth=(neo4j_connection_info["username"], neo4j_connection_info["password"]),
    )
    try:
        with driver.session() as session:
            session.run(
                """
                CREATE (m:Message {
                    id: $message_id,
                    role: 'user',
                    content: 'Merge entity test',
                    created_at: datetime()
                })
                """,
                {"message_id": str(uuid4())},
            )
            session.run(
                """
                MATCH (m:Message {content: 'Merge entity test'})
                MATCH (source:Entity {id: $source_id})
                MERGE (m)-[:MENTIONS]->(source)
                """,
                {"source_id": source_id},
            )
            session.run(
                queries.CREATE_ENTITY_RELATION_BY_ID,
                {
                    "source_id": source_id,
                    "target_id": other_id,
                    "relation_type": "USES",
                    "confidence": 0.9,
                },
            )

        merged = runner.invoke(
            cli,
            args + ["merge-entity", "--source-id", source_id, "--target-id", target_id],
        )
        assert merged.exit_code == 0, merged.output
        payload = json.loads(merged.output)
        assert payload["source"]["metadata"]["repo"] == "agent-memory"
        assert payload["source"]["metadata"]["task"] == "entity merge test"
        assert payload["target"]["id"] == target_id

        with driver.session() as session:
            source_state = session.run(
                "MATCH (e:Entity {id: $id}) RETURN e.merged_into AS merged_into",
                {"id": source_id},
            ).single()
            assert source_state is not None
            assert source_state["merged_into"] == target_id

            target_state = session.run(
                "MATCH (e:Entity {id: $id}) RETURN e.aliases AS aliases",
                {"id": target_id},
            ).single()
            assert target_state is not None
            aliases = target_state["aliases"] or []
            assert "agent-memory" in aliases
            assert "agent-memory-repo" in aliases

            mentions_count = session.run(
                """
                MATCH (:Message {content: 'Merge entity test'})-[:MENTIONS]->(e:Entity {id: $id})
                RETURN count(e) AS count
                """,
                {"id": target_id},
            ).single()["count"]
            assert mentions_count == 1

            related_count = session.run(
                """
                MATCH (:Entity {id: $target_id})-[r:RELATED_TO]->(:Entity {id: $other_id})
                RETURN count(r) AS count
                """,
                {"target_id": target_id, "other_id": other_id},
            ).single()["count"]
            assert related_count == 1

            lookup = session.run(queries.GET_ENTITY_BY_NAME, {"name": "agent-memory"}).single()
            assert lookup is not None
            assert dict(lookup["e"])["id"] == target_id
    finally:
        driver.close()


@pytest.mark.integration
def test_memory_cli_add_and_delete_message(neo4j_connection_info: dict[str, str]) -> None:
    runner = CliRunner()
    args = _memory_args(neo4j_connection_info)

    created = runner.invoke(
        cli,
        args
        + [
            "add-message",
            "--session-id",
            "coding/agent-memory/cli-test/run-1",
            "--role",
            "user",
            "Store this short-term message",
        ],
    )
    assert created.exit_code == 0, created.output
    message_id = json.loads(created.output)["message"]["id"]

    deleted = runner.invoke(
        cli,
        args + ["delete-message", "--id", message_id],
    )
    assert deleted.exit_code == 0, deleted.output
    assert json.loads(deleted.output)["deleted"] is True


@pytest.mark.integration
def test_memory_cli_search_facts_returns_active_match(
    neo4j_connection_info: dict[str, str],
) -> None:
    runner = CliRunner()
    args = _memory_args(neo4j_connection_info)

    created = runner.invoke(
        cli,
        args
        + [
            "add-fact",
            "--repo",
            "agent-memory",
            "--task",
            "cli test",
            "--subject",
            "CLI memory",
            "--predicate",
            "best_start",
            "--object-value",
            "real shell commands",
        ],
    )
    assert created.exit_code == 0, created.output

    searched = runner.invoke(
        cli,
        args
        + [
            "search",
            "--kind",
            "fact",
            "--query",
            "real shell commands",
            "--threshold",
            "0.0",
        ],
    )
    assert searched.exit_code == 0, searched.output
    payload = json.loads(searched.output)
    assert payload["count"] >= 1
    assert any(result["object"] == "real shell commands" for result in payload["results"])


@pytest.mark.integration
def test_memory_cli_get_context_returns_relevant_memory(
    neo4j_connection_info: dict[str, str],
) -> None:
    runner = CliRunner()
    args = _memory_args(neo4j_connection_info)
    session_id = "coding/agent-memory/cli-context/run-1"

    message = runner.invoke(
        cli,
        args
        + [
            "add-message",
            "--session-id",
            session_id,
            "--role",
            "user",
            "Use the CLI memory workflow for durable coding-agent memory.",
        ],
    )
    assert message.exit_code == 0, message.output

    fact = runner.invoke(
        cli,
        args
        + [
            "add-fact",
            "--repo",
            "agent-memory",
            "--task",
            "cli context",
            "--subject",
            "CLI memory workflow",
            "--predicate",
            "recommended_surface",
            "--object-value",
            "neo4j-agent-memory memory commands",
        ],
    )
    assert fact.exit_code == 0, fact.output

    context = runner.invoke(
        cli,
        args
        + [
            "get-context",
            "--session-id",
            session_id,
            "--query",
            "How should I operate durable coding-agent memory from the shell?",
            "--max-items",
            "5",
        ],
    )
    assert context.exit_code == 0, context.output
    payload = json.loads(context.output)
    assert payload["has_context"] is True
    assert "Use the CLI memory workflow for durable coding-agent memory." in payload["context"]
    assert "CLI memory workflow recommended_surface neo4j-agent-memory memory commands" in payload["context"]
