"""Authentication middleware and utilities."""

import time
from typing import Annotated, Any

import grpc
import httpx
import structlog
from fastapi import Depends, Header, HTTPException, Request, status

try:
    from app.proto import auth_v1_pb2, auth_v1_pb2_grpc
except ImportError:
    try:
        from proto import auth_v1_pb2, auth_v1_pb2_grpc
    except ImportError:
        auth_v1_pb2 = None
        auth_v1_pb2_grpc = None

from app.config import Settings, get_settings

logger = structlog.get_logger()


class AuthUser:
    """Authenticated user from JWT or API key."""

    def __init__(
        self,
        user_id: str,
        email: str | None = None,
        roles: list[str] | None = None,
        api_key_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        subscription_tier: str = "free",
    ):
        self.user_id = user_id
        self.email = email
        self.roles = roles or []
        self.api_key_id = api_key_id
        self.metadata = metadata or {}
        self.subscription_tier = subscription_tier or "free"

    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        return role in self.roles

    def __repr__(self) -> str:
        return f"AuthUser(user_id={self.user_id}, email={self.email}, tier={self.subscription_tier})"


class RateLimiter:
    """Tier-aware in-memory rate limiter."""

    def __init__(
        self,
        tier_limits: dict[str, dict[str, int]] | None = None,
        limit_per_minute: int = 60,
        burst: int = 10,
    ):
        self.tier_limits = tier_limits or {
            "free": {"per_minute": limit_per_minute, "burst": burst},
            "pro": {"per_minute": 240, "burst": 20},
            "team": {"per_minute": 480, "burst": 30},
            "enterprise": {"per_minute": 1000, "burst": 50},
        }
        self.limit_per_minute = limit_per_minute
        self.burst = burst
        self._requests: dict[str, list[float]] = {}

    def get_limits_for_tier(self, tier: str = "free") -> dict[str, int]:
        """Get rate limits for specific tier."""
        tier_key = (tier or "free").lower()
        return self.tier_limits.get(
            tier_key,
            self.tier_limits.get("free", {"per_minute": 60, "burst": 10}),
        )

    def is_allowed(self, key: str, tier: str = "free") -> bool:
        """Check if request is allowed for the given key and subscription tier."""
        now = time.time()
        window_start = now - 60  # 1 minute window

        limits = self.get_limits_for_tier(tier)
        per_minute = limits.get("per_minute", self.limit_per_minute)

        # Clean old requests
        if key in self._requests:
            self._requests[key] = [t for t in self._requests[key] if t > window_start]
        else:
            self._requests[key] = []

        # Check rate
        if len(self._requests[key]) >= per_minute:
            return False

        # Record request
        self._requests[key].append(now)
        return True

    def get_remaining(self, key: str, tier: str = "free") -> int:
        """Get remaining requests for the key and subscription tier."""
        now = time.time()
        window_start = now - 60

        limits = self.get_limits_for_tier(tier)
        per_minute = limits.get("per_minute", self.limit_per_minute)

        if key not in self._requests:
            return per_minute

        recent = [t for t in self._requests[key] if t > window_start]
        return max(0, per_minute - len(recent))

    def get_reset_time(self, key: str) -> float:
        """Get timestamp when the oldest request in the window will expire."""
        if key not in self._requests or not self._requests[key]:
            return time.time()
        return self._requests[key][0] + 60


# Global rate limiter
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get rate limiter singleton."""
    global _rate_limiter
    if _rate_limiter is None:
        settings = get_settings()
        _rate_limiter = RateLimiter(
            tier_limits=settings.tier_rate_limits,
            limit_per_minute=settings.rate_limit_per_minute,
            burst=settings.rate_limit_burst,
        )
    return _rate_limiter


async def validate_jwt_token(
    token: str,
    settings: Settings,
) -> AuthUser | None:
    """Validate JWT token against auth-middleware service (prefers gRPC)."""
    # Try gRPC if available
    if auth_v1_pb2_grpc and auth_v1_pb2:
        try:
            auth_grpc_addr = settings.auth_grpc_addr
            async with grpc.aio.insecure_channel(auth_grpc_addr) as channel:
                stub = auth_v1_pb2_grpc.AuthStub(channel)
                request = auth_v1_pb2.ValidateTokenRequest(token=token)
                response = await stub.ValidateToken(request, timeout=2.0)

                if response.valid:
                    subscription_tier = getattr(response, "subscription_tier", "free") or "free"
                    return AuthUser(
                        user_id=response.user_id,
                        email=response.email,
                        roles=list(response.roles),
                        subscription_tier=subscription_tier,
                    )
        except grpc.RpcError as e:
            logger.warning(
                "Auth gRPC failed for token validation, falling back to local/HTTP", error=str(e)
            )
        except Exception as e:
            logger.error("Unexpected gRPC error during token validation", error=str(e))

    return None


async def validate_api_key(
    api_key: str,
    settings: Settings,
) -> AuthUser | None:
    """Validate API key against auth-middleware service (prefers gRPC)."""
    # Try gRPC if available
    if auth_v1_pb2_grpc and auth_v1_pb2:
        try:
            auth_grpc_addr = settings.auth_grpc_addr
            async with grpc.aio.insecure_channel(auth_grpc_addr) as channel:
                stub = auth_v1_pb2_grpc.AuthStub(channel)
                request = auth_v1_pb2.ValidateApiKeyRequest(api_key=api_key)
                response = await stub.ValidateApiKey(request, timeout=2.0)

                if response.valid:
                    subscription_tier = getattr(response, "subscription_tier", "free") or "free"
                    return AuthUser(
                        user_id=response.user_id,
                        email=response.email,
                        roles=list(response.roles),
                        api_key_id=response.key_id,
                        subscription_tier=subscription_tier,
                    )
        except grpc.RpcError as e:
            logger.warning("Auth gRPC failed for API key, falling back to HTTP", error=str(e))
        except Exception as e:
            logger.error("Unexpected gRPC error during API key validation", error=str(e))

    # Fallback to HTTP
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.auth_middleware_url}/api/auth/validate-key",
                json={"api_key": api_key},
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                return AuthUser(
                    user_id=data.get("user_id", ""),
                    email=data.get("email"),
                    roles=data.get("roles", []),
                    api_key_id=data.get("key_id"),
                    subscription_tier=data.get("subscription_tier", "free"),
                )
    except Exception as e:
        logger.error("API key validation failed", error=str(e))

    return None


async def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> AuthUser:
    """FastAPI dependency for authenticated user with tier-based rate limiting."""
    client_ip = request.client.host if request.client else "unknown"

    # Try JWT token
    user = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        user = await validate_jwt_token(token, settings)

    # Try API key
    if not user and x_api_key:
        user = await validate_api_key(x_api_key, settings)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Enforce tier-based rate limiting
    rate_limiter = get_rate_limiter()
    rate_key = user.user_id or client_ip
    tier = user.subscription_tier or "free"

    if not rate_limiter.is_allowed(rate_key, tier):
        limits = rate_limiter.get_limits_for_tier(tier)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded for {tier} tier ({limits.get('per_minute', 60)} req/min)",
            headers={
                "Retry-After": "60",
                "X-RateLimit-Limit": str(limits.get("per_minute", 60)),
                "X-RateLimit-Remaining": "0",
            },
        )

    return user


async def get_optional_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> AuthUser | None:
    """FastAPI dependency for optional authenticated user."""
    try:
        return await get_current_user(request, authorization, x_api_key, settings)
    except HTTPException:
        return None
