"""Services module."""

from .prompt_compressor import CompressedQuery, PromptCompressor
from .session import (
    ClientSession,
    SessionManager,
    get_session_manager,
    shutdown_session_manager,
)
from .toggle_client import FeatureToggleClient, get_toggle_client, is_feature_enabled

# Arc memory engine — thin HTTP client to the Arc memory-unit service
# (`Arc/`, crate `arc-memory`), which owns the authoritative `arc_*` store.
from .arc_store import (  # noqa: F401
    ArcCaller,
    ArcError,
    ArcStore,
)
from .retrieval_coordinator import RetrievalCoordinator  # noqa: F401

__all__ = [
    "FeatureToggleClient",
    "get_toggle_client",
    "is_feature_enabled",
    "ClientSession",
    "SessionManager",
    "get_session_manager",
    "shutdown_session_manager",
    "PromptCompressor",
    "CompressedQuery",
    "ArcCaller",
    "ArcError",
    "ArcStore",
    "RetrievalCoordinator",
]
