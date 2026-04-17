"""CLI commands for Neo4j Agent Memory.

Usage:
    neo4j-agent-memory extract "John works at Acme Corp"
    echo "John works at Acme Corp" | neo4j-agent-memory extract -
    neo4j-agent-memory extract --file document.txt --format json
    neo4j-agent-memory schemas list
    neo4j-agent-memory stats
    neo4j-agent-memory memory session-id --repo agent-memory --task "debug extraction"
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from neo4j_agent_memory.cli.memory_ops import MemoryCliConnection, MemoryCliService
from neo4j_agent_memory.memory.reasoning import ToolCallStatus
from neo4j_agent_memory.extraction import (
    ExtractionResult,
    ExtractorBuilder,
)
from neo4j_agent_memory.schema import (
    EntitySchemaConfig,
    EntityTypeConfig,
    load_schema_from_file,
)

console = Console()
error_console = Console(stderr=True)


def run_async(coro):
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already in an async context — create a new loop in a thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


def echo_json(payload: Any) -> None:
    """Emit a JSON payload to stdout."""
    click.echo(json.dumps(payload, indent=2, default=str))


def parse_json_option(raw: str | None, option_name: str) -> Any | None:
    """Parse a JSON CLI option."""
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"{option_name} must be valid JSON: {exc}") from exc


def run_memory_operation(
    connection: MemoryCliConnection,
    operation,
) -> Any:
    """Run one memory CLI operation with a connected service."""

    async def runner():
        async with MemoryCliService(connection) as service:
            return await operation(service)

    try:
        return run_async(runner())
    except click.ClickException:
        raise
    except Exception as exc:  # pragma: no cover - surfaced as CLI error
        raise click.ClickException(str(exc)) from exc


def format_entities_table(result: ExtractionResult) -> Table:
    """Format extraction result as a Rich table."""
    table = Table(title="Extracted Entities")
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Confidence", style="yellow", justify="right")
    table.add_column("Attributes", style="dim")

    for entity in result.entities:
        attrs = entity.attributes or {}
        attrs_str = json.dumps(attrs) if attrs else ""
        table.add_row(
            entity.type,
            entity.name,
            f"{entity.confidence:.2f}" if entity.confidence else "N/A",
            attrs_str[:50] + "..." if len(attrs_str) > 50 else attrs_str,
        )

    return table


def format_relations_table(result: ExtractionResult) -> Table:
    """Format extraction relations as a Rich table."""
    table = Table(title="Extracted Relations")
    table.add_column("Source", style="cyan")
    table.add_column("Relation", style="magenta")
    table.add_column("Target", style="green")
    table.add_column("Confidence", style="yellow", justify="right")

    for rel in result.relations:
        table.add_row(
            rel.source,
            rel.relation_type,
            rel.target,
            f"{rel.confidence:.2f}" if rel.confidence else "N/A",
        )

    return table


def format_preferences_table(result: ExtractionResult) -> Table:
    """Format extraction preferences as a Rich table."""
    table = Table(title="Extracted Preferences")
    table.add_column("Category", style="cyan")
    table.add_column("Preference", style="green")
    table.add_column("Confidence", style="yellow", justify="right")

    for pref in result.preferences:
        table.add_row(
            pref.category,
            pref.preference,
            f"{pref.confidence:.2f}" if pref.confidence else "N/A",
        )

    return table


def result_to_dict(result: ExtractionResult) -> dict[str, Any]:
    """Convert extraction result to a dictionary for JSON output."""
    return {
        "entities": [
            {
                "type": e.type,
                "name": e.name,
                "confidence": e.confidence,
                "attributes": e.attributes,
            }
            for e in result.entities
        ],
        "relations": [
            {
                "source": r.source,
                "relation_type": r.relation_type,
                "target": r.target,
                "confidence": r.confidence,
                "attributes": r.attributes if hasattr(r, "attributes") else {},
            }
            for r in result.relations
        ],
        "preferences": [
            {
                "category": p.category,
                "preference": p.preference,
                "confidence": p.confidence,
            }
            for p in result.preferences
        ],
        "source_text": result.source_text,
    }


@click.group()
@click.version_option()
def cli():
    """Neo4j Agent Memory - Entity Extraction CLI.

    Extract entities, relations, and preferences from text using
    GLiNER and LLM-based extractors.
    """
    pass


@cli.command()
@click.argument("text", required=False)
@click.option(
    "-f",
    "--file",
    type=click.Path(exists=True, path_type=Path),
    help="Read text from a file instead of argument.",
)
@click.option(
    "--format",
    "-o",
    type=click.Choice(["table", "json", "jsonl"]),
    default="table",
    help="Output format (default: table).",
)
@click.option(
    "--schema",
    type=click.Path(exists=True, path_type=Path),
    help="Path to a schema YAML file.",
)
@click.option(
    "--entity-types",
    "-e",
    multiple=True,
    help="Entity types to extract (can be specified multiple times).",
)
@click.option(
    "--extractor",
    type=click.Choice(["gliner", "llm", "hybrid"]),
    default="gliner",
    help="Extractor to use (default: gliner).",
)
@click.option(
    "--model",
    default=None,
    help="Model name for GLiNER or LLM extractor.",
)
@click.option(
    "--relations/--no-relations",
    default=True,
    help="Extract relations between entities.",
)
@click.option(
    "--preferences/--no-preferences",
    default=False,
    help="Extract preferences/sentiments.",
)
@click.option(
    "--confidence-threshold",
    type=float,
    default=0.5,
    help="Minimum confidence threshold (default: 0.5).",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress progress output.",
)
def extract(
    text: str | None,
    file: Path | None,
    format: str,
    schema: Path | None,
    entity_types: tuple[str, ...],
    extractor: str,
    model: str | None,
    relations: bool,
    preferences: bool,
    confidence_threshold: float,
    quiet: bool,
):
    """Extract entities from text.

    TEXT can be provided as an argument, from a file (--file), or piped via stdin.
    Use "-" as TEXT to read from stdin.

    Examples:

        neo4j-agent-memory extract "John works at Acme Corp"

        echo "John works at Acme Corp" | neo4j-agent-memory extract -

        neo4j-agent-memory extract --file document.txt --format json

        neo4j-agent-memory extract "..." --entity-types Person --entity-types Organization
    """
    # Get text from argument, file, or stdin
    if text == "-" or (text is None and file is None and not sys.stdin.isatty()):
        text = sys.stdin.read()
    elif file:
        text = file.read_text()
    elif text is None:
        error_console.print("[red]Error:[/red] No text provided. Use --help for usage.")
        sys.exit(1)

    if not text.strip():
        error_console.print("[red]Error:[/red] Empty text provided.")
        sys.exit(1)

    async def do_extract():
        # Build the extractor
        builder = ExtractorBuilder()

        if schema:
            schema_config = load_schema_from_file(schema)
            builder = builder.with_schema(schema_config)
        elif entity_types:
            # Create a simple schema with the specified types
            schema_config = EntitySchemaConfig(
                name="cli_schema",
                entity_types=[EntityTypeConfig(name=et) for et in entity_types],
            )
            builder = builder.with_schema(schema_config)

        # Configure extractor type
        if extractor == "gliner":
            if model:
                builder = builder.with_gliner(model_name=model)
            else:
                builder = builder.with_gliner()
        elif extractor == "llm":
            if model:
                builder = builder.with_llm(model=model)
            else:
                builder = builder.with_llm()
        elif extractor == "hybrid":
            builder = builder.with_gliner()
            if model:
                builder = builder.with_llm(model=model)
            else:
                builder = builder.with_llm()

        # Set confidence threshold
        builder = builder.with_confidence_threshold(confidence_threshold)

        ext = builder.build()

        # Run extraction
        result = await ext.extract(
            text,
            extract_relations=relations,
            extract_preferences=preferences,
        )

        return result

    # Run with progress indicator
    if quiet or format in ("json", "jsonl"):
        result = run_async(do_extract())
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("Extracting entities...", total=None)
            result = run_async(do_extract())

    # Output results
    if format == "json":
        click.echo(json.dumps(result_to_dict(result), indent=2))
    elif format == "jsonl":
        # Output each entity as a separate JSON line
        for entity in result.entities:
            click.echo(
                json.dumps(
                    {
                        "type": "entity",
                        "data": {
                            "type": entity.type,
                            "name": entity.name,
                            "confidence": entity.confidence,
                            "attributes": entity.attributes,
                        },
                    }
                )
            )
        for rel in result.relations:
            click.echo(
                json.dumps(
                    {
                        "type": "relation",
                        "data": {
                            "source": rel.source,
                            "relation_type": rel.relation_type,
                            "target": rel.target,
                            "confidence": rel.confidence,
                        },
                    }
                )
            )
        for pref in result.preferences:
            click.echo(
                json.dumps(
                    {
                        "type": "preference",
                        "data": {
                            "category": pref.category,
                            "preference": pref.preference,
                            "confidence": pref.confidence,
                        },
                    }
                )
            )
    else:
        # Table format
        if result.entities:
            console.print(format_entities_table(result))
        else:
            console.print("[dim]No entities extracted.[/dim]")

        if relations and result.relations:
            console.print()
            console.print(format_relations_table(result))

        if preferences and result.preferences:
            console.print()
            console.print(format_preferences_table(result))

        # Summary
        console.print()
        console.print(
            f"[dim]Extracted {len(result.entities)} entities, "
            f"{len(result.relations)} relations, "
            f"{len(result.preferences)} preferences[/dim]"
        )


@cli.group()
def schemas():
    """Manage extraction schemas."""
    pass


@schemas.command("list")
@click.option(
    "--format",
    "-o",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format.",
)
@click.option(
    "--uri",
    envvar="NEO4J_URI",
    default="bolt://localhost:7687",
    help="Neo4j URI (default: bolt://localhost:7687 or NEO4J_URI env var).",
)
@click.option(
    "--user",
    envvar="NEO4J_USER",
    default="neo4j",
    help="Neo4j username (default: neo4j or NEO4J_USER env var).",
)
@click.option(
    "--password",
    envvar="NEO4J_PASSWORD",
    help="Neo4j password (or NEO4J_PASSWORD env var).",
)
def schemas_list(format: str, uri: str, user: str, password: str | None):
    """List saved schemas from Neo4j."""
    if not password:
        error_console.print(
            "[red]Error:[/red] Neo4j password required. Set NEO4J_PASSWORD or use --password."
        )
        sys.exit(1)

    from neo4j import AsyncGraphDatabase

    from neo4j_agent_memory.schema import SchemaManager

    async def do_list():
        driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        try:
            manager = SchemaManager(driver)
            return await manager.list_schemas()
        finally:
            await driver.close()

    try:
        schema_list = run_async(do_list())
    except Exception as e:
        error_console.print(f"[red]Error connecting to Neo4j:[/red] {e}")
        sys.exit(1)

    if format == "json":
        click.echo(
            json.dumps(
                [
                    {
                        "name": s.name,
                        "latest_version": s.latest_version,
                        "is_active": s.is_active,
                        "version_count": s.version_count,
                        "description": s.description,
                    }
                    for s in schema_list
                ],
                indent=2,
            )
        )
    else:
        if not schema_list:
            console.print("[dim]No schemas found.[/dim]")
            return

        table = Table(title="Saved Schemas")
        table.add_column("Name", style="cyan")
        table.add_column("Version", style="green")
        table.add_column("Active", style="yellow")
        table.add_column("Versions", style="dim")

        for s in schema_list:
            table.add_row(
                s.name,
                s.latest_version,
                "✓" if s.is_active else "",
                str(s.version_count),
            )

        console.print(table)


@schemas.command("show")
@click.argument("name")
@click.option(
    "--version",
    "-v",
    help="Schema version (default: active version).",
)
@click.option(
    "--format",
    "-o",
    type=click.Choice(["yaml", "json"]),
    default="yaml",
    help="Output format.",
)
@click.option(
    "--uri",
    envvar="NEO4J_URI",
    default="bolt://localhost:7687",
    help="Neo4j URI.",
)
@click.option(
    "--user",
    envvar="NEO4J_USER",
    default="neo4j",
    help="Neo4j username.",
)
@click.option(
    "--password",
    envvar="NEO4J_PASSWORD",
    help="Neo4j password.",
)
def schemas_show(
    name: str, version: str | None, format: str, uri: str, user: str, password: str | None
):
    """Show details of a saved schema."""
    if not password:
        error_console.print("[red]Error:[/red] Neo4j password required.")
        sys.exit(1)

    from neo4j import AsyncGraphDatabase

    from neo4j_agent_memory.schema import SchemaManager

    async def do_show():
        driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        try:
            manager = SchemaManager(driver)
            if version:
                return await manager.load_schema_version(name, version)
            return await manager.load_schema(name)
        finally:
            await driver.close()

    try:
        schema_config = run_async(do_show())
    except Exception as e:
        error_console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if not schema_config:
        error_console.print(f"[red]Error:[/red] Schema '{name}' not found.")
        sys.exit(1)

    if format == "json":
        click.echo(json.dumps(schema_config.to_dict(), indent=2))
    else:
        # YAML output
        import yaml

        click.echo(yaml.dump(schema_config.to_dict(), default_flow_style=False, sort_keys=False))


@schemas.command("validate")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
def schemas_validate(file: Path):
    """Validate a schema YAML file."""
    try:
        schema = load_schema_from_file(file)
        console.print(f"[green]✓[/green] Schema '{schema.name}' is valid.")
        entity_type_names = [et.name for et in schema.entity_types]
        console.print(f"  Entity types: {', '.join(entity_type_names)}")
        if schema.relation_types:
            relation_type_names = [rt.name for rt in schema.relation_types]
            console.print(f"  Relation types: {', '.join(relation_type_names)}")
    except Exception as e:
        error_console.print(f"[red]✗ Invalid schema:[/red] {e}")
        sys.exit(1)


@cli.command()
@click.option(
    "--format",
    "-o",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format.",
)
@click.option(
    "--uri",
    envvar="NEO4J_URI",
    default="bolt://localhost:7687",
    help="Neo4j URI.",
)
@click.option(
    "--user",
    envvar="NEO4J_USER",
    default="neo4j",
    help="Neo4j username.",
)
@click.option(
    "--password",
    envvar="NEO4J_PASSWORD",
    help="Neo4j password.",
)
def stats(format: str, uri: str, user: str, password: str | None):
    """Show extraction statistics from Neo4j.

    Displays counts of entities, relations, and extractors stored in the database.
    """
    if not password:
        error_console.print(
            "[red]Error:[/red] Neo4j password required. Set NEO4J_PASSWORD or use --password."
        )
        sys.exit(1)

    from neo4j import AsyncGraphDatabase

    from neo4j_agent_memory.memory import LongTermMemory

    async def do_stats():
        driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        try:
            memory = LongTermMemory(driver)
            extraction_stats = await memory.get_extraction_stats()
            extractor_stats = await memory.get_extractor_stats()
            return extraction_stats, extractor_stats
        finally:
            await driver.close()

    try:
        extraction_stats, extractor_stats = run_async(do_stats())
    except Exception as e:
        error_console.print(f"[red]Error connecting to Neo4j:[/red] {e}")
        sys.exit(1)

    if format == "json":
        click.echo(
            json.dumps(
                {
                    "extraction_stats": extraction_stats,
                    "extractor_stats": extractor_stats,
                },
                indent=2,
            )
        )
    else:
        # Overview panel
        console.print(
            Panel(
                f"[cyan]Entities:[/cyan] {extraction_stats.get('total_entities', 0)}\n"
                f"[cyan]With Provenance:[/cyan] {extraction_stats.get('entities_with_provenance', 0)}\n"
                f"[cyan]Extractors:[/cyan] {extraction_stats.get('total_extractors', 0)}",
                title="Extraction Statistics",
            )
        )

        # Entity types breakdown
        entity_types = extraction_stats.get("entity_types", {})
        if entity_types:
            console.print()
            table = Table(title="Entities by Type")
            table.add_column("Type", style="cyan")
            table.add_column("Count", style="green", justify="right")

            for etype, count in sorted(entity_types.items(), key=lambda x: -x[1]):
                table.add_row(etype, str(count))

            console.print(table)

        # Extractor breakdown
        if extractor_stats:
            console.print()
            table = Table(title="Extractors")
            table.add_column("Name", style="cyan")
            table.add_column("Version", style="dim")
            table.add_column("Entities", style="green", justify="right")

            for ext in extractor_stats:
                table.add_row(
                    ext.get("name", "Unknown"),
                    ext.get("version") or "N/A",
                    str(ext.get("entity_count", 0)),
                )

            console.print(table)


@cli.group()
@click.option(
    "--uri",
    envvar="NEO4J_URI",
    default="bolt://localhost:7687",
    help="Neo4j URI.",
)
@click.option(
    "--user",
    envvar=["NEO4J_USER", "NEO4J_USERNAME"],
    default="neo4j",
    help="Neo4j username.",
)
@click.option(
    "--password",
    envvar="NEO4J_PASSWORD",
    help="Neo4j password.",
)
@click.option(
    "--database",
    envvar="NEO4J_DATABASE",
    default="neo4j",
    help="Neo4j database name.",
)
@click.option(
    "--local-embedder",
    is_flag=True,
    default=False,
    help="Use the local sentence-transformers embedder for local workflows.",
)
@click.option(
    "--hashed-local-embedder",
    is_flag=True,
    default=False,
    help="Force the deterministic hashed local embedder as a fallback local mode.",
)
@click.pass_context
def memory(
    ctx: click.Context,
    uri: str,
    user: str,
    password: str | None,
    database: str,
    local_embedder: bool,
    hashed_local_embedder: bool,
):
    """Operate the three memory layers through a shell-friendly CLI."""
    if local_embedder and hashed_local_embedder:
        raise click.UsageError("Choose either --local-embedder or --hashed-local-embedder.")

    ctx.obj = MemoryCliConnection(
        uri=uri,
        user=user,
        password=password,
        database=database,
        local_embedder=local_embedder,
        hashed_local_embedder=hashed_local_embedder,
    )


@memory.command("session-id")
@click.option("--repo", required=True, help="Repository slug.")
@click.option("--task", required=True, help="Task label.")
@click.option("--run-id", default=None, help="Optional explicit run suffix.")
@click.pass_obj
def memory_session_id(connection: MemoryCliConnection, repo: str, task: str, run_id: str | None):
    """Build a task-scoped coding session identifier."""
    service = MemoryCliService(connection)
    echo_json(service.build_session_id(repo=repo, task=task, run_id=run_id))


@memory.command("add-message")
@click.argument("text")
@click.option("--session-id", required=True, help="Target session ID.")
@click.option("--role", type=click.Choice(["user", "assistant", "system"]), required=True)
@click.option("--metadata-json", default=None, help="Optional JSON metadata.")
@click.option("--extract-entities/--no-extract-entities", default=False, help="Run entity extraction.")
@click.option(
    "--extract-relations/--no-extract-relations",
    default=False,
    help="Run relation extraction when extraction is enabled.",
)
@click.option("--generate-embedding/--no-generate-embedding", default=True, help="Generate embeddings.")
@click.pass_obj
def memory_add_message(
    connection: MemoryCliConnection,
    text: str,
    session_id: str,
    role: str,
    metadata_json: str | None,
    extract_entities: bool,
    extract_relations: bool,
    generate_embedding: bool,
):
    """Add one short-term message."""
    metadata = parse_json_option(metadata_json, "--metadata-json")
    result = run_memory_operation(
        connection,
        lambda service: service.add_message(
            session_id=session_id,
            role=role,
            text=text,
            metadata=metadata,
            extract_entities=extract_entities,
            extract_relations=extract_relations,
            generate_embedding=generate_embedding,
        ),
    )
    echo_json(result)


@memory.command("delete-message")
@click.option("--id", "message_id", required=True, help="Message UUID.")
@click.pass_obj
def memory_delete_message(connection: MemoryCliConnection, message_id: str):
    """Delete one short-term message by UUID."""
    echo_json(run_memory_operation(connection, lambda service: service.delete_message(message_id)))


@memory.command("start-trace")
@click.option("--session-id", required=True, help="Target session ID.")
@click.option("--task", required=True, help="Trace task label.")
@click.option("--message-id", default=None, help="Optional triggering message UUID.")
@click.option("--metadata-json", default=None, help="Optional JSON metadata.")
@click.option("--generate-embedding/--no-generate-embedding", default=True, help="Generate task embedding.")
@click.pass_obj
def memory_start_trace(
    connection: MemoryCliConnection,
    session_id: str,
    task: str,
    message_id: str | None,
    metadata_json: str | None,
    generate_embedding: bool,
):
    """Start one reasoning trace."""
    metadata = parse_json_option(metadata_json, "--metadata-json")
    result = run_memory_operation(
        connection,
        lambda service: service.start_trace(
            session_id=session_id,
            task=task,
            metadata=metadata,
            generate_embedding=generate_embedding,
            message_id=message_id,
        ),
    )
    echo_json(result)


@memory.command("add-trace-step")
@click.option("--trace-id", required=True, help="Reasoning trace UUID.")
@click.option("--thought", default=None, help="Concise reusable thought.")
@click.option("--action", default=None, help="Action taken.")
@click.option("--observation", default=None, help="Observation from the action.")
@click.option("--metadata-json", default=None, help="Optional JSON metadata.")
@click.option("--generate-embedding/--no-generate-embedding", default=True, help="Generate step embedding.")
@click.pass_obj
def memory_add_trace_step(
    connection: MemoryCliConnection,
    trace_id: str,
    thought: str | None,
    action: str | None,
    observation: str | None,
    metadata_json: str | None,
    generate_embedding: bool,
):
    """Add one reasoning step."""
    metadata = parse_json_option(metadata_json, "--metadata-json")
    result = run_memory_operation(
        connection,
        lambda service: service.add_trace_step(
            trace_id=trace_id,
            thought=thought,
            action=action,
            observation=observation,
            metadata=metadata,
            generate_embedding=generate_embedding,
        ),
    )
    echo_json(result)


@memory.command("add-tool-call")
@click.option("--step-id", required=True, help="Reasoning step UUID.")
@click.option("--tool-name", required=True, help="Tool name.")
@click.option("--arguments-json", default="{}", help="Tool arguments as JSON.")
@click.option("--result-json", default=None, help="Tool result as JSON.")
@click.option("--result-text", default=None, help="Tool result as plain text.")
@click.option(
    "--status",
    type=click.Choice([status.value for status in ToolCallStatus]),
    default=ToolCallStatus.SUCCESS.value,
    help="Tool call status.",
)
@click.option("--duration-ms", type=int, default=None, help="Tool duration in milliseconds.")
@click.option("--error", default=None, help="Error message when the tool failed.")
@click.option("--auto-observation", is_flag=True, default=False, help="Populate the step observation automatically.")
@click.option("--message-id", default=None, help="Optional triggering message UUID.")
@click.pass_obj
def memory_add_tool_call(
    connection: MemoryCliConnection,
    step_id: str,
    tool_name: str,
    arguments_json: str,
    result_json: str | None,
    result_text: str | None,
    status: str,
    duration_ms: int | None,
    error: str | None,
    auto_observation: bool,
    message_id: str | None,
):
    """Record one tool call under a reasoning step."""
    if result_json and result_text:
        raise click.ClickException("Use either --result-json or --result-text, not both.")
    arguments = parse_json_option(arguments_json, "--arguments-json")
    result: Any | None = result_text
    if result_json is not None:
        result = parse_json_option(result_json, "--result-json")
    payload = run_memory_operation(
        connection,
        lambda service: service.add_tool_call(
            step_id=step_id,
            tool_name=tool_name,
            arguments=arguments or {},
            result=result,
            status=ToolCallStatus(status),
            duration_ms=duration_ms,
            error=error,
            auto_observation=auto_observation,
            message_id=message_id,
        ),
    )
    echo_json(payload)


@memory.command("complete-trace")
@click.option("--trace-id", required=True, help="Reasoning trace UUID.")
@click.option("--outcome", default=None, help="Outcome summary.")
@click.option("--success", is_flag=True, default=False, help="Mark the trace as successful.")
@click.option("--failure", is_flag=True, default=False, help="Mark the trace as failed.")
@click.option(
    "--generate-step-embeddings",
    is_flag=True,
    default=False,
    help="Generate missing step embeddings before completion.",
)
@click.pass_obj
def memory_complete_trace(
    connection: MemoryCliConnection,
    trace_id: str,
    outcome: str | None,
    success: bool,
    failure: bool,
    generate_step_embeddings: bool,
):
    """Complete one reasoning trace."""
    if success and failure:
        raise click.ClickException("Use either --success or --failure, not both.")
    resolved_success: bool | None = True if success else False if failure else None
    payload = run_memory_operation(
        connection,
        lambda service: service.complete_trace(
            trace_id=trace_id,
            outcome=outcome,
            success=resolved_success,
            generate_step_embeddings=generate_step_embeddings,
        ),
    )
    echo_json(payload)


@memory.command("add-entity")
@click.option("--repo", required=True, help="Repository slug.")
@click.option("--task", required=True, help="Task label.")
@click.option("--name", required=True, help="Entity name.")
@click.option("--type", "entity_type", required=True, help="Entity type.")
@click.option("--description", default=None, help="Optional entity description.")
@click.option("--scope", "scope_kind", type=click.Choice(["repo", "personal"]), default="repo")
@click.option("--metadata-json", default=None, help="Optional JSON metadata.")
@click.option("--resolve/--no-resolve", default=True, help="Run entity resolution.")
@click.option("--deduplicate/--no-deduplicate", default=True, help="Run entity deduplication.")
@click.option("--enrich/--no-enrich", default=False, help="Run enrichment.")
@click.option("--geocode/--no-geocode", default=False, help="Run geocoding for location entities.")
@click.pass_obj
def memory_add_entity(
    connection: MemoryCliConnection,
    repo: str,
    task: str,
    name: str,
    entity_type: str,
    description: str | None,
    scope_kind: str,
    metadata_json: str | None,
    resolve: bool,
    deduplicate: bool,
    enrich: bool,
    geocode: bool,
):
    """Add or reuse one long-term entity."""
    metadata = parse_json_option(metadata_json, "--metadata-json")
    payload = run_memory_operation(
        connection,
        lambda service: service.add_entity(
            repo=repo,
            task=task,
            name=name,
            entity_type=entity_type,
            description=description,
            scope_kind=scope_kind,
            metadata=metadata,
            resolve=resolve,
            deduplicate=deduplicate,
            enrich=enrich,
            geocode=geocode,
        ),
    )
    echo_json(payload)


@memory.command("update-entity")
@click.option("--id", "entity_id", required=True, help="Existing entity UUID.")
@click.option("--name", default=None, help="Override entity name.")
@click.option("--canonical-name", default=None, help="Override canonical display name.")
@click.option("--description", default=None, help="Override entity description.")
@click.option("--metadata-json", default=None, help="Optional JSON metadata patch.")
@click.pass_obj
def memory_update_entity(
    connection: MemoryCliConnection,
    entity_id: str,
    name: str | None,
    canonical_name: str | None,
    description: str | None,
    metadata_json: str | None,
):
    """Update one entity without changing its identity."""
    if name is None and canonical_name is None and description is None and metadata_json is None:
        raise click.ClickException(
            "Provide at least one of --name, --canonical-name, --description, or --metadata-json."
        )
    metadata = parse_json_option(metadata_json, "--metadata-json")
    payload = run_memory_operation(
        connection,
        lambda service: service.update_entity(
            entity_id=entity_id,
            name=name,
            canonical_name=canonical_name,
            description=description,
            metadata_updates=metadata,
        ),
    )
    echo_json(payload)


@memory.command("alias-entity")
@click.option("--id", "entity_id", required=True, help="Existing entity UUID.")
@click.option("--alias", required=True, help="Alias to add.")
@click.pass_obj
def memory_alias_entity(
    connection: MemoryCliConnection,
    entity_id: str,
    alias: str,
):
    """Add one alias to an existing entity."""
    payload = run_memory_operation(
        connection,
        lambda service: service.alias_entity(
            entity_id=entity_id,
            alias=alias,
        ),
    )
    echo_json(payload)


@memory.command("merge-entity")
@click.option("--source-id", required=True, help="Entity UUID to merge from.")
@click.option("--target-id", required=True, help="Entity UUID to merge into.")
@click.pass_obj
def memory_merge_entity(
    connection: MemoryCliConnection,
    source_id: str,
    target_id: str,
):
    """Merge one entity into another and keep the target active."""
    if source_id == target_id:
        raise click.ClickException("Use different values for --source-id and --target-id.")
    payload = run_memory_operation(
        connection,
        lambda service: service.merge_entity(
            source_id=source_id,
            target_id=target_id,
        ),
    )
    echo_json(payload)


@memory.command("add-preference")
@click.option("--repo", required=True, help="Repository slug.")
@click.option("--task", required=True, help="Task label.")
@click.option("--category", required=True, help="Preference category.")
@click.option("--preference", required=True, help="Preference text.")
@click.option("--context", default=None, help="Optional preference context.")
@click.option("--scope", "scope_kind", type=click.Choice(["repo", "personal"]), default="repo")
@click.option("--confidence", type=float, default=1.0, help="Stored confidence score.")
@click.option("--metadata-json", default=None, help="Optional JSON metadata.")
@click.option("--generate-embedding/--no-generate-embedding", default=True, help="Generate embedding.")
@click.pass_obj
def memory_add_preference(
    connection: MemoryCliConnection,
    repo: str,
    task: str,
    category: str,
    preference: str,
    context: str | None,
    scope_kind: str,
    confidence: float,
    metadata_json: str | None,
    generate_embedding: bool,
):
    """Add or reuse one durable preference."""
    metadata = parse_json_option(metadata_json, "--metadata-json")
    payload = run_memory_operation(
        connection,
        lambda service: service.add_preference(
            repo=repo,
            task=task,
            category=category,
            preference=preference,
            context=context,
            scope_kind=scope_kind,
            confidence=confidence,
            metadata=metadata,
            generate_embedding=generate_embedding,
        ),
    )
    echo_json(payload)


@memory.command("add-fact")
@click.option("--repo", required=True, help="Repository slug.")
@click.option("--task", required=True, help="Task label.")
@click.option("--subject", required=True, help="Fact subject.")
@click.option("--predicate", required=True, help="Fact predicate.")
@click.option("--object-value", required=True, help="Fact object value.")
@click.option("--scope", "scope_kind", type=click.Choice(["repo", "personal"]), default="repo")
@click.option("--confidence", type=float, default=1.0, help="Stored confidence score.")
@click.option("--metadata-json", default=None, help="Optional JSON metadata.")
@click.option("--generate-embedding/--no-generate-embedding", default=True, help="Generate embedding.")
@click.pass_obj
def memory_add_fact(
    connection: MemoryCliConnection,
    repo: str,
    task: str,
    subject: str,
    predicate: str,
    object_value: str,
    scope_kind: str,
    confidence: float,
    metadata_json: str | None,
    generate_embedding: bool,
):
    """Add or reuse one durable fact."""
    metadata = parse_json_option(metadata_json, "--metadata-json")
    payload = run_memory_operation(
        connection,
        lambda service: service.add_fact(
            repo=repo,
            task=task,
            subject=subject,
            predicate=predicate,
            obj=object_value,
            scope_kind=scope_kind,
            confidence=confidence,
            metadata=metadata,
            generate_embedding=generate_embedding,
        ),
    )
    echo_json(payload)


@memory.command("replace-preference")
@click.option("--id", "preference_id", required=True, help="Existing preference UUID.")
@click.option("--preference", required=True, help="New preference text.")
@click.option("--category", default=None, help="Override category.")
@click.option("--context", default=None, help="Override context.")
@click.option("--repo", default=None, help="Override repo metadata.")
@click.option("--task", default=None, help="Override task metadata.")
@click.option("--scope", "scope_kind", type=click.Choice(["repo", "personal"]), default=None)
@click.option("--confidence", type=float, default=None, help="Override stored confidence.")
@click.option("--generate-embedding/--no-generate-embedding", default=True, help="Generate embedding.")
@click.pass_obj
def memory_replace_preference(
    connection: MemoryCliConnection,
    preference_id: str,
    preference: str,
    category: str | None,
    context: str | None,
    repo: str | None,
    task: str | None,
    scope_kind: str | None,
    confidence: float | None,
    generate_embedding: bool,
):
    """Create a new active preference and supersede the previous one."""
    payload = run_memory_operation(
        connection,
        lambda service: service.replace_preference(
            preference_id=preference_id,
            preference=preference,
            category=category,
            context=context,
            repo=repo,
            task=task,
            scope_kind=scope_kind,
            confidence=confidence,
            generate_embedding=generate_embedding,
        ),
    )
    echo_json(payload)


@memory.command("replace-fact")
@click.option("--id", "fact_id", required=True, help="Existing fact UUID.")
@click.option("--subject", default=None, help="Override subject.")
@click.option("--predicate", default=None, help="Override predicate.")
@click.option("--object-value", default=None, help="Override object value.")
@click.option("--repo", default=None, help="Override repo metadata.")
@click.option("--task", default=None, help="Override task metadata.")
@click.option("--scope", "scope_kind", type=click.Choice(["repo", "personal"]), default=None)
@click.option("--confidence", type=float, default=None, help="Override stored confidence.")
@click.option("--generate-embedding/--no-generate-embedding", default=True, help="Generate embedding.")
@click.pass_obj
def memory_replace_fact(
    connection: MemoryCliConnection,
    fact_id: str,
    subject: str | None,
    predicate: str | None,
    object_value: str | None,
    repo: str | None,
    task: str | None,
    scope_kind: str | None,
    confidence: float | None,
    generate_embedding: bool,
):
    """Create a new active fact and supersede the previous one."""
    if subject is None and predicate is None and object_value is None:
        raise click.ClickException("Provide at least one of --subject, --predicate, or --object-value.")
    payload = run_memory_operation(
        connection,
        lambda service: service.replace_fact(
            fact_id=fact_id,
            subject=subject,
            predicate=predicate,
            obj=object_value,
            repo=repo,
            task=task,
            scope_kind=scope_kind,
            confidence=confidence,
            generate_embedding=generate_embedding,
        ),
    )
    echo_json(payload)


@memory.command("inspect")
@click.option("--kind", type=click.Choice(["entity", "preference", "fact", "message"]), required=True)
@click.option("--id", "entry_id", required=True, help="Entry UUID.")
@click.pass_obj
def memory_inspect(connection: MemoryCliConnection, kind: str, entry_id: str):
    """Inspect one memory entry by UUID."""
    echo_json(run_memory_operation(connection, lambda service: service.inspect(kind=kind, entry_id=entry_id)))


@memory.command("search")
@click.option("--kind", type=click.Choice(["entity", "preference", "fact", "message"]), required=True)
@click.option("--query", required=True, help="Search query.")
@click.option("--limit", type=int, default=10, help="Maximum results.")
@click.option("--threshold", type=float, default=0.7, help="Minimum similarity threshold.")
@click.option("--session-id", default=None, help="Optional session filter for messages.")
@click.option("--category", default=None, help="Optional category filter for preferences.")
@click.option(
    "--include-superseded",
    is_flag=True,
    default=False,
    help="Include superseded durable entries for facts and preferences.",
)
@click.pass_obj
def memory_search(
    connection: MemoryCliConnection,
    kind: str,
    query: str,
    limit: int,
    threshold: float,
    session_id: str | None,
    category: str | None,
    include_superseded: bool,
):
    """Search one memory layer."""
    payload = run_memory_operation(
        connection,
        lambda service: service.search(
            kind=kind,
            query=query,
            limit=limit,
            threshold=threshold,
            session_id=session_id,
            category=category,
            include_superseded=include_superseded,
        ),
    )
    echo_json(payload)


@memory.command("get-context")
@click.option("--query", required=True, help="Context retrieval query.")
@click.option("--session-id", default=None, help="Optional session filter.")
@click.option("--include-short-term/--no-include-short-term", default=True)
@click.option("--include-long-term/--no-include-long-term", default=True)
@click.option("--include-reasoning/--no-include-reasoning", default=True)
@click.option("--max-items", type=int, default=10, help="Maximum items per layer.")
@click.pass_obj
def memory_get_context(
    connection: MemoryCliConnection,
    query: str,
    session_id: str | None,
    include_short_term: bool,
    include_long_term: bool,
    include_reasoning: bool,
    max_items: int,
):
    """Assemble combined context across the enabled memory layers."""
    payload = run_memory_operation(
        connection,
        lambda service: service.get_context(
            query=query,
            session_id=session_id,
            include_short_term=include_short_term,
            include_long_term=include_long_term,
            include_reasoning=include_reasoning,
            max_items=max_items,
        ),
    )
    echo_json(payload)


@memory.command("recall")
@click.option("--repo", required=True, help="Repository slug.")
@click.option("--task", required=True, help="Task label.")
@click.option("--session-id", required=True, help="Task-scoped coding session ID.")
@click.option("--query", default=None, help="Optional recall query. Defaults to the task label.")
@click.option("--recent-messages", type=int, default=6, help="Maximum recent session messages.")
@click.option("--max-preferences", type=int, default=5, help="Maximum durable preferences.")
@click.option("--max-facts", type=int, default=5, help="Maximum durable facts.")
@click.option("--max-entities", type=int, default=5, help="Maximum relevant entities.")
@click.option("--max-traces", type=int, default=3, help="Maximum similar past tasks.")
@click.pass_obj
def memory_recall(
    connection: MemoryCliConnection,
    repo: str,
    task: str,
    session_id: str,
    query: str | None,
    recent_messages: int,
    max_preferences: int,
    max_facts: int,
    max_entities: int,
    max_traces: int,
):
    """Assemble coding-oriented startup recall for one task session."""
    payload = run_memory_operation(
        connection,
        lambda service: service.recall(
            repo=repo,
            task=task,
            session_id=session_id,
            query=query,
            recent_messages=recent_messages,
            max_preferences=max_preferences,
            max_facts=max_facts,
            max_entities=max_entities,
            max_traces=max_traces,
        ),
    )
    echo_json(payload)


@memory.command("delete")
@click.option("--kind", type=click.Choice(["entity", "preference", "fact", "message"]), required=True)
@click.option("--id", "entry_id", required=True, help="Entry UUID.")
@click.pass_obj
def memory_delete(connection: MemoryCliConnection, kind: str, entry_id: str):
    """Delete one memory entry by UUID."""
    echo_json(run_memory_operation(connection, lambda service: service.delete(kind=kind, entry_id=entry_id)))


@cli.group()
def mcp():
    """MCP (Model Context Protocol) server commands.

    Start an MCP server that exposes memory tools, resources, and prompts
    for Claude Desktop, Claude Code, Cursor, and other MCP-compatible hosts.
    """
    pass


@mcp.command("serve")
@click.option(
    "--uri",
    envvar="NEO4J_URI",
    default="bolt://localhost:7687",
    help="Neo4j connection URI.",
)
@click.option(
    "--user",
    envvar="NEO4J_USER",
    default="neo4j",
    help="Neo4j username.",
)
@click.option(
    "--password",
    envvar="NEO4J_PASSWORD",
    help="Neo4j password (or NEO4J_PASSWORD env var).",
)
@click.option(
    "--database",
    envvar="NEO4J_DATABASE",
    default="neo4j",
    help="Neo4j database name.",
)
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse", "http"]),
    default="stdio",
    help="MCP transport type (default: stdio).",
)
@click.option(
    "--host",
    default="127.0.0.1",
    help="Host for network transports.",
)
@click.option(
    "--port",
    type=int,
    default=8080,
    help="Port for network transports.",
)
@click.option(
    "--profile",
    type=click.Choice(["core", "extended"]),
    default="extended",
    help="Tool profile: core (6 tools) or extended (16 tools).",
)
@click.option(
    "--session-strategy",
    type=click.Choice(["per_conversation", "per_day", "persistent"]),
    default="per_conversation",
    help="Session identity strategy.",
)
@click.option(
    "--user-id",
    envvar="MCP_USER_ID",
    default=None,
    help="User ID for per_day/persistent session strategies.",
)
@click.option(
    "--observation-threshold",
    type=int,
    default=30000,
    help="Token threshold for observational memory compression.",
)
@click.option(
    "--no-auto-preferences",
    is_flag=True,
    default=False,
    help="Disable automatic preference detection.",
)
def mcp_serve(
    uri: str,
    user: str,
    password: str | None,
    database: str,
    transport: str,
    host: str,
    port: int,
    profile: str,
    session_strategy: str,
    user_id: str | None,
    observation_threshold: int,
    no_auto_preferences: bool,
):
    """Start the MCP server for Claude Desktop and other MCP hosts.

    The server exposes memory tools, resources, and prompts via the
    Model Context Protocol. Use stdio transport for Claude Desktop
    or SSE/HTTP for network deployments.

    \b
    Examples:
        # Start with stdio transport (for Claude Desktop)
        neo4j-agent-memory mcp serve --password mypassword

    \b
        # Start with SSE transport on port 8080
        neo4j-agent-memory mcp serve --transport sse --port 8080

    \b
        # Start with core profile (fewer tools, less context overhead)
        neo4j-agent-memory mcp serve --profile core
    """
    if not password:
        error_console.print(
            "[red]Error:[/red] Neo4j password required. Set NEO4J_PASSWORD or use --password."
        )
        sys.exit(1)

    try:
        from neo4j_agent_memory.mcp.server import run_server
    except ImportError:
        error_console.print(
            "[red]Error:[/red] MCP dependencies not installed. "
            "Install with: pip install neo4j-agent-memory[mcp]"
        )
        sys.exit(1)

    asyncio.run(
        run_server(
            neo4j_uri=uri,
            neo4j_user=user,
            neo4j_password=password,
            neo4j_database=database,
            transport=transport,
            host=host,
            port=port,
            profile=profile,
            session_strategy=session_strategy,
            user_id=user_id,
            observation_threshold=observation_threshold,
            auto_preferences=not no_auto_preferences,
        )
    )


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
