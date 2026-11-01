from collections import defaultdict
import json
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

logger = logging.getLogger("idevify.ratelimit")

class SlidingWindowRateLimiter(BaseHTTPMiddleware):
    """In-memory sliding-window rate limiter protecting against DDoS, brute force, and quota drainage."""

    def __init__(self, app):
        super().__init__(app)
        # Dictionary mapping key -> list of float timestamps
        self.request_history: dict[str, list[float]] = defaultdict(list)
        self.last_cleanup = time.time()

        # Path rules: (prefix, max_requests, window_seconds)
        self.rules = [
            ("/api/auth/login", 15, 60),
            ("/api/auth/register", 15, 60),
            ("/api/chat/message", 45, 60),
            ("/api/documents/upload", 15, 600),
            ("/api/", 180, 60),
        ]

        # Whitelist / Bypassed endpoints (static assets, health checks)
        self.exempt_paths = {
            "/api/health",
            "/widget.js",
            "/dashboard",
            "/",
        }

    def _cleanup_expired(self, current_time: float):
        """Periodically purges old timestamps to prevent memory leakage."""
        if current_time - self.last_cleanup > 300:  # Every 5 minutes
            keys_to_remove = []
            for key, timestamps in self.request_history.items():
                self.request_history[key] = [t for t in timestamps if current_time - t < 600]
                if not self.request_history[key]:
                    keys_to_remove.append(key)
            for k in keys_to_remove:
                del self.request_history[k]
            self.last_cleanup = current_time

    async def dispatch(self, request: Request, call_next) -> Response:
        # 0. Bypass rate limiting in automated testing environment (unless explicitly evaluating rate limits)
        if settings.ENVIRONMENT == "testing" and request.headers.get("X-Test-Rate-Limit") != "true":
            return await call_next(request)

        path = request.url.path

        # 1. Skip exempt paths or chat page assets
        if path in self.exempt_paths or path.startswith("/chat/"):
            return await call_next(request)

        # 2. Extract client IP
        client_ip = request.client.host if request.client else "127.0.0.1"

        # 3. Match rate limiting rule
        matched_rule = None
        for prefix, max_reqs, window_sec in self.rules:
            if path.startswith(prefix):
                matched_rule = (prefix, max_reqs, window_sec)
                break

        if not matched_rule:
            return await call_next(request)

        prefix, max_requests, window_seconds = matched_rule
        now = time.time()
        self._cleanup_expired(now)

        key = f"{client_ip}:{prefix}"
        timestamps = self.request_history[key]

        # Filter timestamps within current sliding window
        valid_timestamps = [t for t in timestamps if now - t < window_seconds]
        self.request_history[key] = valid_timestamps

        # 4. Check if limit exceeded
        if len(valid_timestamps) >= max_requests:
            oldest = valid_timestamps[0]
            retry_after = max(1, int(window_seconds - (now - oldest)))
            logger.warning(f"Rate limit exceeded for IP {client_ip} on '{path}'. Retry-After: {retry_after}s")

            return Response(
                content=json.dumps({
                    "detail": f"Rate limit exceeded. Maximum {max_requests} requests allowed per {window_seconds}s. Please retry in {retry_after} seconds."
                }),
                status_code=429,
                media_type="application/json",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0"
                }
            )

        # 5. Record request and proceed
        self.request_history[key].append(now)
        remaining = max(0, max_requests - len(self.request_history[key]))

        response: Response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
