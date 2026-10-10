"""Arc memory-unit client — thin transport to the Arc memory service.

The memory unit implementation (models, durable store, retrieval, lifecycle)
lives in the Arc Rust service (``Arc/``, crate ``arc-memory``). This module is
only the transport used by the MCP gateway and REST layer and keeps the same
call surface the routes and tools already use. Arc owns the authoritative
``arc_*`` store, so there is exactly one copy of each record.
"""

from typing import Any

import httpx
import structlog

from app.config import get_settings
from app.schemas.arc import (
    ArcMemory,
    ArcMemoryInput,
    ArcSession,
    ArcSessionEvent,
    ArcSessionEventInput,
    ArcSessionInput,
    EvidenceSpan,
    EvidenceSpanInput,
    MemoryCorrectionInput,
    RecallQuery,
    SessionFinishInput,
)

logger = structlog.get_logger()

REQUEST_TIMEOUT = 30.0


class ArcError(Exception):
    """Error raised by the Arc memory service (mapped to HTTP by the router)."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class ArcCaller:
    """Identity of the caller for scope enforcement (spec §14).

    ``principal_id`` is the authenticated user (REST) or agent identity (MCP).
    Scope checks run inside Arc *before* results are returned — never as
    post-filtering of already-leaked content.
    """

    def __init__(
        self,
        workspace_id: str,
        principal_id: str | None = None,
        session_id: str | None = None,
    ):
        self.workspace_id = workspace_id
        self.principal_id = principal_id
        self.session_id = session_id


class ArcStore:
    """HTTP client for the Arc memory-unit service (Rust, port 3006)."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or get_settings().arc_service_url).rstrip("/")

    # ── transport ─────────────────────────────────────────────────────────

    def _params(self, caller: ArcCaller | None, extra: dict | None = None) -> dict:
        params: dict[str, Any] = {}
        if caller is not None:
            params["workspace_id"] = caller.workspace_id
            if caller.principal_id:
                params["principal_id"] = caller.principal_id
            if caller.session_id:
                params["session_id"] = caller.session_id
        if extra:
            params.update({k: v for k, v in extra.items() if v not in (None, "")})
        return params

    async def _request(
        self,
        method: str,
        path: str,
        caller: ArcCaller | None = None,
        body: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        query = self._params(caller, params)
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.request(
                    method,
                    f"{self.base_url}{path}",
                    params=query or None,
                    json=body,
                )
        except httpx.HTTPError as exc:
            raise ArcError(f"Arc memory service unreachable: {exc}", 503) from exc
        if resp.status_code >= 400:
            try:
                message = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                message = resp.text
            raise ArcError(message or f"Arc error {resp.status_code}",
                           resp.status_code)
        return resp.json()

    # ── sessions ──────────────────────────────────────────────────────────

    async def start_session(
        self, payload: ArcSessionInput, caller: ArcCaller
    ) -> ArcSession:
        """Create a session, or identify an existing one by external ID (§8.1)."""
        body = payload.model_dump(mode="json")
        body["principal_id"] = payload.principal_id or caller.principal_id
        data = await self._request("POST", "/api/v1/memory/sessions", caller, body)
        return ArcSession(**data["session"])

    async def get_session_state(
        self, session_id: str, caller: ArcCaller, event_limit: int = 10
    ) -> dict:
        """Session + compact handoff + recent events + linked memories."""
        return await self._request(
            "GET",
            f"/api/v1/memory/sessions/{session_id}",
            caller,
            params={"event_limit": event_limit},
        )

    async def append_event(
        self, session_id: str, payload: ArcSessionEventInput, caller: ArcCaller
    ) -> ArcSessionEvent:
        """Append an event to the session history (append-only)."""
        body = payload.model_dump(mode="json")
        body["actor_id"] = payload.actor_id or caller.principal_id
        data = await self._request(
            "POST", f"/api/v1/memory/sessions/{session_id}/events", caller, body
        )
        return ArcSessionEvent(**data["event"])

    async def summarize_session(
        self, session_id: str, payload: SessionFinishInput, caller: ArcCaller
    ) -> ArcSession:
        """Create or update the concise session summary."""
        data = await self._request(
            "POST",
            f"/api/v1/memory/sessions/{session_id}/summarize",
            caller,
            payload.model_dump(mode="json"),
        )
        return ArcSession(**data["session"])

    async def finish_session(
        self, session_id: str, payload: SessionFinishInput, caller: ArcCaller
    ) -> ArcSession:
        """Finish, pause or hand off a session (history preserved)."""
        data = await self._request(
            "POST",
            f"/api/v1/memory/sessions/{session_id}/finish",
            caller,
            payload.model_dump(mode="json"),
        )
        return ArcSession(**data["session"])

    async def search_sessions(
        self, query: str, caller: ArcCaller, limit: int = 10
    ) -> list[ArcSession]:
        """Find prior sessions by text, task or identifier."""
        data = await self._request(
            "GET",
            "/api/v1/memory/sessions/search",
            caller,
            params={"q": query, "limit": limit},
        )
        return [ArcSession(**s) for s in data.get("sessions", [])]

    # ── memory units ──────────────────────────────────────────────────────

    async def record_memory(
        self, payload: ArcMemoryInput, caller: ArcCaller, owner_id: str | None = None
    ) -> ArcMemory:
        """Persist a memory unit with provenance, keys and evidence links."""
        body = payload.model_dump(mode="json")
        body["owner_id"] = owner_id or caller.principal_id
        data = await self._request("POST", "/api/v1/memory/units", caller, body)
        return ArcMemory(**data["memory"])

    async def link_evidence(
        self, memory_id: str, ev: EvidenceSpanInput, caller: ArcCaller
    ) -> EvidenceSpan:
        """Associate a new evidence span with a memory unit."""
        data = await self._request(
            "POST",
            f"/api/v1/memory/units/{memory_id}/evidence",
            caller,
            ev.model_dump(mode="json"),
        )
        return EvidenceSpan(**data["evidence"])

    async def get_memory(
        self, caller: ArcCaller, memory_id: str | None = None,
        canonical_key: str | None = None,
    ) -> dict:
        """Retrieve one memory unit by ID or canonical key (Path A)."""
        if memory_id:
            return await self._request(
                "GET", f"/api/v1/memory/units/{memory_id}", caller
            )
        if canonical_key:
            return await self._request(
                "GET", "/api/v1/memory/units/key", caller,
                params={"key": canonical_key},
            )
        raise ArcError("memory_id or canonical_key required")

    async def correct_memory(
        self, memory_id: str, correction: MemoryCorrectionInput, caller: ArcCaller
    ) -> dict:
        """Mark a memory incorrect/contradicted/superseded — history preserved."""
        return await self._request(
            "POST",
            f"/api/v1/memory/units/{memory_id}/correct",
            caller,
            correction.model_dump(mode="json"),
        )

    async def recall(self, query: RecallQuery, caller: ArcCaller) -> list[dict]:
        """Retrieve relevant memories via keyed, lexical and session paths."""
        body = query.model_dump(mode="json")
        body.setdefault("principal_id", caller.principal_id)
        body.setdefault("session_id", caller.session_id)
        data = await self._request("POST", "/api/v1/memory/recall", caller, body)
        return data.get("results", [])


