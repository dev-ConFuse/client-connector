"""Arc REST API — sessions, memories, recall and Context Capsule (spec §11).

All routes are authenticated (``get_current_user``) and enforce workspace +
scope rules inside the Arc store before returning data. Writes only touch
ConFuse's own Arc records — connected sources stay read-only.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.auth import AuthUser, get_current_user
from app.schemas.arc import (
    ArcMemoryInput,
    ArcSessionEventInput,
    ArcSessionInput,
    EvidenceSpanInput,
    MemoryCorrectionInput,
    RecallQuery,
    SessionFinishInput,
)
from app.services.arc_store import ArcCaller, ArcError, ArcStore
from app.services.retrieval_coordinator import RetrievalCoordinator

router = APIRouter(prefix="/api/v1/arc", tags=["arc"])

_store = ArcStore()
_coordinator = RetrievalCoordinator(_store)


def _caller(
    user: AuthUser,
    workspace_id: str | None,
    session_id: str | None = None,
) -> ArcCaller:
    """Build the scope-enforcing caller identity for a request."""
    return ArcCaller(
        workspace_id=workspace_id or "",
        principal_id=user.user_id,
        session_id=session_id,
    )


def _ws_header(
    x_workspace_id: Annotated[str | None, Header(alias="X-Workspace-Id")] = None,
) -> str | None:
    return x_workspace_id


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def start_session(
    payload: ArcSessionInput,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Create or identify a durable agent session."""
    try:
        session = await _store.start_session(
            payload, _caller(user, payload.workspace_id)
        )
        return {"session": session.model_dump(mode="json")}
    except ArcError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/sessions/{session_id}")
async def resume_session(
    session_id: UUID,
    event_limit: int = Query(default=10, ge=1, le=100),
    workspace_id: str | None = Depends(_ws_header),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Resume a session: state, compact handoff, recent events, memories."""
    try:
        return await _store.get_session_state(
            str(session_id), _caller(user, workspace_id), event_limit
        )
    except ArcError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("/sessions/{session_id}/events", status_code=status.HTTP_201_CREATED)
async def append_session_event(
    session_id: UUID,
    payload: ArcSessionEventInput,
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-Id")] = None,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Append an event to the session history (append-only)."""
    try:
        event = await _store.append_event(
            str(session_id), payload, _caller(user, workspace_id, str(session_id))
        )
        return {"event": event.model_dump(mode="json")}
    except ArcError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("/sessions/{session_id}/summarize")
async def summarize_session(
    session_id: UUID,
    payload: SessionFinishInput,
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-Id")] = None,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Create or update the concise session summary."""
    try:
        session = await _store.summarize_session(
            str(session_id), payload, _caller(user, workspace_id, str(session_id))
        )
        return {"session": session.model_dump(mode="json")}
    except ArcError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("/sessions/{session_id}/finish")
async def finish_session(
    session_id: UUID,
    payload: SessionFinishInput,
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-Id")] = None,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Finish, pause or hand off a session (history preserved)."""
    try:
        session = await _store.finish_session(
            str(session_id), payload, _caller(user, workspace_id, str(session_id))
        )
        return {"session": session.model_dump(mode="json")}
    except ArcError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/sessions")
async def search_sessions(
    q: str = Query(default=""),
    workspace_id: str | None = Depends(_ws_header),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Find prior sessions by query, artifact, task or identifier."""
    if not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Workspace-Id header required",
        )
    sessions = await _store.search_sessions(q, _caller(user, workspace_id))
    return {"sessions": [s.model_dump(mode="json") for s in sessions]}


@router.post("/memories", status_code=status.HTTP_201_CREATED)
async def record_memory(
    payload: ArcMemoryInput,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Persist an internal Arc memory with declared type and provenance."""
    try:
        memory = await _store.record_memory(
            payload, _caller(user, payload.workspace_id, str(payload.session_id)
                             if payload.session_id else None),
            owner_id=user.user_id,
        )
        return {"memory": memory.model_dump(mode="json")}
    except ArcError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/memories/{memory_id}")
async def get_memory(
    memory_id: UUID,
    workspace_id: str | None = Depends(_ws_header),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve one memory by ID (with its evidence spans)."""
    try:
        return await _store.get_memory(
            _caller(user, workspace_id), memory_id=str(memory_id)
        )
    except ArcError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/memories")
async def get_memory_by_key(
    key: str = Query(description="canonical key or kind:value lookup key"),
    workspace_id: str | None = Depends(_ws_header),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Path A — deterministic lookup of a known memory by canonical key."""
    try:
        return await _store.get_memory(
            _caller(user, workspace_id), canonical_key=key
        )
    except ArcError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("/memories/{memory_id}/evidence", status_code=status.HTTP_201_CREATED)
async def link_evidence(
    memory_id: UUID,
    payload: EvidenceSpanInput,
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-Id")] = None,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Associate a source-grounded evidence span with a memory."""
    try:
        evidence = await _store.link_evidence(
            str(memory_id), payload, _caller(user, workspace_id)
        )
        return {"evidence": evidence.model_dump(mode="json")}
    except ArcError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("/memories/{memory_id}/correct")
async def correct_memory(
    memory_id: UUID,
    payload: MemoryCorrectionInput,
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-Id")] = None,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Mark a memory incorrect/contradicted/superseded — history preserved."""
    try:
        return await _store.correct_memory(
            str(memory_id), payload, _caller(user, workspace_id)
        )
    except ArcError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("/recall")
async def recall(
    payload: RecallQuery,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve relevant memories via keyed, lexical and session paths."""
    try:
        hits = await _store.recall(
            payload,
            _caller(user, payload.workspace_id, str(payload.session_id)
                    if payload.session_id else None),
        )
        return {"results": hits}
    except ArcError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("/context")
async def assemble_context(
    payload: dict[str, Any],
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Combine Knowledge Base results and Arc memories into a Context Capsule."""
    query = (payload.get("query") or "").strip()
    workspace_id = payload.get("workspace_id") or ""
    if not query or not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="query and workspace_id are required",
        )
    session_id = payload.get("session_id")
    try:
        capsule = await _coordinator.assemble_context(
            query=query,
            workspace_id=workspace_id,
            caller=_caller(user, workspace_id, str(session_id) if session_id else None),
            keywords=payload.get("keywords"),
            session_id=UUID(str(session_id)) if session_id else None,
            limit=int(payload.get("limit", 10)),
            token_budget=int(payload.get("token_budget", 4000)),
        )
        return {"capsule": capsule.model_dump(mode="json")}
    except ArcError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))

