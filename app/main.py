"""Client Connector — MCP endpoint for AI agents.

Hosts MCP connections from AI agents (Cursor, Claude, Windsurf, etc.)
and routes knowledge queries to data-vent for FalkorDB retrieval.
"""

from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv

# Load environment variables from .map.env (non-sensitive), .secret.env (sensitive),
# and .env.local — same loader pattern as doc-data-con / repo-data-con. Required
# because app.mcp_server reads raw os.environ values (see env-policy.md).
load_dotenv(".map.env")
load_dotenv(".secret.env", override=True)
load_dotenv(".env.local", override=True)

import structlog
from fastapi import Depends, FastAPI, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth import AuthUser, get_current_user
from app.config import get_settings
from app.infra.db.postgres import close_postgresql, init_postgresql
from app.services import get_session_manager, shutdown_session_manager

# Configure structured logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Client Connector service")

    try:
        # Initialize database
        await init_postgresql()
        logger.info("PostgreSQL initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize PostgreSQL", error=str(e))
        # Continue without database for degraded mode
        logger.warning("Client Connector starting in degraded mode without database")

    try:
        # Start session manager
        await get_session_manager()
        logger.info("Session manager started")
    except Exception as e:
        logger.error("Failed to start session manager", error=str(e))
        logger.warning("Client Connector starting without session manager")

    settings = get_settings()
    logger.info(
        "Client Connector ready",
        host=settings.host,
        port=settings.port,
    )

    yield

    logger.info("Shutting down Client Connector")
    try:
        await shutdown_session_manager()
    except Exception as e:
        logger.error("Error shutting down session manager", error=str(e))
    
    try:
        await close_postgresql()
    except Exception as e:
        logger.error("Error closing PostgreSQL", error=str(e))
    
    logger.info("Client Connector stopped")


class CorrelationIdMiddleware:
    """Middleware to extract or generate a correlation ID and bind it to structlog."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        headers = dict(scope.get("headers", []))
        correlation_id = headers.get(b"x-correlation-id", uuid4().hex.encode()).decode("utf-8")

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        async def send_wrapper(message):
            try:
                if message["type"] == "http.response.start":
                    # Add the correlation ID to the response headers
                    res_headers = message.setdefault("headers", [])
                    res_headers.append((b"x-correlation-id", correlation_id.encode("utf-8")))
                await send(message)
            except RuntimeError as e:
                if "Unexpected ASGI message" in str(e):
                    # Suppress Uvicorn error caused by FastMCP returning a Response
                    # after EventSourceResponse has already completed the request.
                    pass
                else:
                    raise

        try:
            await self.app(scope, receive, send_wrapper)
        except RuntimeError as e:
            if "Unexpected ASGI message" in str(e):
                pass
            else:
                raise


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Client Connector",
        description="MCP endpoint for AI Agents — connects to ConFuse knowledge layer",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Correlation ID
    app.add_middleware(CorrelationIdMiddleware)

    # Mount routers
    from app.mcp_server import get_mcp_app
    from app.routing import arc_router

    # Arc memory engine REST API (sessions, memories, recall, context capsules)
    app.include_router(arc_router)

    # Using a versioned, fixed API endpoint for MCP
    app.mount("/api/v1/mcp", get_mcp_app().sse_app())

    # Root endpoint for UptimeRobot
    @app.api_route("/", methods=["GET", "HEAD"])
    async def root_check() -> dict[str, str]:
        """Root endpoint for basic health monitoring."""
        return {"status": "ok"}

    # Health endpoint
    @app.get("/health")
    async def health_check() -> dict[str, Any]:
        """Health check endpoint."""
        session_manager = await get_session_manager()
        stats = await session_manager.get_stats()

        return {
            "status": "healthy",
            "service": "client-connector",
            "sessions": stats,
        }

    # Admin endpoints
    @app.get("/admin/sessions")
    async def list_sessions(
        user: AuthUser = Depends(get_current_user),
    ) -> dict[str, Any]:
        """List all active sessions (admin only)."""
        if not user.has_role("admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin role required",
            )

        session_manager = await get_session_manager()
        sessions = await session_manager.list_sessions()

        return {
            "sessions": [
                {
                    "id": str(s.id),
                    "state": s.state.value,
                    "client": s.client_info.model_dump() if s.client_info else None,
                    "user_id": s.user_id,
                    "connected_at": s.connected_at.isoformat(),
                    "last_activity": s.last_activity.isoformat(),
                    "request_count": s.request_count,
                }
                for s in sessions
            ],
            "total": len(sessions),
        }

    @app.get("/admin/stats")
    async def get_stats(
        user: AuthUser = Depends(get_current_user),
    ) -> dict[str, Any]:
        """Get service statistics (admin only)."""
        if not user.has_role("admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin role required",
            )

        session_manager = await get_session_manager()
        return await session_manager.get_stats()

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
