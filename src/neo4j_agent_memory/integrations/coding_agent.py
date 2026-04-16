"""Thin coding-agent workflow helpers for Neo4j Agent Memory.

This module adds a task-scoped wrapper over ``MemoryClient`` for coding agents.
It keeps the native three-layer model intact while making a few workflow
decisions explicit:

- one ``session_id`` per active coding task
- short-term messages for the current task stream
- curated long-term writes for durable facts and preferences
- reasoning traces only for non-trivial work
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
import re
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from neo4j_agent_memory.integrations.base import validate_query, validate_session_id
from neo4j_agent_memory.memory.long_term import normalize_entity_type
from neo4j_agent_memory.memory.reasoning import ToolCallStatus

if TYPE_CHECKING:
    from neo4j_agent_memory import MemoryClient
    from neo4j_agent_memory.memory.long_term import Entity, Fact, Preference
    from neo4j_agent_memory.memory.reasoning import ReasoningStep, ReasoningTrace, ToolCall
    from neo4j_agent_memory.memory.short_term import Message


_SESSION_PART_RE = re.compile(r"[^a-z0-9]+")
_STRONG_SOURCES = {"user_explicit", "code_verified", "docs_verified", "test_verified"}


def _normalize_durable_value(value: str | None) -> str:
    """Normalize durable text values before duplicate checks."""
    if value is None:
        return ""
    return " ".join(value.strip().casefold().split())


class LongTermCandidateType(str, Enum):
    """Supported long-term candidate types."""

    FACT = "fact"
    PREFERENCE = "preference"
    ENTITY = "entity"


class LongTermCandidateScopeKind(str, Enum):
    """Logical scope boundary for durable candidates."""

    REPO = "repo"
    PERSONAL = "personal"


class LongTermCandidateSource(str, Enum):
    """Origin of the evidence backing a durable candidate."""

    USER_EXPLICIT = "user_explicit"
    CODE_VERIFIED = "code_verified"
    DOCS_VERIFIED = "docs_verified"
    TEST_VERIFIED = "test_verified"
    RUN_OBSERVATION = "run_observation"


class LongTermCandidateConfidence(str, Enum):
    """Policy confidence level for candidate review."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(slots=True)
class LongTermMemoryCandidate:
    """Structured long-term memory candidate for review before persistence."""

    type: LongTermCandidateType
    scope_kind: LongTermCandidateScopeKind
    content: str
    why_candidate: str
    source: LongTermCandidateSource
    confidence: LongTermCandidateConfidence
    evidence: str
    suggested_action: str
    payload: dict[str, Any]

    @property
    def recommended(self) -> bool:
        """Whether the candidate is strong enough to recommend for review."""
        return self.confidence == LongTermCandidateConfidence.HIGH


def _slugify_session_part(value: str, label: str) -> str:
    """Normalize one session-id segment."""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string, got {type(value).__name__}")

    normalized = _SESSION_PART_RE.sub("-", value.strip().lower()).strip("-")
    if not normalized:
        raise ValueError(f"{label} must contain at least one alphanumeric character")
    return normalized


def build_coding_session_id(
    repo: str,
    task: str,
    *,
    run_id: str | None = None,
    prefix: str = "coding",
) -> str:
    """Build a task-scoped session identifier for coding workflows."""
    prefix_slug = _slugify_session_part(prefix, "prefix")
    repo_slug = _slugify_session_part(repo, "repo")
    task_slug = _slugify_session_part(task, "task")
    run_slug = _slugify_session_part(run_id, "run_id") if run_id is not None else uuid4().hex[:8]
    return f"{prefix_slug}/{repo_slug}/{task_slug}/{run_slug}"


class CodingAgentMemory:
    """Task-scoped helper around ``MemoryClient`` for coding-agent workflows."""

    def __init__(
        self,
        memory_client: "MemoryClient",
        *,
        repo: str,
        task: str,
        session_id: str | None = None,
        extract_entities_from_user_messages: bool = True,
    ):
        self._client = memory_client
        self._repo = _slugify_session_part(repo, "repo")
        self._task = validate_query(task)
        self._session_id = (
            validate_session_id(session_id)
            if session_id is not None
            else build_coding_session_id(repo, task)
        )
        self._extract_entities_from_user_messages = extract_entities_from_user_messages
        self._last_user_message_id: UUID | None = None
        self._active_trace_id: UUID | None = None
        self._active_step_id: UUID | None = None

    @property
    def session_id(self) -> str:
        """Return the task-scoped session id."""
        return self._session_id

    @property
    def repo(self) -> str:
        """Return the normalized repo slug."""
        return self._repo

    @property
    def task(self) -> str:
        """Return the human-readable task label."""
        return self._task

    @property
    def memory_client(self) -> "MemoryClient":
        """Return the wrapped ``MemoryClient``."""
        return self._client

    def _base_metadata(self) -> dict[str, Any]:
        return {
            "repo": self._repo,
            "task": self._task,
            "session_kind": "coding_task",
        }

    def _merge_metadata(self, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = self._base_metadata()
        if metadata:
            merged.update(metadata)
        return merged

    def _durable_scope_key(self, metadata: dict[str, Any] | None = None) -> tuple[str, str]:
        merged = self._merge_metadata(metadata)
        return (
            _normalize_durable_value(merged.get("scope_kind")),
            _normalize_durable_value(merged.get("repo")),
        )

    def _preference_scope_key(self, preference: "Preference") -> tuple[str, str]:
        return self._durable_scope_key(preference.metadata)

    def _fact_scope_key(self, fact: "Fact") -> tuple[str, str]:
        return self._durable_scope_key(fact.metadata)

    def _is_superseded(self, metadata: dict[str, Any] | None) -> bool:
        return (metadata or {}).get("status") == "superseded"

    def _build_active_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        active_metadata = dict(metadata)
        active_metadata.setdefault("status", "active")
        return active_metadata

    def _build_superseded_metadata(
        self,
        metadata: dict[str, Any] | None,
        *,
        superseded_by: UUID,
        reason: str,
    ) -> dict[str, Any]:
        updated = dict(metadata or {})
        updated["status"] = "superseded"
        updated["superseded_by"] = str(superseded_by)
        updated["superseded_at"] = datetime.now(UTC).isoformat()
        updated["supersession_reason"] = reason
        return updated

    def _repo_recall_metadata_match(self, metadata: dict[str, Any] | None) -> bool:
        """Whether durable memory should appear in repo-scoped coding recall."""
        normalized_scope = _normalize_durable_value((metadata or {}).get("scope_kind"))
        normalized_repo = _normalize_durable_value((metadata or {}).get("repo"))
        if normalized_scope == LongTermCandidateScopeKind.PERSONAL.value:
            return True
        return normalized_repo == self._repo

    def _filter_repo_recall_entries(self, entries: list[Any]) -> list[Any]:
        """Keep only durable entries relevant to the current repo recall."""
        return [
            entry
            for entry in entries
            if self._repo_recall_metadata_match(getattr(entry, "metadata", None))
        ]

    def _truncate_text(self, text: str | None, *, limit: int = 140) -> str:
        """Keep recall output compact."""
        if not text:
            return ""
        if len(text) <= limit:
            return text
        return f"{text[: limit - 3]}..."

    def _format_section(self, title: str, lines: list[str]) -> str:
        """Format one recall section when it has content."""
        if not lines:
            return ""
        return "\n".join([f"## {title}", *lines])

    def _format_reasoning_trace_lines(self, trace: "ReasoningTrace") -> list[str]:
        """Format one reasoning trace summary for startup recall fallback."""
        lines = [f"**Task**: {trace.task}"]
        if trace.outcome:
            lines.append(f"- Outcome: {self._truncate_text(trace.outcome)}")
        if trace.success is not None:
            lines.append(f"- Success: {'Yes' if trace.success else 'No'}")

        action = ""
        observation = ""
        tools: list[str] = []
        seen_tools: set[str] = set()
        for step in getattr(trace, "steps", []):
            if not action and getattr(step, "action", None):
                action = step.action
            if not observation and getattr(step, "observation", None):
                observation = step.observation
            for tool_call in getattr(step, "tool_calls", []):
                tool_name = getattr(tool_call, "tool_name", "")
                if tool_name and tool_name not in seen_tools:
                    seen_tools.add(tool_name)
                    tools.append(tool_name)

        if action:
            lines.append(f"- Key action: {self._truncate_text(action, limit=100)}")
        if tools:
            lines.append(f"- Tools: {', '.join(tools)}")
        if observation:
            lines.append(f"- Observation: {self._truncate_text(observation, limit=120)}")
        return lines

    async def _find_existing_preference(
        self,
        *,
        category: str,
        preference: str,
        context: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> "Preference | None":
        category_matches = await self._client.long_term.get_preferences_by_category(category)
        target_scope = self._durable_scope_key(metadata)
        target_preference = _normalize_durable_value(preference)
        target_context = _normalize_durable_value(context)

        for existing in category_matches:
            if self._is_superseded(existing.metadata):
                continue
            if self._preference_scope_key(existing) != target_scope:
                continue
            if _normalize_durable_value(existing.preference) != target_preference:
                continue
            if _normalize_durable_value(existing.context) != target_context:
                continue
            return existing
        return None

    async def _find_existing_entity(
        self,
        *,
        name: str,
        entity_type: str,
    ) -> "Entity | None":
        existing = await self._client.long_term.get_entity_by_name(name)
        if existing is None:
            return None
        if normalize_entity_type(existing.type) != normalize_entity_type(entity_type):
            return None
        return existing

    async def _find_existing_fact(
        self,
        *,
        subject: str,
        predicate: str,
        obj: str,
        metadata: dict[str, Any] | None = None,
    ) -> "Fact | None":
        subject_matches = await self._client.long_term.get_facts_about(subject)
        target_scope = self._durable_scope_key(metadata)
        target_predicate = _normalize_durable_value(predicate)
        target_object = _normalize_durable_value(obj)

        for existing in subject_matches:
            if self._is_superseded(existing.metadata):
                continue
            if self._fact_scope_key(existing) != target_scope:
                continue
            if _normalize_durable_value(existing.predicate) != target_predicate:
                continue
            if _normalize_durable_value(existing.object) != target_object:
                continue
            return existing
        return None

    async def _find_conflicting_preferences(
        self,
        *,
        category: str,
        preference: str,
        context: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> list["Preference"]:
        category_matches = await self._client.long_term.get_preferences_by_category(
            category,
            include_superseded=False,
        )
        target_scope = self._durable_scope_key(metadata)
        target_preference = _normalize_durable_value(preference)
        target_context = _normalize_durable_value(context)

        conflicts: list["Preference"] = []
        for existing in category_matches:
            if self._preference_scope_key(existing) != target_scope:
                continue
            if _normalize_durable_value(existing.context) != target_context:
                continue
            if _normalize_durable_value(existing.preference) == target_preference:
                continue
            conflicts.append(existing)
        return conflicts

    async def _find_conflicting_facts(
        self,
        *,
        subject: str,
        predicate: str,
        obj: str,
        metadata: dict[str, Any] | None = None,
    ) -> list["Fact"]:
        subject_matches = await self._client.long_term.get_facts_about(
            subject,
            include_superseded=False,
        )
        target_scope = self._durable_scope_key(metadata)
        target_predicate = _normalize_durable_value(predicate)
        target_object = _normalize_durable_value(obj)

        conflicts: list["Fact"] = []
        for existing in subject_matches:
            if self._fact_scope_key(existing) != target_scope:
                continue
            if _normalize_durable_value(existing.predicate) != target_predicate:
                continue
            if _normalize_durable_value(existing.object) == target_object:
                continue
            conflicts.append(existing)
        return conflicts

    async def _supersede_preferences(
        self,
        preferences: list["Preference"],
        *,
        superseded_by: UUID,
        reason: str,
    ) -> None:
        for preference in preferences:
            updated_metadata = self._build_superseded_metadata(
                preference.metadata,
                superseded_by=superseded_by,
                reason=reason,
            )
            await self._client.long_term.update_preference_metadata(preference.id, updated_metadata)
            await self._client.long_term.link_preference_supersession(
                preference.id,
                superseded_by,
                reason=reason,
            )

    async def _supersede_facts(
        self,
        facts: list["Fact"],
        *,
        superseded_by: UUID,
        reason: str,
    ) -> None:
        for fact in facts:
            updated_metadata = self._build_superseded_metadata(
                fact.metadata,
                superseded_by=superseded_by,
                reason=reason,
            )
            await self._client.long_term.update_fact_metadata(fact.id, updated_metadata)
            await self._client.long_term.link_fact_supersession(
                fact.id,
                superseded_by,
                reason=reason,
            )

    def _candidate_metadata(
        self,
        *,
        scope_kind: LongTermCandidateScopeKind,
        source: LongTermCandidateSource,
        evidence: str,
        confidence: LongTermCandidateConfidence,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        candidate_metadata = self._merge_metadata(metadata)
        candidate_metadata.update(
            {
                "scope_kind": scope_kind.value,
                "candidate_source": source.value,
                "candidate_evidence": evidence,
                "candidate_confidence": confidence.value,
            }
        )
        return candidate_metadata

    def _resolve_candidate_confidence(
        self,
        *,
        source: LongTermCandidateSource,
        durable: bool,
        reusable: bool,
        confidence: LongTermCandidateConfidence | None = None,
    ) -> LongTermCandidateConfidence:
        if confidence is not None:
            return confidence

        if not durable or not reusable:
            return LongTermCandidateConfidence.LOW

        if source.value in _STRONG_SOURCES:
            return LongTermCandidateConfidence.HIGH

        return LongTermCandidateConfidence.MEDIUM

    def _default_why_candidate(
        self,
        *,
        source: LongTermCandidateSource,
        durable: bool,
        reusable: bool,
    ) -> str:
        if source == LongTermCandidateSource.USER_EXPLICIT:
            source_reason = "Explicit user instruction"
        elif source == LongTermCandidateSource.CODE_VERIFIED:
            source_reason = "Confirmed in code"
        elif source == LongTermCandidateSource.DOCS_VERIFIED:
            source_reason = "Confirmed in documentation"
        elif source == LongTermCandidateSource.TEST_VERIFIED:
            source_reason = "Confirmed by tests"
        else:
            source_reason = "Observed during a real run"

        reuse_reason = "durable and reusable" if durable and reusable else "not durable enough yet"
        return f"{source_reason}; {reuse_reason} for future coding tasks."

    def _build_candidate(
        self,
        *,
        candidate_type: LongTermCandidateType,
        scope_kind: LongTermCandidateScopeKind,
        content: str,
        source: LongTermCandidateSource,
        evidence: str,
        payload: dict[str, Any],
        durable: bool,
        reusable: bool,
        why_candidate: str | None = None,
        confidence: LongTermCandidateConfidence | None = None,
    ) -> LongTermMemoryCandidate | None:
        resolved_confidence = self._resolve_candidate_confidence(
            source=source,
            durable=durable,
            reusable=reusable,
            confidence=confidence,
        )
        if resolved_confidence == LongTermCandidateConfidence.LOW:
            return None

        action = {
            LongTermCandidateType.FACT: "remember_fact",
            LongTermCandidateType.PREFERENCE: "remember_preference",
            LongTermCandidateType.ENTITY: "remember_entity",
        }[candidate_type]

        return LongTermMemoryCandidate(
            type=candidate_type,
            scope_kind=scope_kind,
            content=content,
            why_candidate=why_candidate
            or self._default_why_candidate(
                source=source,
                durable=durable,
                reusable=reusable,
            ),
            source=source,
            confidence=resolved_confidence,
            evidence=evidence,
            suggested_action=action,
            payload=payload,
        )

    async def add_user_message(
        self,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
        extract_entities: bool | None = None,
        generate_embedding: bool = True,
    ) -> "Message":
        """Store a user message in task-scoped short-term memory."""
        message = await self._client.short_term.add_message(
            session_id=self._session_id,
            role="user",
            content=content,
            metadata=self._merge_metadata(metadata),
            extract_entities=(
                self._extract_entities_from_user_messages
                if extract_entities is None
                else extract_entities
            ),
            generate_embedding=generate_embedding,
        )
        self._last_user_message_id = message.id
        return message

    async def add_assistant_message(
        self,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
        extract_entities: bool = False,
        generate_embedding: bool = True,
    ) -> "Message":
        """Store an assistant message in task-scoped short-term memory."""
        return await self._client.short_term.add_message(
            session_id=self._session_id,
            role="assistant",
            content=content,
            metadata=self._merge_metadata(metadata),
            extract_entities=extract_entities,
            generate_embedding=generate_embedding,
        )

    async def save_interaction(
        self,
        *,
        user_message: str,
        assistant_message: str,
        user_metadata: dict[str, Any] | None = None,
        assistant_metadata: dict[str, Any] | None = None,
        extract_user_entities: bool | None = None,
    ) -> tuple["Message", "Message"]:
        """Store a user/assistant pair for the current coding task."""
        user = await self.add_user_message(
            user_message,
            metadata=user_metadata,
            extract_entities=extract_user_entities,
        )
        assistant = await self.add_assistant_message(
            assistant_message,
            metadata=assistant_metadata,
        )
        return user, assistant

    async def remember_entity(
        self,
        name: str,
        entity_type: str,
        *,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
        resolve: bool = True,
        deduplicate: bool = True,
        enrich: bool = False,
        geocode: bool = False,
    ) -> tuple["Entity", Any]:
        """Store a curated long-term entity relevant to the coding workflow."""
        existing = await self._find_existing_entity(name=name, entity_type=entity_type)
        if existing is not None:
            return existing, None

        return await self._client.long_term.add_entity(
            name=name,
            entity_type=entity_type,
            description=description,
            metadata=self._merge_metadata(metadata),
            resolve=resolve,
            deduplicate=deduplicate,
            enrich=enrich,
            geocode=geocode,
        )

    async def remember_preference(
        self,
        category: str,
        preference: str,
        *,
        context: str | None = None,
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
        generate_embedding: bool = True,
        deduplicate: bool = True,
        supersede_conflicts: bool = True,
    ) -> "Preference":
        """Store a durable user or workflow preference."""
        merged_metadata = self._build_active_metadata(self._merge_metadata(metadata))
        if deduplicate:
            existing = await self._find_existing_preference(
                category=category,
                preference=preference,
                context=context,
                metadata=merged_metadata,
            )
            if existing is not None:
                return existing

        conflicts: list["Preference"] = []
        if supersede_conflicts:
            conflicts = await self._find_conflicting_preferences(
                category=category,
                preference=preference,
                context=context,
                metadata=merged_metadata,
            )
            if conflicts:
                merged_metadata["supersedes_ids"] = [str(item.id) for item in conflicts]

        created = await self._client.long_term.add_preference(
            category=category,
            preference=preference,
            context=context,
            confidence=confidence,
            metadata=merged_metadata,
            generate_embedding=generate_embedding,
        )
        if conflicts:
            await self._supersede_preferences(
                conflicts,
                superseded_by=created.id,
                reason=(
                    "Superseded by a newer preference in the same category, context, "
                    "and durable scope."
                ),
            )
        return created

    async def remember_fact(
        self,
        subject: str,
        predicate: str,
        obj: str,
        *,
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
        generate_embedding: bool = True,
        deduplicate: bool = True,
        supersede_conflicts: bool = True,
    ) -> "Fact":
        """Store a durable long-term fact for the coding workflow."""
        merged_metadata = self._build_active_metadata(self._merge_metadata(metadata))
        if deduplicate:
            existing = await self._find_existing_fact(
                subject=subject,
                predicate=predicate,
                obj=obj,
                metadata=merged_metadata,
            )
            if existing is not None:
                return existing

        conflicts: list["Fact"] = []
        if supersede_conflicts:
            conflicts = await self._find_conflicting_facts(
                subject=subject,
                predicate=predicate,
                obj=obj,
                metadata=merged_metadata,
            )
            if conflicts:
                merged_metadata["supersedes_ids"] = [str(item.id) for item in conflicts]

        created = await self._client.long_term.add_fact(
            subject=subject,
            predicate=predicate,
            obj=obj,
            confidence=confidence,
            metadata=merged_metadata,
            generate_embedding=generate_embedding,
        )
        if conflicts:
            await self._supersede_facts(
                conflicts,
                superseded_by=created.id,
                reason=(
                    "Superseded by a newer fact with the same subject, predicate, "
                    "and durable scope."
                ),
            )
        return created

    def propose_fact_candidate(
        self,
        *,
        subject: str,
        predicate: str,
        obj: str,
        source: LongTermCandidateSource,
        evidence: str,
        scope_kind: LongTermCandidateScopeKind = LongTermCandidateScopeKind.REPO,
        durable: bool = True,
        reusable: bool = True,
        why_candidate: str | None = None,
        confidence: LongTermCandidateConfidence | None = None,
        memory_confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
        generate_embedding: bool = True,
    ) -> LongTermMemoryCandidate | None:
        """Propose a durable fact candidate without writing it."""
        content = f"{subject} {predicate} {obj}"
        resolved_confidence = self._resolve_candidate_confidence(
            source=source,
            durable=durable,
            reusable=reusable,
            confidence=confidence,
        )
        candidate_metadata = self._candidate_metadata(
            scope_kind=scope_kind,
            source=source,
            evidence=evidence,
            confidence=resolved_confidence,
            metadata=metadata,
        )
        return self._build_candidate(
            candidate_type=LongTermCandidateType.FACT,
            scope_kind=scope_kind,
            content=content,
            source=source,
            evidence=evidence,
            durable=durable,
            reusable=reusable,
            why_candidate=why_candidate,
            confidence=resolved_confidence,
            payload={
                "subject": subject,
                "predicate": predicate,
                "obj": obj,
                "confidence": memory_confidence,
                "metadata": candidate_metadata,
                "generate_embedding": generate_embedding,
            },
        )

    def propose_preference_candidate(
        self,
        *,
        category: str,
        preference: str,
        source: LongTermCandidateSource,
        evidence: str,
        context: str | None = None,
        scope_kind: LongTermCandidateScopeKind = LongTermCandidateScopeKind.REPO,
        durable: bool = True,
        reusable: bool = True,
        why_candidate: str | None = None,
        confidence: LongTermCandidateConfidence | None = None,
        memory_confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
        generate_embedding: bool = True,
    ) -> LongTermMemoryCandidate | None:
        """Propose a durable preference candidate without writing it."""
        resolved_confidence = self._resolve_candidate_confidence(
            source=source,
            durable=durable,
            reusable=reusable,
            confidence=confidence,
        )
        candidate_metadata = self._candidate_metadata(
            scope_kind=scope_kind,
            source=source,
            evidence=evidence,
            confidence=resolved_confidence,
            metadata=metadata,
        )
        return self._build_candidate(
            candidate_type=LongTermCandidateType.PREFERENCE,
            scope_kind=scope_kind,
            content=preference,
            source=source,
            evidence=evidence,
            durable=durable,
            reusable=reusable,
            why_candidate=why_candidate,
            confidence=resolved_confidence,
            payload={
                "category": category,
                "preference": preference,
                "context": context,
                "confidence": memory_confidence,
                "metadata": candidate_metadata,
                "generate_embedding": generate_embedding,
            },
        )

    def propose_entity_candidate(
        self,
        *,
        name: str,
        entity_type: str,
        source: LongTermCandidateSource,
        evidence: str,
        description: str | None = None,
        scope_kind: LongTermCandidateScopeKind = LongTermCandidateScopeKind.REPO,
        durable: bool = True,
        reusable: bool = True,
        why_candidate: str | None = None,
        confidence: LongTermCandidateConfidence | None = None,
        metadata: dict[str, Any] | None = None,
        resolve: bool = True,
        deduplicate: bool = True,
        enrich: bool = False,
        geocode: bool = False,
    ) -> LongTermMemoryCandidate | None:
        """Propose a durable entity candidate without writing it."""
        resolved_confidence = self._resolve_candidate_confidence(
            source=source,
            durable=durable,
            reusable=reusable,
            confidence=confidence,
        )
        candidate_metadata = self._candidate_metadata(
            scope_kind=scope_kind,
            source=source,
            evidence=evidence,
            confidence=resolved_confidence,
            metadata=metadata,
        )
        return self._build_candidate(
            candidate_type=LongTermCandidateType.ENTITY,
            scope_kind=scope_kind,
            content=name,
            source=source,
            evidence=evidence,
            durable=durable,
            reusable=reusable,
            why_candidate=why_candidate,
            confidence=resolved_confidence,
            payload={
                "name": name,
                "entity_type": entity_type,
                "description": description,
                "metadata": candidate_metadata,
                "resolve": resolve,
                "deduplicate": deduplicate,
                "enrich": enrich,
                "geocode": geocode,
            },
        )

    async def remember_candidate(
        self,
        candidate: LongTermMemoryCandidate,
        *,
        allow_medium_confidence: bool = False,
    ) -> "Entity | Preference | Fact":
        """Persist a reviewed long-term candidate explicitly."""
        if (
            candidate.confidence == LongTermCandidateConfidence.MEDIUM
            and not allow_medium_confidence
        ):
            raise ValueError(
                "Medium-confidence candidates require explicit override "
                "(allow_medium_confidence=True) before writing long-term memory."
            )

        if candidate.type == LongTermCandidateType.FACT:
            return await self.remember_fact(**candidate.payload)
        if candidate.type == LongTermCandidateType.PREFERENCE:
            return await self.remember_preference(**candidate.payload)
        if candidate.type == LongTermCandidateType.ENTITY:
            entity, _ = await self.remember_entity(**candidate.payload)
            return entity
        raise ValueError(f"Unsupported candidate type: {candidate.type}")

    async def start_trace(
        self,
        *,
        task: str | None = None,
        metadata: dict[str, Any] | None = None,
        generate_embedding: bool = True,
        triggered_by_message_id: UUID | str | None = None,
    ) -> "ReasoningTrace":
        """Start a reasoning trace for the current coding task."""
        trace = await self._client.reasoning.start_trace(
            session_id=self._session_id,
            task=task or self._task,
            metadata=self._merge_metadata(metadata),
            generate_embedding=generate_embedding,
            triggered_by_message_id=triggered_by_message_id or self._last_user_message_id,
        )
        self._active_trace_id = trace.id
        self._active_step_id = None
        return trace

    async def add_trace_step(
        self,
        *,
        thought: str | None = None,
        action: str | None = None,
        observation: str | None = None,
        metadata: dict[str, Any] | None = None,
        generate_embedding: bool = True,
        trace_id: UUID | None = None,
    ) -> "ReasoningStep":
        """Add one reasoning step to the active trace."""
        resolved_trace_id = trace_id or self._active_trace_id
        if resolved_trace_id is None:
            raise RuntimeError("No active trace. Call start_trace() first.")

        step = await self._client.reasoning.add_step(
            resolved_trace_id,
            thought=thought,
            action=action,
            observation=observation,
            metadata=self._merge_metadata(metadata),
            generate_embedding=generate_embedding,
        )
        self._active_step_id = step.id
        return step

    async def record_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        result: Any | None = None,
        status: ToolCallStatus = ToolCallStatus.SUCCESS,
        duration_ms: int | None = None,
        error: str | None = None,
        auto_observation: bool = False,
        step_id: UUID | None = None,
        message_id: UUID | str | None = None,
    ) -> "ToolCall":
        """Record one tool call under the active reasoning step."""
        resolved_step_id = step_id or self._active_step_id
        if resolved_step_id is None:
            raise RuntimeError("No active reasoning step. Call add_trace_step() first.")

        return await self._client.reasoning.record_tool_call(
            resolved_step_id,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            status=status,
            duration_ms=duration_ms,
            error=error,
            auto_observation=auto_observation,
            message_id=message_id or self._last_user_message_id,
        )

    async def complete_trace(
        self,
        *,
        outcome: str | None = None,
        success: bool | None = None,
        generate_step_embeddings: bool = False,
        trace_id: UUID | None = None,
    ) -> "ReasoningTrace":
        """Complete the active reasoning trace."""
        resolved_trace_id = trace_id or self._active_trace_id
        if resolved_trace_id is None:
            raise RuntimeError("No active trace. Call start_trace() first.")

        trace = await self._client.reasoning.complete_trace(
            resolved_trace_id,
            outcome=outcome,
            success=success,
            generate_step_embeddings=generate_step_embeddings,
        )
        if trace_id is None or trace_id == self._active_trace_id:
            self._active_trace_id = None
            self._active_step_id = None
        return trace

    async def get_context(
        self,
        query: str | None = None,
        *,
        include_short_term: bool = True,
        include_long_term: bool = True,
        include_reasoning: bool = True,
        max_items: int = 10,
    ) -> str:
        """Get combined context for the current coding task."""
        return await self._client.get_context(
            query=query or self._task,
            session_id=self._session_id,
            include_short_term=include_short_term,
            include_long_term=include_long_term,
            include_reasoning=include_reasoning,
            max_items=max_items,
        )

    async def get_startup_recall(
        self,
        query: str | None = None,
        *,
        recent_messages: int = 6,
        max_preferences: int = 5,
        max_facts: int = 5,
        max_entities: int = 5,
        max_traces: int = 3,
    ) -> str:
        """Get a coding-oriented startup recall for the current task."""
        recall_query = validate_query(query) if query is not None else self._task

        sections = [
            self._format_section(
                "Task Frame",
                [
                    f"- Repo: {self._repo}",
                    f"- Task: {self._task}",
                    f"- Session: {self._session_id}",
                    f"- Recall query: {recall_query}",
                ],
            )
        ]

        conversation = await self._client.short_term.get_conversation(
            self._session_id,
            limit=max(recent_messages, 1),
        )
        recent_lines: list[str] = []
        for message in conversation.messages[-recent_messages:]:
            role = getattr(message.role, "value", str(message.role))
            if role not in {"user", "assistant", "system"}:
                continue
            recent_lines.append(
                f"- [{role}] {self._truncate_text(getattr(message, 'content', ''), limit=180)}"
            )
        sections.append(self._format_section("Active Task Stream", recent_lines))

        preferences = self._filter_repo_recall_entries(
            await self._client.long_term.search_preferences(
                recall_query,
                limit=max_preferences,
                threshold=0.0,
            )
        )
        if not preferences:
            preferences = self._filter_repo_recall_entries(
                await self._client.long_term.list_preferences(
                    repo=self._repo,
                    include_personal=True,
                    limit=max_preferences,
                )
            )
        preference_lines = []
        for preference in preferences:
            line = f"- [{preference.category}] {self._truncate_text(preference.preference, limit=140)}"
            if preference.context:
                line += f" (context: {self._truncate_text(preference.context, limit=80)})"
            preference_lines.append(line)
        sections.append(self._format_section("Durable Preferences", preference_lines))

        facts = self._filter_repo_recall_entries(
            await self._client.long_term.search_facts(
                recall_query,
                limit=max_facts,
                threshold=0.0,
            )
        )
        if not facts:
            facts = self._filter_repo_recall_entries(
                await self._client.long_term.list_facts(
                    repo=self._repo,
                    include_personal=True,
                    limit=max_facts,
                )
            )
        fact_lines = [
            f"- {self._truncate_text(fact.subject, limit=60)} {self._truncate_text(fact.predicate, limit=60)} "
            f"{self._truncate_text(fact.object, limit=140)}"
            for fact in facts
        ]
        sections.append(self._format_section("Durable Facts", fact_lines))

        entities = self._filter_repo_recall_entries(
            await self._client.long_term.search_entities(
                recall_query,
                limit=max_entities,
                threshold=0.0,
            )
        )
        if not entities:
            entities = self._filter_repo_recall_entries(
                await self._client.long_term.list_entities(
                    repo=self._repo,
                    include_personal=True,
                    limit=max_entities,
                )
            )
        entity_lines = []
        for entity in entities:
            line = f"- {entity.name} [{entity.type}]"
            if entity.description:
                line += f": {self._truncate_text(entity.description, limit=120)}"
            entity_lines.append(line)
        sections.append(self._format_section("Relevant Entities", entity_lines))

        reasoning_context = await self._client.reasoning.get_context(
            recall_query,
            max_traces=max_traces,
        )
        if not reasoning_context:
            session_traces = await self._client.reasoning.get_session_traces(
                self._session_id,
                limit=max_traces,
            )
            fallback_lines: list[str] = []
            for trace in session_traces:
                detailed_trace = await self._client.reasoning.get_trace(trace.id)
                fallback_lines.extend(self._format_reasoning_trace_lines(detailed_trace or trace))
                fallback_lines.append("")
            reasoning_context = "\n".join(fallback_lines).strip()
        if reasoning_context:
            sections.append(self._format_section("Similar Past Tasks", reasoning_context.splitlines()))

        return "\n\n".join(section for section in sections if section).strip()
