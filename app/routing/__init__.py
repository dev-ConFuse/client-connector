"""Routers package — FastAPI routers mounted by ``app.main``."""

from app.routing.arc_routes import router as arc_router

__all__ = ["arc_router"]
