"""Operational helpers for the CLI memory workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Iterable
from uuid import UUID

from pydantic import SecretStr

from neo4j_agent_memory import (
    CodingAgentMemory,
    EmbeddingConfig,
    EmbeddingProvider,
    MemoryClient,
    MemorySettings,
    Neo4jConfig,
    ToolCallStatus,
    build_coding_session_id,
)


TOKEN_RE = re.compile(r"[a-z0-9_]+")
_REPLACEMENT_METADATA_DROP_KEYS = {
    "status",
    "superseded_by",
    "superseded_at",
    "supersession_reason",
    "supersedes_ids",
    "candidate_source",
    "candidate_evidence",
    "candidate_confidence",
}


def _deserialize_metadata(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _sanitize_active_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    cleaned = dict(metadata or {})
    for key in _REPLACEMENT_METADATA_DROP_KEYS:
        cleaned.pop(key, None)
    return cleaned


def _build_superseded_metadata(
    metadata: dict[str, Any] | None,
    *,
    superseded_by: str,
    reason: str,
) -> dict[str, Any]:
    updated = dict(metadata or {})
    updated["status"] = "superseded"
    updated["superseded_by"] = superseded_by
    updated["superseded_at"] = datetime.now(UTC).isoformat()
    updated["supersession_reason"] = reason
    return updated


def to_jsonable(value: Any) -> Any:
    """Convert common model and graph values to JSON-safe structures."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {
            key: to_jsonable(item)
            for key, item in value.items()
            if key not in {"embedding", "task_embedding"}
        }
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump(mode="python"))
    return value


@dataclass(slots=True)
class LocalHashedEmbedder:
    """Deterministic local embedder for CLI-driven local workflows."""

    dimensions: int = 384

    def _tokenize(self, text: str) -> list[str]:
        return TOKEN_RE.findall(text.lower())

    def _bucket(self, token: str) -> int:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % self.dimensions

    async def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = self._tokenize(text)
        if not tokens:
            return vector

        for token in tokens:
            vector[self._bucket(token)] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector

        return [value / norm for value in vector]

    async def embed_batch(self, texts: Iterable[str]) -> list[list[float]]:
        return [await self.embed(text) for text in texts]


@dataclass(slots=True)
class MemoryCliConnection:
    uri: str
    user: str
    password: str | None
    database: str
    local_embedder: bool = False


class MemoryCliService:
    """Thin service layer for the CLI memory workflow."""

    def __init__(self, connection: MemoryCliConnection):
        self._connection = connection
        self._client: MemoryClient | None = None

    def _build_settings(self) -> MemorySettings:
        settings = MemorySettings()
        settings.neo4j = Neo4jConfig(
            uri=self._connection.uri,
            username=self._connection.user,
            password=SecretStr(self._connection.password or ""),
            database=self._connection.database,
        )

        if self._connection.local_embedder:
            settings.embedding = EmbeddingConfig(
                provider=EmbeddingProvider.CUSTOM,
                model="local-hashed-overlap",
                dimensions=384,
            )

        return settings

    async def __aenter__(self) -> MemoryCliService:
        if not self._connection.password:
            raise ValueError("Neo4j password required. Set NEO4J_PASSWORD or use --password.")

        embedder = LocalHashedEmbedder(dimensions=384) if self._connection.local_embedder else None
        self._client = MemoryClient(self._build_settings(), embedder=embedder)
        await self._client.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    @property
    def client(self) -> MemoryClient:
        if self._client is None:
            raise RuntimeError("MemoryCliService is not connected.")
        return self._client

    def build_session_id(self, repo: str, task: str, run_id: str | None = None) -> dict[str, Any]:
        return {
            "session_id": build_coding_session_id(repo=repo, task=task, run_id=run_id),
            "repo": repo,
            "task": task,
        }

    def _coding_memory(self, repo: str, task: str, session_id: str | None = None) -> CodingAgentMemory:
        return CodingAgentMemory(self.client, repo=repo, task=task, session_id=session_id)

    async def add_message(
        self,
        *,
        session_id: str,
        role: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        extract_entities: bool = False,
        extract_relations: bool = False,
        generate_embedding: bool = True,
    ) -> dict[str, Any]:
        message = await self.client.short_term.add_message(
            session_id=session_id,
            role=role,
            content=text,
            metadata=metadata,
            extract_entities=extract_entities,
            extract_relations=extract_relations,
            generate_embedding=generate_embedding,
        )
        return {"message": to_jsonable(message)}

    async def delete_message(self, message_id: str) -> dict[str, Any]:
        deleted = await self.client.short_term.delete_message(message_id)
        return {"kind": "message", "id": message_id, "deleted": deleted}

    async def start_trace(
        self,
        *,
        session_id: str,
        task: str,
        metadata: dict[str, Any] | None = None,
        generate_embedding: bool = True,
        message_id: str | None = None,
    ) -> dict[str, Any]:
        trace = await self.client.reasoning.start_trace(
            session_id=session_id,
            task=task,
            metadata=metadata,
            generate_embedding=generate_embedding,
            triggered_by_message_id=message_id,
        )
        return {"trace": to_jsonable(trace)}

    async def add_trace_step(
        self,
        *,
        trace_id: str,
        thought: str | None = None,
        action: str | None = None,
        observation: str | None = None,
        metadata: dict[str, Any] | None = None,
        generate_embedding: bool = True,
    ) -> dict[str, Any]:
        step = await self.client.reasoning.add_step(
            UUID(trace_id),
            thought=thought,
            action=action,
            observation=observation,
            metadata=metadata,
            generate_embedding=generate_embedding,
        )
        return {"step": to_jsonable(step)}

    async def add_tool_call(
        self,
        *,
        step_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any | None = None,
        status: ToolCallStatus = ToolCallStatus.SUCCESS,
        duration_ms: int | None = None,
        error: str | None = None,
        auto_observation: bool = False,
        message_id: str | None = None,
    ) -> dict[str, Any]:
        tool_call = await self.client.reasoning.record_tool_call(
            UUID(step_id),
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            status=status,
            duration_ms=duration_ms,
            error=error,
            auto_observation=auto_observation,
            message_id=message_id,
        )
        return {"tool_call": to_jsonable(tool_call)}

    async def complete_trace(
        self,
        *,
        trace_id: str,
        outcome: str | None = None,
        success: bool | None = None,
        generate_step_embeddings: bool = False,
    ) -> dict[str, Any]:
        trace = await self.client.reasoning.complete_trace(
            UUID(trace_id),
            outcome=outcome,
            success=success,
            generate_step_embeddings=generate_step_embeddings,
        )
        return {"trace": to_jsonable(trace)}

    async def add_entity(
        self,
        *,
        repo: str,
        task: str,
        name: str,
        entity_type: str,
        description: str | None = None,
        scope_kind: str = "repo",
        metadata: dict[str, Any] | None = None,
        resolve: bool = True,
        deduplicate: bool = True,
        enrich: bool = False,
        geocode: bool = False,
    ) -> dict[str, Any]:
        coding_memory = self._coding_memory(repo, task)
        entity, dedup_result = await coding_memory.remember_entity(
            name=name,
            entity_type=entity_type,
            description=description,
            metadata={**(metadata or {}), "scope_kind": scope_kind},
            resolve=resolve,
            deduplicate=deduplicate,
            enrich=enrich,
            geocode=geocode,
        )
        return {
            "entity": to_jsonable(entity),
            "deduplication": to_jsonable(dedup_result),
        }

    async def update_entity(
        self,
        *,
        entity_id: str,
        name: str | None = None,
        canonical_name: str | None = None,
        description: str | None = None,
        metadata_updates: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entity = await self.client.long_term.update_entity(
            entity_id,
            name=name,
            canonical_name=canonical_name,
            description=description,
            metadata_updates=metadata_updates,
        )
        if entity is None:
            raise ValueError(f"Entity not found: {entity_id}")
        return {"entity": to_jsonable(entity)}

    async def alias_entity(
        self,
        *,
        entity_id: str,
        alias: str,
    ) -> dict[str, Any]:
        entity = await self.client.long_term.add_entity_alias(entity_id, alias)
        if entity is None:
            raise ValueError(f"Entity not found: {entity_id}")
        return {"entity": to_jsonable(entity), "alias": alias}

    async def merge_entity(
        self,
        *,
        source_id: str,
        target_id: str,
    ) -> dict[str, Any]:
        if source_id == target_id:
            raise ValueError("source_id and target_id must be different.")
        result = await self.client.long_term.merge_duplicate_entities(
            UUID(source_id),
            UUID(target_id),
        )
        if result is None:
            raise ValueError(f"Could not merge entities {source_id} -> {target_id}.")
        source, target = result
        return {
            "source": to_jsonable(source),
            "target": to_jsonable(target),
        }

    async def add_preference(
        self,
        *,
        repo: str,
        task: str,
        category: str,
        preference: str,
        context: str | None = None,
        scope_kind: str = "repo",
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
        generate_embedding: bool = True,
    ) -> dict[str, Any]:
        coding_memory = self._coding_memory(repo, task)
        created = await coding_memory.remember_preference(
            category=category,
            preference=preference,
            context=context,
            confidence=confidence,
            metadata={**(metadata or {}), "scope_kind": scope_kind},
            generate_embedding=generate_embedding,
        )
        return {"preference": to_jsonable(created)}

    async def add_fact(
        self,
        *,
        repo: str,
        task: str,
        subject: str,
        predicate: str,
        obj: str,
        scope_kind: str = "repo",
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
        generate_embedding: bool = True,
    ) -> dict[str, Any]:
        coding_memory = self._coding_memory(repo, task)
        created = await coding_memory.remember_fact(
            subject=subject,
            predicate=predicate,
            obj=obj,
            confidence=confidence,
            metadata={**(metadata or {}), "scope_kind": scope_kind},
            generate_embedding=generate_embedding,
        )
        return {"fact": to_jsonable(created)}

    async def _inspect_raw(self, label: str, entry_id: str) -> dict[str, Any] | None:
        node = await self.client.graph.get_node_by_id(label, entry_id)
        if node is None:
            return None
        if "metadata" in node:
            node["metadata"] = _deserialize_metadata(node["metadata"])
        return to_jsonable(node)

    async def replace_preference(
        self,
        *,
        preference_id: str,
        preference: str,
        category: str | None = None,
        context: str | None = None,
        repo: str | None = None,
        task: str | None = None,
        scope_kind: str | None = None,
        confidence: float | None = None,
        generate_embedding: bool = True,
    ) -> dict[str, Any]:
        existing = await self._inspect_raw("Preference", preference_id)
        if existing is None:
            raise ValueError(f"Preference not found: {preference_id}")

        metadata = _sanitize_active_metadata(_deserialize_metadata(existing.get("metadata")))
        resolved_repo = repo or metadata.get("repo") or "memory-cli"
        resolved_task = task or metadata.get("task") or "memory-cli"
        resolved_scope = scope_kind or metadata.get("scope_kind") or "repo"

        result = await self.add_preference(
            repo=resolved_repo,
            task=resolved_task,
            category=category or str(existing["category"]),
            preference=preference,
            context=context if context is not None else existing.get("context"),
            scope_kind=resolved_scope,
            confidence=confidence if confidence is not None else float(existing.get("confidence", 1.0)),
            metadata=metadata,
            generate_embedding=generate_embedding,
        )
        created = result["preference"]
        if created["id"] != preference_id and existing.get("metadata", {}).get("status") != "superseded":
            await self.client.long_term.update_preference_metadata(
                preference_id,
                _build_superseded_metadata(
                    _deserialize_metadata(existing.get("metadata")),
                    superseded_by=created["id"],
                    reason="Superseded by explicit CLI replace-preference command.",
                ),
            )
            await self.client.long_term.link_preference_supersession(
                preference_id,
                created["id"],
                reason="Superseded by explicit CLI replace-preference command.",
            )
        result["replaced_id"] = preference_id
        return result

    async def replace_fact(
        self,
        *,
        fact_id: str,
        subject: str | None = None,
        predicate: str | None = None,
        obj: str | None = None,
        repo: str | None = None,
        task: str | None = None,
        scope_kind: str | None = None,
        confidence: float | None = None,
        generate_embedding: bool = True,
    ) -> dict[str, Any]:
        existing = await self._inspect_raw("Fact", fact_id)
        if existing is None:
            raise ValueError(f"Fact not found: {fact_id}")

        metadata = _sanitize_active_metadata(_deserialize_metadata(existing.get("metadata")))
        resolved_repo = repo or metadata.get("repo") or "memory-cli"
        resolved_task = task or metadata.get("task") or "memory-cli"
        resolved_scope = scope_kind or metadata.get("scope_kind") or "repo"

        result = await self.add_fact(
            repo=resolved_repo,
            task=resolved_task,
            subject=subject or str(existing["subject"]),
            predicate=predicate or str(existing["predicate"]),
            obj=obj or str(existing["object"]),
            scope_kind=resolved_scope,
            confidence=confidence if confidence is not None else float(existing.get("confidence", 1.0)),
            metadata=metadata,
            generate_embedding=generate_embedding,
        )
        created = result["fact"]
        if created["id"] != fact_id and existing.get("metadata", {}).get("status") != "superseded":
            await self.client.long_term.update_fact_metadata(
                fact_id,
                _build_superseded_metadata(
                    _deserialize_metadata(existing.get("metadata")),
                    superseded_by=created["id"],
                    reason="Superseded by explicit CLI replace-fact command.",
                ),
            )
            await self.client.long_term.link_fact_supersession(
                fact_id,
                created["id"],
                reason="Superseded by explicit CLI replace-fact command.",
            )
        result["replaced_id"] = fact_id
        return result

    async def inspect(self, *, kind: str, entry_id: str) -> dict[str, Any]:
        label_map = {
            "entity": "Entity",
            "preference": "Preference",
            "fact": "Fact",
            "message": "Message",
        }
        label = label_map[kind]
        entry = await self._inspect_raw(label, entry_id)
        return {"kind": kind, "id": entry_id, "entry": entry}

    async def search(
        self,
        *,
        kind: str,
        query: str,
        limit: int = 10,
        threshold: float = 0.7,
        session_id: str | None = None,
        category: str | None = None,
        include_superseded: bool = False,
    ) -> dict[str, Any]:
        if kind == "entity":
            results = await self.client.long_term.search_entities(
                query,
                limit=limit,
                threshold=threshold,
            )
        elif kind == "preference":
            results = await self.client.long_term.search_preferences(
                query,
                category=category,
                limit=limit,
                threshold=threshold,
                include_superseded=include_superseded,
            )
        elif kind == "fact":
            results = await self.client.long_term.search_facts(
                query,
                limit=limit,
                threshold=threshold,
                include_superseded=include_superseded,
            )
        elif kind == "message":
            results = await self.client.short_term.search_messages(
                query,
                session_id=session_id,
                limit=limit,
                threshold=threshold,
            )
        else:
            raise ValueError(f"Unsupported search kind: {kind}")

        return {
            "kind": kind,
            "query": query,
            "count": len(results),
            "results": to_jsonable(results),
        }

    async def get_context(
        self,
        *,
        query: str,
        session_id: str | None = None,
        include_short_term: bool = True,
        include_long_term: bool = True,
        include_reasoning: bool = True,
        max_items: int = 10,
    ) -> dict[str, Any]:
        context = await self.client.get_context(
            query=query,
            session_id=session_id,
            include_short_term=include_short_term,
            include_long_term=include_long_term,
            include_reasoning=include_reasoning,
            max_items=max_items,
        )
        return {
            "session_id": session_id,
            "query": query,
            "has_context": bool(context),
            "context": context,
        }

    async def recall(
        self,
        *,
        repo: str,
        task: str,
        session_id: str,
        query: str | None = None,
        recent_messages: int = 6,
        max_preferences: int = 5,
        max_facts: int = 5,
        max_entities: int = 5,
        max_traces: int = 3,
    ) -> dict[str, Any]:
        coding_memory = self._coding_memory(repo=repo, task=task, session_id=session_id)
        context = await coding_memory.get_startup_recall(
            query=query,
            recent_messages=recent_messages,
            max_preferences=max_preferences,
            max_facts=max_facts,
            max_entities=max_entities,
            max_traces=max_traces,
        )
        return {
            "repo": repo,
            "task": task,
            "session_id": session_id,
            "query": query or task,
            "has_context": bool(context),
            "context": context,
        }

    async def delete(self, *, kind: str, entry_id: str) -> dict[str, Any]:
        if kind == "message":
            return await self.delete_message(entry_id)

        label_map = {
            "entity": "Entity",
            "preference": "Preference",
            "fact": "Fact",
        }
        label = label_map[kind]
        deleted = await self.client.graph.delete_node_by_id(label, entry_id)
        return {"kind": kind, "id": entry_id, "deleted": deleted}
