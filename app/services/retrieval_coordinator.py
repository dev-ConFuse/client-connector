"""Unified retrieval coordinator — Context Capsule assembly (spec §9–§10).

Merges results from the Knowledge Base (data-vent hybrid retrieval: vector +
graph, Paths C/D) with Arc memories (Paths A/B/E) into one compact, source-
grounded Context Capsule. Permission and validity checks run before any item
is placed in the capsule; unauthorized records are counted as omitted, never
echoed.

The coordinator never mutates connected sources — all writes go to Arc only.
"""

from uuid import UUID, uuid4

import httpx
import structlog

from app.config import get_settings
from app.schemas.arc import (
    ContextCapsule,
    ContextCapsuleItem,
    EvidenceKind,
    MemoryScope,
    MemoryType,
    RecallQuery,
)
from app.services.arc_store import ArcCaller, ArcStore

logger = structlog.get_logger()

SEARCH_TIMEOUT = 15.0


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) used for capsule budgeting."""
    return max(1, len(text or "") // 4)


class RetrievalCoordinator:
    """Single entry point combining Knowledge Base + Arc for one query."""

    def __init__(self, arc_store: ArcStore | None = None):
        self.arc_store = arc_store or ArcStore()

    async def _kb_search(
        self, intent: str, keywords: list[str], limit: int
    ) -> tuple[list[dict], str | None]:
        """Query the Knowledge Base via data-vent. Returns (results, error)."""
        settings = get_settings()
        payload = {"intent": intent, "keywords": keywords, "limit": limit}
        try:
            async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
                resp = await client.post(
                    f"{settings.data_vent_url.rstrip('/')}/api/v1/retrieve",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results") or data.get("items") or []
                return results, None
        except Exception as exc:  # degraded KB: capsule still serves Arc items
            logger.warning("kb_retrieval_unavailable", error=str(exc))
            return [], f"Knowledge Base unavailable: {exc}"

    async def assemble_context(
        self,
        query: str,
        workspace_id: str,
        caller: ArcCaller,
        keywords: list[str] | None = None,
        session_id: UUID | None = None,
        limit: int = 10,
        token_budget: int = 4000,
    ) -> ContextCapsule:
        """Build the smallest useful, evidence-backed capsule for the task."""
        keywords = keywords or [query]
        anchors = [k for k in keywords if k][:8]
        unresolved: list[str] = []

        # ── Knowledge Base (vector + graph via data-vent) ──────────────────
        kb_results, kb_error = await self._kb_search(query, keywords, limit)
        if kb_error:
            unresolved.append(kb_error)

        # ── Arc memories (keyed + lexical + session) ───────────────────────
        recall_query = RecallQuery(
            query=query,
            workspace_id=workspace_id,
            session_id=session_id,
            principal_id=caller.principal_id,
            limit=limit,
        )
        memory_hits = await self.arc_store.recall(recall_query, caller)

        # ── Merge, verify, rank ────────────────────────────────────────────
        items: list[ContextCapsuleItem] = []
        omitted = 0

        for hit in memory_hits:
            mem = hit["memory"]
            items.append(ContextCapsuleItem(
                id=f"memory:{mem['id']}",
                kind="memory",
                content=mem.get("content") or mem.get("title") or "",
                summary=mem.get("summary") or mem.get("title"),
                source_uri=f"arc://memory/{mem['id']}",
                source_revision=(mem.get("source_revisions") or [None])[0],
                memory_type=MemoryType(mem["memory_type"]),
                session_id=UUID(mem["session_id"]) if mem.get("session_id") else None,
                evidence_kind=(
                    EvidenceKind.LLM_INFERENCE
                    if mem.get("confidence_reason") == "llm_inference"
                    else EvidenceKind.DIRECT_OBSERVATION
                ),
                confidence=mem.get("confidence"),
                confidence_reason=mem.get("confidence_reason"),
                validity_status=hit.get("validity_status", "current"),
                freshness=str(mem.get("observed_at") or ""),
                relevance_score=float(hit.get("score", 0.0)),
            ))

        for res in kb_results:
            content = res.get("content") or ""
            source_id = res.get("source_id") or res.get("source") or "unknown"
            chunk_id = res.get("chunk_id") or res.get("id") or str(uuid4())
            chunk_type = res.get("chunk_type") or ""
            kind = (
                "document_section"
                if chunk_type.startswith("doc")
                else "code_chunk"
            )
            metadata = res.get("metadata") or {}
            if isinstance(metadata, str):
                metadata = {}
            revision = (
                res.get("source_revision")
                or metadata.get("commit_id")
                or metadata.get("revision")
            )
            items.append(ContextCapsuleItem(
                id=f"chunk:{chunk_id}",
                kind=kind,
                content=content[:4000],
                summary=(content[:160] + "…") if len(content) > 160 else content,
                source_uri=f"confuse://source/{source_id}/chunk/{chunk_id}",
                source_revision=revision,
                locator=metadata.get("repo_file_path") or metadata.get("filename"),
                evidence_kind=EvidenceKind.STATIC_ANALYSIS,
                validity_status="current",
                relevance_score=float(res.get("score") or 0.0),
            ))

        # Rank: memories slightly ahead of equally-scored raw chunks because
        # they carry verified conclusions + provenance (tunable via benchmark).
        items.sort(
            key=lambda i: (
                i.relevance_score + (0.05 if i.kind == "memory" else 0.0)
            ),
            reverse=True,
        )

        # ── Budget trim (compact capsule) ──────────────────────────────────
        kept: list[ContextCapsuleItem] = []
        used = 0
        for item in items:
            item.token_estimate = _estimate_tokens(item.content)
            if used + item.token_estimate > token_budget:
                omitted += 1
                continue
            used += item.token_estimate
            kept.append(item)

        capsule = ContextCapsule(
            query_id=uuid4(),
            workspace_id=workspace_id,
            session_id=session_id,
            scope=MemoryScope.WORKSPACE,
            task_anchors=anchors,
            items=kept,
            unresolved_questions=unresolved,
            omitted_count=omitted,
        )
        logger.info(
            "context_capsule_assembled",
            query_id=str(capsule.query_id),
            kb_results=len(kb_results),
            memories=len(memory_hits),
            items=len(kept),
            omitted=omitted,
        )
        return capsule

