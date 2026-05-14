"""Session-wide fixtures for ``tests/cli``.

Spins up (or reuses) a dedicated Neo4j container on bolt://localhost:7688 with
its own volume, completely separate from the production agent-memory store on
:7687. Stamps the ``:_TestSentinel`` node so the safety guards in
``tests/conftest.py`` don't fire (we wipe between class sessions to keep tests
hermetic).

Why a separate container, not testcontainers?
- The CLI tests drive a binary that picks up DB params from env vars. Reusing a
  long-lived container keeps the suite under 30s instead of 5+ minutes for cold
  Neo4j startup per test.
- The docker-compose.cli-test.yml file pins port 7688 so an accidental
  ``NEO4J_URI=bolt://localhost:7687`` (the prod port) cannot reach this fixture.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from tests.cli.helpers import CLI, REPO_ROOT

CLI_TEST_URI = os.environ.get("CLI_TEST_NEO4J_URI", "bolt://localhost:7688")
CLI_TEST_USER = os.environ.get("CLI_TEST_NEO4J_USERNAME", "neo4j")
CLI_TEST_PASSWORD = os.environ.get(
    "CLI_TEST_NEO4J_PASSWORD", "cli-test-password"
)
CLI_TEST_CONTAINER = "neo4j-agent-memory-cli-test"
COMPOSE_FILE = REPO_ROOT / "docker-compose.cli-test.yml"


def _container_running() -> bool:
    if not shutil.which("docker"):
        return False
    res = subprocess.run(
        ["docker", "ps", "--filter", f"name={CLI_TEST_CONTAINER}",
         "--format", "{{.Names}}"],
        capture_output=True, text=True,
    )
    return CLI_TEST_CONTAINER in res.stdout


def _wait_for_neo4j(timeout: float = 90.0) -> None:
    """Poll cypher-shell until Neo4j accepts queries."""
    deadline = time.time() + timeout
    last_err = ""
    while time.time() < deadline:
        res = subprocess.run(
            ["docker", "exec", CLI_TEST_CONTAINER, "cypher-shell",
             "-u", CLI_TEST_USER, "-p", CLI_TEST_PASSWORD, "RETURN 1"],
            capture_output=True, text=True, timeout=10,
        )
        if res.returncode == 0:
            return
        last_err = res.stderr.strip()
        time.sleep(2)
    raise RuntimeError(
        f"Neo4j on {CLI_TEST_URI} did not become ready in {timeout}s. "
        f"Last error: {last_err}"
    )


def _exec_cypher(query: str) -> str:
    res = subprocess.run(
        ["docker", "exec", CLI_TEST_CONTAINER, "cypher-shell",
         "-u", CLI_TEST_USER, "-p", CLI_TEST_PASSWORD, "--format", "plain",
         query],
        capture_output=True, text=True, timeout=20,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"cypher-shell failed: {res.stderr.strip()}"
        )
    return res.stdout


@pytest.fixture(scope="session")
def cli_neo4j_container() -> dict[str, str]:
    """Ensure the dedicated CLI-test Neo4j container is up and reachable.

    Honors ``CLI_TEST_AUTOSTART`` (default: 1) — when 1 and the container is
    missing, this fixture brings it up via docker-compose. Set to 0 in CI if
    you prefer to manage the container externally.
    """
    autostart = os.environ.get("CLI_TEST_AUTOSTART", "1") == "1"

    if not _container_running():
        if not autostart:
            pytest.skip(
                f"CLI-test container '{CLI_TEST_CONTAINER}' not running and "
                f"CLI_TEST_AUTOSTART=0. Start with: "
                f"docker compose -f {COMPOSE_FILE.name} up -d"
            )
        if not COMPOSE_FILE.is_file():
            pytest.skip(f"{COMPOSE_FILE} missing")
        env = os.environ.copy()
        env.setdefault("NEO4J_CLI_TEST_PASSWORD", CLI_TEST_PASSWORD)
        subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"],
            check=True, env=env, capture_output=True,
        )

    _wait_for_neo4j()

    # Stamp the sentinel so any helper that wants to wipe knows this is safe.
    _exec_cypher(
        "MERGE (s:_TestSentinel {id: 'singleton'}) "
        "SET s.created_at = coalesce(s.created_at, datetime()), "
        "s.last_seen_at = datetime()"
    )

    return {
        "uri": CLI_TEST_URI,
        "username": CLI_TEST_USER,
        "password": CLI_TEST_PASSWORD,
        "container": CLI_TEST_CONTAINER,
    }


@pytest.fixture(scope="session")
def cli(cli_neo4j_container) -> CLI:
    """Session-wide CLI instance bound to the test container."""
    return CLI(
        uri=cli_neo4j_container["uri"],
        username=cli_neo4j_container["username"],
        password=cli_neo4j_container["password"],
    )


@pytest.fixture
def clean_cli_db(cli_neo4j_container) -> None:
    """Wipe everything except the sentinel before a test runs.

    Use sparingly — most tests should isolate via unique IDs/sessions instead
    of forcing a wipe, because wipes serialize the suite. Currently used by
    tests that assert on global counts (search results, list-candidates,
    stats).
    """
    _exec_cypher("MATCH (n) WHERE NOT n:_TestSentinel DETACH DELETE n")


@pytest.fixture(scope="session", autouse=True)
def _final_cleanup(cli_neo4j_container):
    """Wipe everything except the sentinel after the whole session ends."""
    yield
    try:
        _exec_cypher("MATCH (n) WHERE NOT n:_TestSentinel DETACH DELETE n")
    except Exception:
        pass
