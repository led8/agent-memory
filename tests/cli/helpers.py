"""Subprocess helpers for driving the ``agent-memory`` CLI in tests.

Tests in this package treat the CLI as a black box: spawn the user-facing
wrapper (``~/.local/bin/agent-memory``) as a subprocess, capture stdout/stderr,
parse JSON, and assert on the result. This catches:

- argument parsing regressions (wrong flag types, missing required args)
- wrapper-level bugs (env loading, AGENT_MEMORY_HOME resolution)
- output contract drift (commands stop returning JSON, key renames)

The wrapper is preferred over the in-package ``neo4j-agent-memory`` entry point
because the wrapper is what the user actually runs day-to-day.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_wrapper() -> Path:
    """Return the path to the user-facing wrapper binary."""
    explicit = os.environ.get("AGENT_MEMORY_BIN")
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return p
    home_local = Path.home() / ".local" / "bin" / "agent-memory"
    if home_local.is_file() and os.access(home_local, os.X_OK):
        return home_local
    on_path = shutil.which("agent-memory")
    if on_path:
        return Path(on_path)
    raise FileNotFoundError(
        "Could not locate the 'agent-memory' wrapper. Install it to "
        "~/.local/bin/agent-memory or set AGENT_MEMORY_BIN."
    )


@dataclass
class CLIResult:
    """Captured outcome of a CLI invocation."""

    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def json(self) -> Any:
        """Parse ``stdout`` as JSON, raising AssertionError on bad payloads."""
        try:
            return json.loads(self.stdout)
        except json.JSONDecodeError as e:
            raise AssertionError(
                f"CLI did not return JSON.\n"
                f"  args:  {' '.join(self.args)}\n"
                f"  rc:    {self.returncode}\n"
                f"  err:   {self.stderr.strip()[:400]}\n"
                f"  out:   {self.stdout[:400]!r}\n"
                f"  parse: {e}"
            ) from e

    def assert_ok(self) -> CLIResult:
        if not self.ok:
            raise AssertionError(
                f"CLI failed (rc={self.returncode}):\n"
                f"  args:   {' '.join(self.args)}\n"
                f"  stdout: {self.stdout[:600]}\n"
                f"  stderr: {self.stderr[:600]}"
            )
        return self


class CLI:
    """Callable wrapper that runs the ``agent-memory`` CLI against a target DB.

    The instance is bound to one Neo4j connection (URI/user/password) at
    construction; every invocation injects those as env vars. The wrapper
    auto-detects ``--local-embedder`` so we don't need network access for tests.
    """

    def __init__(
        self,
        *,
        uri: str,
        username: str,
        password: str,
        wrapper: Path | None = None,
        repo_home: Path | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.uri = uri
        self.username = username
        self.password = password
        self.wrapper = wrapper or _resolve_wrapper()
        self.repo_home = repo_home or REPO_ROOT
        self.timeout = timeout

    def run(
        self,
        *args: str,
        stdin: str | None = None,
        extra_env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> CLIResult:
        env = os.environ.copy()
        env.update(
            {
                "AGENT_MEMORY_HOME": str(self.repo_home),
                "NEO4J_URI": self.uri,
                "NEO4J_USERNAME": self.username,
                "NEO4J_PASSWORD": self.password,
            }
        )
        if extra_env:
            env.update(extra_env)

        proc = subprocess.run(
            [str(self.wrapper), *args],
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout or self.timeout,
        )
        return CLIResult(
            args=tuple(args),
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

    def memory(self, *args: str, **kwargs: Any) -> CLIResult:
        """Shortcut: ``cli.memory("add-fact", ...)``.

        Auto-injects ``--uri/--user/--password`` because the wrapper sources
        ``.env`` which would otherwise clobber connection env vars with the
        production credentials.
        """
        return self.run(
            "memory",
            "--uri", self.uri,
            "--user", self.username,
            "--password", self.password,
            *args,
            **kwargs,
        )
