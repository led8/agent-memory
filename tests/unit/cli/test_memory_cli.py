"""Unit tests for the memory CLI surface."""

from __future__ import annotations

import importlib
import json

from click.testing import CliRunner

from neo4j_agent_memory.cli.main import cli


cli_main = importlib.import_module("neo4j_agent_memory.cli.main")


class FakeMemoryCliService:
    """Small async fake for CLI dispatch tests."""

    last_connection = None
    last_call = None

    def __init__(self, connection):
        FakeMemoryCliService.last_connection = connection

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def add_fact(self, **kwargs):
        FakeMemoryCliService.last_call = ("add_fact", kwargs)
        return {"fact": {"id": "fact-1", **kwargs}}

    async def update_entity(self, **kwargs):
        FakeMemoryCliService.last_call = ("update_entity", kwargs)
        return {"entity": {"id": "entity-1", **kwargs}}

    async def alias_entity(self, **kwargs):
        FakeMemoryCliService.last_call = ("alias_entity", kwargs)
        return {"entity": {"id": "entity-1"}, "alias": kwargs["alias"]}

    async def recall(self, **kwargs):
        FakeMemoryCliService.last_call = ("recall", kwargs)
        return {
            "repo": kwargs["repo"],
            "task": kwargs["task"],
            "session_id": kwargs["session_id"],
            "query": kwargs["query"] or kwargs["task"],
            "has_context": True,
            "context": "## Task Frame\n- Repo: agent-memory",
        }


def test_memory_session_id_outputs_json() -> None:
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["memory", "session-id", "--repo", "agent-memory", "--task", "debug extraction"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["repo"] == "agent-memory"
    assert payload["task"] == "debug extraction"
    assert payload["session_id"].startswith("coding/agent-memory/debug-extraction/")


def test_memory_add_fact_dispatches_to_service(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(cli_main, "MemoryCliService", FakeMemoryCliService)

    result = runner.invoke(
        cli,
        [
            "memory",
            "--uri",
            "bolt://localhost:7687",
            "--user",
            "neo4j",
            "--password",
            "secret",
            "--local-embedder",
            "add-fact",
            "--repo",
            "agent-memory",
            "--task",
            "cli smoke",
            "--subject",
            "CLI memory",
            "--predicate",
            "best_start",
            "--object-value",
            "real shell commands",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["fact"]["id"] == "fact-1"
    assert FakeMemoryCliService.last_connection.password == "secret"
    assert FakeMemoryCliService.last_connection.local_embedder is True
    assert FakeMemoryCliService.last_call == (
        "add_fact",
        {
            "repo": "agent-memory",
            "task": "cli smoke",
            "subject": "CLI memory",
            "predicate": "best_start",
            "obj": "real shell commands",
            "scope_kind": "repo",
            "confidence": 1.0,
            "metadata": None,
            "generate_embedding": True,
        },
    )


def test_memory_replace_fact_requires_override_field() -> None:
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "memory",
            "--password",
            "secret",
            "replace-fact",
            "--id",
            "fact-1",
        ],
    )

    assert result.exit_code != 0
    assert "Provide at least one" in result.output


def test_memory_add_tool_call_rejects_two_result_formats() -> None:
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "memory",
            "--password",
            "secret",
            "add-tool-call",
            "--step-id",
            "550e8400-e29b-41d4-a716-446655440000",
            "--tool-name",
            "rg",
            "--arguments-json",
            "{}",
            "--result-json",
            "{}",
            "--result-text",
            "duplicate",
        ],
    )

    assert result.exit_code != 0
    assert "either --result-json or --result-text" in result.output


def test_memory_update_entity_dispatches_to_service(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(cli_main, "MemoryCliService", FakeMemoryCliService)

    result = runner.invoke(
        cli,
        [
            "memory",
            "--password",
            "secret",
            "update-entity",
            "--id",
            "entity-1",
            "--name",
            "Neo4j Agent Memory",
            "--metadata-json",
            '{"scope_kind":"repo"}',
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["entity"]["id"] == "entity-1"
    assert FakeMemoryCliService.last_call == (
        "update_entity",
        {
            "entity_id": "entity-1",
            "name": "Neo4j Agent Memory",
            "canonical_name": None,
            "description": None,
            "metadata_updates": {"scope_kind": "repo"},
        },
    )


def test_memory_alias_entity_dispatches_to_service(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(cli_main, "MemoryCliService", FakeMemoryCliService)

    result = runner.invoke(
        cli,
        [
            "memory",
            "--password",
            "secret",
            "alias-entity",
            "--id",
            "entity-1",
            "--alias",
            "agent-memory",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["alias"] == "agent-memory"
    assert FakeMemoryCliService.last_call == (
        "alias_entity",
        {
            "entity_id": "entity-1",
            "alias": "agent-memory",
        },
    )


def test_memory_merge_entity_rejects_same_source_and_target() -> None:
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "memory",
            "--password",
            "secret",
            "merge-entity",
            "--source-id",
            "entity-1",
            "--target-id",
            "entity-1",
        ],
    )

    assert result.exit_code != 0
    assert "different values" in result.output


def test_memory_recall_dispatches_to_service(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(cli_main, "MemoryCliService", FakeMemoryCliService)

    result = runner.invoke(
        cli,
        [
            "memory",
            "--password",
            "secret",
            "recall",
            "--repo",
            "agent-memory",
            "--task",
            "debug extraction",
            "--session-id",
            "coding/agent-memory/debug-extraction/test",
            "--query",
            "How should I debug extraction?",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["has_context"] is True
    assert FakeMemoryCliService.last_call == (
        "recall",
        {
            "repo": "agent-memory",
            "task": "debug extraction",
            "session_id": "coding/agent-memory/debug-extraction/test",
            "query": "How should I debug extraction?",
            "recent_messages": 6,
            "max_preferences": 5,
            "max_facts": 5,
            "max_entities": 5,
            "max_traces": 3,
        },
    )
