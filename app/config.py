"""Configuration settings for client-connector."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment.

    Env-only configuration (`.map.env` → `.secret.env` → `.env.local`, see
    `.cline/rules/env-policy.md`): no defaults for env-backed values — missing
    required vars fail fast at boot.
    """

    model_config = SettingsConfigDict(
        env_file=(".map.env", ".secret.env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server
    host: str = Field(alias="HOST")
    port: int = Field(alias="CLIENT_CONNECTOR_PORT")
    debug: bool = Field(alias="DEBUG")



    # Authentication
    auth_middleware_url: str = Field(alias="AUTH_MIDDLEWARE_URL")
    auth_grpc_addr: str = Field(alias="AUTH_GRPC_ADDR")
    api_key_header: str = Field(alias="API_KEY_HEADER")

    # Database
    database_url: str = Field(alias="DATABASE_URL")

    # Rate Limiting
    rate_limit_per_minute: int = Field(alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_burst: int = Field(alias="RATE_LIMIT_BURST")
    tier_rate_limits: dict[str, dict[str, int]] = Field(alias="TIER_RATE_LIMITS")

    # Session
    session_timeout_minutes: int = Field(alias="SESSION_TIMEOUT_MINUTES")
    max_concurrent_clients: int = Field(alias="MAX_CONCURRENT_CLIENTS")

    # Logging
    log_level: str = Field(alias="LOG_LEVEL")
    log_format: Literal["json", "console"] = Field(alias="LOG_FORMAT")

    # Downstream Services (for MCP gateway operations)
    data_vent_url: str = Field(alias="DATA_VENT_URL")

    # Arc memory-unit service (Rust, port 3006) — authoritative memory store
    arc_service_url: str = Field(alias="ARC_SERVICE_URL")

    # CORS
    cors_origins: str = Field(alias="CORS_ORIGINS")

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins as list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
