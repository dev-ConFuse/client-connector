"""Arc memory engine — typed contracts.

Pydantic models for the Arc persistent memory engine (sessions, memories,
evidence) and the unified Context Capsule output format. Field names follow
the canonical spec (snake_case, explicit optionality); physical storage lives
in ``app.services.arc_store``.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────


class MemoryType(str, Enum):
    """Logical memory classification (spec §7.1)."""

    EPISODIC = "episodic"       # what happened
    SEMANTIC = "semantic"       # what is understood
    PROCEDURAL = "procedural"   # how work should be done
    DECISION = "decision"       # why a choice was made
    SESSION = "session"         # what an agent was doing


class MemoryStatus(str, Enum):
    """Lifecycle state. Corrections never delete history."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    CONTRADICTED = "contradicted"
    RETRACTED = "retracted"


class MemoryScope(str, Enum):
    """Access scope. Scope is never widened automatically."""

    SESSION_PRIVATE = "session_private"
    USER_PRIVATE = "user_private"
    PROJECT = "project"
    REPOSITORY = "repository"
    WORKSPACE = "workspace"
    ORGANIZATION = "organization"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    FINISHED = "finished"
    HANDED_OFF = "handed_off"


class CorrectionAction(str, Enum):
    """Action applied by ``arc_correct_memory``."""

    SUPERSEDE = "supersede"
    CONTRADICT = "contradict"
    RETRACT = "retract"


class EvidenceKind(str, Enum):
    """How an observation was obtained — never interchangeable (spec §5.4)."""

    COMPILER_INDEX = "compiler_index"
    STATIC_ANALYSIS = "static_analysis"
    DEPENDENCY_MANIFEST = "dependency_manifest"
    API_SCHEMA_DECLARATION = "api_schema_declaration"
    DOCUMENTATION = "documentation"
    GIT_HISTORY = "git_history"
    TEST_RESULT = "test_result"
    DIRECT_OBSERVATION = "direct_observation"
    LLM_INFERENCE = "llm_inference"
    SEMANTIC_SIMILARITY = "semantic_similarity"


# ─────────────────────────────────────────────────────────────────────────────
# Evidence
# ─────────────────────────────────────────────────────────────────────────────


class EvidenceSpan(BaseModel):
    """A source-grounded span supporting a memory (spec §5.4)."""

    id: UUID = Field(default_factory=uuid4)
    memory_id: UUID | None = None
    source_artifact_id: str | None = None
    source_snapshot_id: str | None = None
    locator: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    section_or_range: str | None = None
    supporting_content: str | None = None
    observation_method: EvidenceKind = EvidenceKind.DIRECT_OBSERVATION
    observed_at: datetime = Field(default_factory=datetime.utcnow)


class EvidenceSpanInput(BaseModel):
    """Input for linking new evidence to a memory."""

    source_artifact_id: str | None = None
    source_snapshot_id: str | None = None
    locator: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    section_or_range: str | None = None
    supporting_content: str | None = None
    observation_method: EvidenceKind = EvidenceKind.DIRECT_OBSERVATION


# ─────────────────────────────────────────────────────────────────────────────
# Memories
# ─────────────────────────────────────────────────────────────────────────────


class ArcMemory(BaseModel):
    """Canonical memory record (spec §7.4)."""

    id: UUID = Field(default_factory=uuid4)
    workspace_id: str
    scope: MemoryScope = MemoryScope.WORKSPACE
    memory_type: MemoryType

    title: str
    summary: str | None = None
    content: str

    canonical_key: str | None = None
    lookup_keys: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    related_memory_ids: list[UUID] = Field(default_factory=list)

    source_ids: list[str] = Field(default_factory=list)
    source_revisions: list[str] = Field(default_factory=list)
    session_id: UUID | None = None

    status: MemoryStatus = MemoryStatus.ACTIVE
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence_reason: str | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    observed_at: datetime | None = None
    last_accessed_at: datetime | None = None

    valid_from: datetime | None = None
    valid_to: datetime | None = None
    supersedes_id: UUID | None = None
    superseded_at: datetime | None = None

    content_hash: str | None = None
    extractor_or_writer_version: str | None = None


class ArcMemoryInput(BaseModel):
    """Request payload for ``arc_record_memory``."""

    workspace_id: str
    memory_type: MemoryType
    title: str
    content: str
    summary: str | None = None
    scope: MemoryScope = MemoryScope.WORKSPACE
    canonical_key: str | None = None
    lookup_keys: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    related_memory_ids: list[UUID] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    source_revisions: list[str] = Field(default_factory=list)
    session_id: UUID | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence_reason: str | None = None
    evidence: list[EvidenceSpanInput] = Field(default_factory=list)
    writer_version: str | None = None


class MemoryCorrectionInput(BaseModel):
    """Request payload for ``arc_correct_memory`` — preserves history."""

    action: CorrectionAction
    reason: str
    replacement: ArcMemoryInput | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Sessions
# ─────────────────────────────────────────────────────────────────────────────


class ArcSession(BaseModel):
    """Durable agent-work session (spec §8.1) — not a login/connection session."""

    id: UUID = Field(default_factory=uuid4)
    workspace_id: str
    scope: MemoryScope = MemoryScope.WORKSPACE

    external_session_id: str | None = None
    agent_provider: str | None = None
    agent_runtime: str | None = None
    principal_id: str | None = None

    title: str | None = None
    task_summary: str | None = None
    status: SessionStatus = SessionStatus.ACTIVE

    parent_session_id: UUID | None = None
    root_repository_id: str | None = None
    root_revision: str | None = None

    started_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: datetime | None = None

    handoff_summary: str | None = None
    next_steps: str | None = None
    unresolved_questions: str | None = None


class ArcSessionInput(BaseModel):
    """Request payload to start (or identify) a session."""

    workspace_id: str
    title: str | None = None
    task_summary: str | None = None
    scope: MemoryScope = MemoryScope.WORKSPACE
    external_session_id: str | None = None
    agent_provider: str | None = None
    agent_runtime: str | None = None
    principal_id: str | None = None
    parent_session_id: UUID | None = None
    root_repository_id: str | None = None
    root_revision: str | None = None


class ArcSessionEvent(BaseModel):
    """Append-only session activity record (spec §8.1)."""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    sequence_number: int
    event_type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    actor_id: str | None = None
    source_artifact_ids: list[str] = Field(default_factory=list)
    memory_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArcSessionEventInput(BaseModel):
    """Request payload for ``arc_session_append``."""

    event_type: str
    summary: str | None = None
    actor_id: str | None = None
    source_artifact_ids: list[str] = Field(default_factory=list)
    memory_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionFinishInput(BaseModel):
    """Request payload for ``arc_session_finish`` / summarize."""

    status: SessionStatus = SessionStatus.FINISHED
    title: str | None = None
    task_summary: str | None = None
    handoff_summary: str | None = None
    next_steps: str | None = None
    unresolved_questions: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Recall / Context Capsule
# ─────────────────────────────────────────────────────────────────────────────


class RecallQuery(BaseModel):
    """Multi-path memory retrieval request (spec §7.2/§9)."""

    query: str
    workspace_id: str
    session_id: UUID | None = None
    principal_id: str | None = None
    memory_types: list[MemoryType] = Field(default_factory=list)
    include_history: bool = False
    limit: int = Field(default=10, ge=1, le=50)


class ContextCapsuleItem(BaseModel):
    """One source-grounded unit inside a Context Capsule (spec §10)."""

    id: str
    kind: Literal["code_chunk", "document_section", "graph_fact", "memory"]
    content: str
    summary: str | None = None

    source_uri: str | None = None
    source_revision: str | None = None
    locator: str | None = None

    relationship_path: str | None = None
    related_entity_ids: list[str] = Field(default_factory=list)

    memory_type: MemoryType | None = None
    session_id: UUID | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)

    evidence_kind: EvidenceKind | None = None
    confidence: float | None = None
    confidence_reason: str | None = None
    validity_status: str = "current"
    freshness: str | None = None

    relevance_score: float = 0.0
    token_estimate: int = 0


class ContextCapsule(BaseModel):
    """Compact, source-grounded query result (spec §10) — not a DB record."""

    query_id: UUID = Field(default_factory=uuid4)
    workspace_id: str
    session_id: UUID | None = None
    scope: MemoryScope = MemoryScope.WORKSPACE

    task_anchors: list[str] = Field(default_factory=list)
    items: list[ContextCapsuleItem] = Field(default_factory=list)

    unresolved_questions: list[str] = Field(default_factory=list)
    omitted_count: int = 0
    generated_at: datetime = Field(default_factory=datetime.utcnow)
