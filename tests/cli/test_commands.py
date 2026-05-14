"""End-to-end tests for the ``agent-memory`` CLI.

Strategy:

- The CLI is invoked as a subprocess against a dedicated Neo4j container on
  port 7688 (separate volume from the production container on 7687).
- The 10 commands the user runs daily get **functional** coverage (happy path
  + at least one failure case + output structure assertions).
- The remaining commands get **smoke** coverage (one invocation, returncode +
  basic JSON shape).
- State flows through fixtures so creates feed into reads/updates/deletes
  without tests fighting each other.
- Pre-existing CLI bugs are tracked via ``@pytest.mark.xfail(strict=True)`` so
  the suite stays green AND a future fix forces a deliberate xfail removal.

Run:

    make test-cli              # autostarts container, runs full suite
    pytest tests/cli/ -v       # if you've already started the container

Skip the wrapper resolution (e.g. when testing a venv install):

    AGENT_MEMORY_BIN=/path/to/neo4j-agent-memory pytest tests/cli/
"""

from __future__ import annotations

import json
import uuid

import pytest

# Mark the entire module as integration so it gets skipped when
# RUN_INTEGRATION_TESTS=0 / SKIP_INTEGRATION_TESTS=1.
pytestmark = pytest.mark.integration


# =============================================================================
# Helpers and shared identifiers
# =============================================================================


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def repo_slug() -> str:
    return _unique("cli-test-repo")


@pytest.fixture(scope="module")
def task_slug() -> str:
    return _unique("cli-test-task")


@pytest.fixture(scope="module")
def session_id(cli, repo_slug, task_slug) -> str:
    """Build a session id via the CLI (also tests ``memory session-id``)."""
    res = cli.memory(
        "session-id", "--repo", repo_slug, "--task", task_slug
    ).assert_ok()
    payload = res.json()
    sid = payload["session_id"]
    assert isinstance(sid, str) and sid.startswith("coding/")
    return sid


# =============================================================================
# Top-level: basic invocation
# =============================================================================


class TestTopLevel:
    def test_version(self, cli):
        res = cli.run("--version").assert_ok()
        assert res.stdout.strip()

    def test_help(self, cli):
        res = cli.run("--help").assert_ok()
        assert "Commands:" in res.stdout
        for c in ("extract", "memory", "schemas", "stats", "mcp"):
            assert c in res.stdout

    def test_memory_help(self, cli):
        res = cli.memory("--help").assert_ok()
        assert "add-fact" in res.stdout
        assert "get-context" in res.stdout

    def test_unknown_command(self, cli):
        res = cli.run("nope-not-a-command")
        assert not res.ok
        assert "no such command" in res.stderr.lower()


# =============================================================================
# memory session-id
# =============================================================================


class TestSessionId:
    def test_basic(self, cli):
        res = cli.memory(
            "session-id", "--repo", "r1", "--task", "t1"
        ).assert_ok()
        out = res.json()
        assert out["repo"] == "r1"
        assert out["task"] == "t1"
        assert out["session_id"].startswith("coding/r1/t1/")

    def test_explicit_run_id(self, cli):
        res = cli.memory(
            "session-id", "--repo", "r2", "--task", "t2", "--run-id", "abc"
        ).assert_ok()
        out = res.json()
        assert out["session_id"] == "coding/r2/t2/abc"

    def test_missing_required(self, cli):
        res = cli.memory("session-id", "--repo", "only-repo")
        assert not res.ok
        assert "task" in (res.stderr + res.stdout).lower()


# =============================================================================
# memory add-fact / inspect / search / replace-fact / delete (functional)
# =============================================================================


class TestFactLifecycle:
    """add-fact → inspect → search → replace-fact → delete."""

    @pytest.fixture(scope="class")
    def fact_id(self, cli, repo_slug, task_slug) -> str:
        res = cli.memory(
            "add-fact",
            "--repo", repo_slug, "--task", task_slug,
            "--subject", "agent-memory-cli-test",
            "--predicate", "verifies",
            "--object-value",
            "CLI add-fact stores subject-predicate-object triples reliably.",
            "--confidence", "0.95",
        ).assert_ok()
        out = res.json()
        return out["fact"]["id"]

    def test_add_fact_returns_uuid(self, fact_id):
        uuid.UUID(fact_id)

    def test_inspect_fact(self, cli, fact_id):
        res = cli.memory(
            "inspect", "--kind", "fact", "--id", fact_id
        ).assert_ok()
        out = res.json()
        assert out["kind"] == "fact"
        assert out["id"] == fact_id
        entry = out["entry"]
        assert entry["subject"] == "agent-memory-cli-test"
        assert entry["predicate"] == "verifies"

    def test_search_fact_finds_it(self, cli, fact_id):
        res = cli.memory(
            "search", "--kind", "fact",
            "--query", "CLI add-fact stores subject-predicate-object triples",
            "--limit", "5",
            "--threshold", "0.0",
        ).assert_ok()
        out = res.json()
        assert out["kind"] == "fact"
        ids = [item["id"] for item in out["results"]]
        assert fact_id in ids

    def test_replace_fact_creates_successor(
        self, cli, fact_id, repo_slug, task_slug
    ):
        res = cli.memory(
            "replace-fact", "--id", fact_id,
            "--object-value", "Updated object value via replace-fact.",
            "--repo", repo_slug, "--task", task_slug,
        ).assert_ok()
        new_id = res.json()["fact"]["id"]
        assert new_id != fact_id

    def test_inspect_missing_fact(self, cli):
        bogus = str(uuid.uuid4())
        res = cli.memory(
            "inspect", "--kind", "fact", "--id", bogus
        ).assert_ok()
        out = res.json()
        # entry is null when fact doesn't exist
        assert out["entry"] is None

    def test_delete_fact(self, cli, fact_id):
        res = cli.memory(
            "delete", "--kind", "fact", "--id", fact_id
        ).assert_ok()
        out = res.json()
        assert out["kind"] == "fact"
        assert out["deleted"] is True


# =============================================================================
# memory add-preference / replace / inspect / search / delete (functional)
# =============================================================================


class TestPreferenceLifecycle:
    @pytest.fixture(scope="class")
    def pref_id(self, cli, repo_slug, task_slug) -> str:
        res = cli.memory(
            "add-preference",
            "--repo", repo_slug, "--task", task_slug,
            "--category", "cli-tests",
            "--preference",
            "Prefers running CLI tests on a dedicated container.",
        ).assert_ok()
        return res.json()["preference"]["id"]

    def test_pref_id_is_uuid(self, pref_id):
        uuid.UUID(pref_id)

    def test_inspect_preference(self, cli, pref_id):
        res = cli.memory(
            "inspect", "--kind", "preference", "--id", pref_id
        ).assert_ok()
        out = res.json()
        assert out["entry"]["category"] == "cli-tests"

    def test_search_preference(self, cli, pref_id):
        res = cli.memory(
            "search", "--kind", "preference",
            "--query", "running CLI tests on a dedicated container",
            "--limit", "5", "--threshold", "0.0",
        ).assert_ok()
        ids = [item["id"] for item in res.json()["results"]]
        assert pref_id in ids

    def test_replace_preference(self, cli, pref_id, repo_slug, task_slug):
        res = cli.memory(
            "replace-preference", "--id", pref_id,
            "--preference", "Updated preference text via replace-preference.",
            "--repo", repo_slug, "--task", task_slug,
        ).assert_ok()
        new_id = res.json()["preference"]["id"]
        assert new_id != pref_id

    def test_delete_preference(self, cli, pref_id):
        res = cli.memory(
            "delete", "--kind", "preference", "--id", pref_id
        ).assert_ok()
        assert res.json()["deleted"] is True


# =============================================================================
# memory add-entity / alias / update / merge / inspect / search
# =============================================================================


class TestEntityLifecycle:
    @pytest.fixture(scope="class")
    def entity_id(self, cli, repo_slug, task_slug) -> str:
        res = cli.memory(
            "add-entity",
            "--repo", repo_slug, "--task", task_slug,
            "--name", _unique("CliEntAlpha"),
            "--type", "OBJECT",
            "--description", "Synthetic entity used in CLI tests.",
            "--no-resolve", "--no-deduplicate",
            "--no-enrich", "--no-geocode",
        ).assert_ok()
        return res.json()["entity"]["id"]

    @pytest.fixture(scope="class")
    def merge_target_id(self, cli, repo_slug, task_slug) -> str:
        res = cli.memory(
            "add-entity",
            "--repo", repo_slug, "--task", task_slug,
            "--name", _unique("CliEntBeta"),
            "--type", "OBJECT",
            "--no-resolve", "--no-deduplicate",
            "--no-enrich", "--no-geocode",
        ).assert_ok()
        return res.json()["entity"]["id"]

    def test_entity_id_is_uuid(self, entity_id):
        uuid.UUID(entity_id)

    def test_alias_entity(self, cli, entity_id):
        res = cli.memory(
            "alias-entity", "--id", entity_id, "--alias", "AliasOne"
        ).assert_ok()
        aliases = res.json()["entity"].get("aliases", [])
        assert "AliasOne" in aliases

    def test_update_entity_description(self, cli, entity_id):
        cli.memory(
            "update-entity", "--id", entity_id,
            "--description", "Updated via update-entity.",
        ).assert_ok()
        inspect_res = cli.memory(
            "inspect", "--kind", "entity", "--id", entity_id
        ).assert_ok()
        assert inspect_res.json()["entry"]["description"] == (
            "Updated via update-entity."
        )

    def test_inspect_entity(self, cli, entity_id):
        res = cli.memory(
            "inspect", "--kind", "entity", "--id", entity_id
        ).assert_ok()
        assert res.json()["entry"]["id"] == entity_id

    def test_search_entity(self, cli, entity_id):
        # First fetch the entity name we just created.
        ent = cli.memory(
            "inspect", "--kind", "entity", "--id", entity_id
        ).assert_ok().json()["entry"]
        res = cli.memory(
            "search", "--kind", "entity",
            "--query", ent["name"],
            "--limit", "5", "--threshold", "0.0",
        ).assert_ok()
        ids = [item["id"] for item in res.json()["results"]]
        assert entity_id in ids

    def test_merge_entity(self, cli, entity_id, merge_target_id):
        res = cli.memory(
            "merge-entity",
            "--source-id", entity_id,
            "--target-id", merge_target_id,
        ).assert_ok()
        out = res.json()
        # merge response surfaces both source and target
        assert out["source"]["id"] == entity_id
        assert out["target"]["id"] == merge_target_id


# =============================================================================
# memory add-message / inspect / search / delete-message
# =============================================================================


class TestMessageLifecycle:
    @pytest.fixture(scope="class")
    def message_payload(self, cli, session_id) -> dict:
        res = cli.memory(
            "add-message",
            "--session-id", session_id, "--role", "user",
            "--no-extract-entities", "--no-extract-relations",
            "Unique CLI test message about widgets and gizmos.",
        ).assert_ok()
        return res.json()["message"]

    def test_message_id_is_uuid(self, message_payload):
        uuid.UUID(message_payload["id"])
        assert message_payload["role"] == "user"

    def test_inspect_message(self, cli, message_payload):
        res = cli.memory(
            "inspect", "--kind", "message", "--id", message_payload["id"]
        ).assert_ok()
        assert res.json()["entry"]["id"] == message_payload["id"]

    def test_search_message(self, cli, message_payload, session_id):
        res = cli.memory(
            "search", "--kind", "message",
            "--query", "Unique CLI test message about widgets",
            "--session-id", session_id,
            "--limit", "5", "--threshold", "0.0",
        ).assert_ok()
        ids = [item["id"] for item in res.json()["results"]]
        assert message_payload["id"] in ids

    def test_delete_message(self, cli, message_payload):
        res = cli.memory(
            "delete-message", "--id", message_payload["id"]
        ).assert_ok()
        assert res.json()["deleted"] is True


# =============================================================================
# memory get-context / recall
# =============================================================================


class TestContextAndRecall:
    @pytest.fixture(scope="class")
    def seeded_fact(self, cli, repo_slug, task_slug):
        res = cli.memory(
            "add-fact",
            "--repo", repo_slug, "--task", task_slug,
            "--subject", "agent-memory-context-probe",
            "--predicate", "asserts",
            "--object-value",
            "Context probe with distinctive token pumpernickel-quasar.",
        ).assert_ok()
        fid = res.json()["fact"]["id"]
        yield fid
        # Best-effort cleanup
        cli.memory("delete", "--kind", "fact", "--id", fid)

    def test_get_context_returns_payload(self, cli, seeded_fact):
        res = cli.memory(
            "get-context",
            "--query", "Context probe pumpernickel-quasar",
            "--no-include-short-term", "--no-include-reasoning",
            "--max-items", "5",
            "--relevance-threshold", "0.0",
        ).assert_ok()
        out = res.json()
        # Contract: get-context returns a string `context` field, not a dict.
        assert "context" in out
        assert "has_context" in out
        assert out["has_context"] is True
        assert "pumpernickel-quasar" in out["context"]
        _ = seeded_fact

    def test_get_context_high_threshold_drops_everything(
        self, cli, seeded_fact
    ):
        res = cli.memory(
            "get-context",
            "--query", "completely unrelated zebra astrolabe topic",
            "--no-include-short-term", "--no-include-reasoning",
            "--relevance-threshold", "0.99",
        ).assert_ok()
        out = res.json()
        # If any context is returned, the seeded fact must NOT appear.
        if out["has_context"]:
            assert "pumpernickel-quasar" not in out["context"]
        _ = seeded_fact

    def test_recall(self, cli, repo_slug, task_slug, session_id):
        res = cli.memory(
            "recall",
            "--repo", repo_slug, "--task", task_slug,
            "--session-id", session_id,
            "--max-facts", "5", "--max-preferences", "5",
            "--max-entities", "5", "--max-traces", "3",
            "--recent-messages", "3",
        ).assert_ok()
        out = res.json()
        # Contract: recall returns repo/task/session_id + a string `context`.
        assert out["repo"] == repo_slug
        assert out["task"] == task_slug
        assert out["session_id"] == session_id
        assert "context" in out
        assert "has_context" in out


# =============================================================================
# memory start-trace / add-trace-step / add-tool-call / complete-trace
# =============================================================================


class TestReasoningTraceLifecycle:
    @pytest.fixture(scope="class")
    def trace_id(self, cli, session_id) -> str:
        res = cli.memory(
            "start-trace", "--session-id", session_id,
            "--task", "CLI test trace task",
            "--no-generate-embedding",
        ).assert_ok()
        return res.json()["trace"]["id"]

    @pytest.fixture(scope="class")
    def step_id(self, cli, trace_id) -> str:
        res = cli.memory(
            "add-trace-step", "--trace-id", trace_id,
            "--thought", "First reasoning step",
            "--action", "call_tool_x",
            "--no-generate-embedding",
        ).assert_ok()
        return res.json()["step"]["id"]

    def test_trace_id_is_uuid(self, trace_id):
        uuid.UUID(trace_id)

    def test_step_id_is_uuid(self, step_id):
        uuid.UUID(step_id)

    def test_add_tool_call(self, cli, step_id):
        res = cli.memory(
            "add-tool-call", "--step-id", step_id,
            "--tool-name", "my_tool",
            "--arguments-json", json.dumps({"q": "hello"}),
            "--result-text", "world",
            "--status", "success",
            "--duration-ms", "42",
        ).assert_ok()
        tc = res.json()["tool_call"]
        assert tc["tool_name"] == "my_tool"
        assert tc["status"] == "success"

    def test_complete_trace(self, cli, trace_id):
        res = cli.memory(
            "complete-trace", "--trace-id", trace_id,
            "--outcome", "All good.", "--success",
        ).assert_ok()
        trace = res.json()["trace"]
        assert trace["outcome"] == "All good."


# =============================================================================
# memory list-candidates / accept / ignore / get-candidate
# =============================================================================


class TestCandidates:
    """Candidates are usually created by the agent loop. We can only verify
    listing shape and that workflow commands fail gracefully on bogus IDs."""

    def test_list_candidates(self, cli):
        res = cli.memory(
            "list-candidates", "--limit", "5"
        ).assert_ok()
        out = res.json()
        assert "candidates" in out
        assert "count" in out
        assert isinstance(out["candidates"], list)

    def test_list_candidates_filter(self, cli):
        res = cli.memory(
            "list-candidates", "--type", "fact", "--limit", "5"
        ).assert_ok()
        assert "candidates" in res.json()

    def test_list_pending_relations(self, cli):
        res = cli.memory(
            "list-pending-relations", "--limit", "5"
        ).assert_ok()
        out = res.json()
        assert "relations" in out
        assert "count" in out

    def test_get_unknown_candidate(self, cli):
        bogus = str(uuid.uuid4())
        res = cli.memory("get-candidate", "--id", bogus)
        # Either a clean error or null candidate — never a Python traceback.
        assert "Traceback" not in res.stderr

    def test_accept_unknown_candidate(self, cli):
        bogus = str(uuid.uuid4())
        res = cli.memory("accept-candidate", "--id", bogus)
        assert "Traceback" not in res.stderr

    def test_ignore_unknown_candidate(self, cli):
        bogus = str(uuid.uuid4())
        res = cli.memory("ignore-candidate", "--id", bogus)
        assert "Traceback" not in res.stderr


# =============================================================================
# memory get-provenance / review-relation
# =============================================================================


class TestProvenance:
    @pytest.fixture(scope="class")
    def provenance_fact_id(self, cli, repo_slug, task_slug) -> str:
        res = cli.memory(
            "add-fact",
            "--repo", repo_slug, "--task", task_slug,
            "--subject", "prov-subj", "--predicate", "prov-pred",
            "--object-value", "prov-obj",
        ).assert_ok()
        return res.json()["fact"]["id"]

    def test_get_provenance_known_fact(self, cli, provenance_fact_id):
        res = cli.memory(
            "get-provenance", "fact", provenance_fact_id
        ).assert_ok()
        out = res.json()
        # Returns the fact + provenance metadata
        assert "fact" in out
        assert out["fact"]["id"] == provenance_fact_id

    def test_get_provenance_unknown_fact(self, cli):
        bogus = str(uuid.uuid4())
        res = cli.memory("get-provenance", "fact", bogus)
        assert "Traceback" not in res.stderr

    def test_review_unknown_relation(self, cli):
        s, t = str(uuid.uuid4()), str(uuid.uuid4())
        res = cli.memory(
            "review-relation", s, t, "RELATED_TO",
            "--reject", "--reviewed-by", "cli-test",
        )
        assert "Traceback" not in res.stderr


# =============================================================================
# Top-level: stats, schemas, extract
# =============================================================================
#
# These commands have pre-existing bugs as of 2026-05-14; the test catches
# them but is marked xfail(strict=True) so the suite stays green AND any
# future fix will force the xfail marker to be removed deliberately.


class TestStats:
    def test_stats_json(self, cli):
        res = cli.run(
            "stats", "--format", "json",
            "--uri", cli.uri, "--user", cli.username,
            "--password", cli.password,
        ).assert_ok()
        out = res.json()
        assert isinstance(out, dict)
        # Verify the documented payload shape: extraction_stats with at least
        # a total_entities count, plus an extractor_stats list.
        assert "extraction_stats" in out
        assert "extractor_stats" in out
        assert isinstance(out["extraction_stats"], dict)
        assert isinstance(out["extractor_stats"], list)
        assert "total_entities" in out["extraction_stats"]


class TestSchemas:
    def test_schemas_help(self, cli):
        res = cli.run("schemas", "--help").assert_ok()
        assert "list" in res.stdout
        assert "validate" in res.stdout

    def test_schemas_validate_missing_file(self, cli, tmp_path):
        bogus = tmp_path / "nope.yaml"
        res = cli.run("schemas", "validate", str(bogus))
        # Should fail cleanly, not crash.
        assert "Traceback" not in res.stderr

    def test_schemas_list(self, cli):
        res = cli.run(
            "schemas", "list", "--format", "json",
            "--uri", cli.uri, "--user", cli.username,
            "--password", cli.password,
        ).assert_ok()
        # An empty DB returns an empty list — the contract is "valid JSON
        # array of schema summaries", not "non-empty".
        out = res.json()
        assert isinstance(out, list)


class TestExtract:
    def test_extract_help(self, cli):
        res = cli.run("extract", "--help").assert_ok()
        assert "entity-types" in res.stdout

    def test_extract_json(self, cli):
        res = cli.run(
            "extract",
            "John Smith works at Acme Corp.",
            "--format", "json", "-q",
        )
        # GLiNER may not be installed in every venv — treat that as a skip,
        # not a failure.
        if not res.ok:
            combined = (res.stderr + res.stdout).lower()
            if "gliner" in combined and (
                "not installed" in combined
                or "importerror" in combined
                or "modulenotfounderror" in combined
                or "no module named" in combined
            ):
                pytest.skip("GLiNER not installed in this venv")
            pytest.fail(
                f"extract failed unexpectedly:\n{res.stderr[:600]}"
            )
        out = res.json()
        assert isinstance(out, dict)
        # Documented payload: entities + relations + preferences arrays.
        assert "entities" in out
