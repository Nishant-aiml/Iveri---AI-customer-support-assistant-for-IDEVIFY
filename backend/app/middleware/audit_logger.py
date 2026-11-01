import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("idevify.audit")

class AuditLoggerMiddleware(BaseHTTPMiddleware):
    """Assigns unique X-Request-ID to every request and logs security-relevant metrics."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        
        # 1. Extract or generate unique Request ID
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id

        # 2. Process request
        response: Response = await call_next(request)

        # 3. Compute execution time
        latency_ms = int((time.time() - start_time) * 1000)

        # 4. Attach Request ID to response
        response.headers["X-Request-ID"] = request_id

        # 5. Security & operational logging (Never log passwords or auth tokens)
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        status_code = response.status_code

        if status_code == 429:
            logger.warning(f"[RATE_LIMIT_TRIPPED] req_id={request_id} ip={client_ip} path={path} latency={latency_ms}ms")
        elif status_code >= 500:
            logger.error(f"[SERVER_ERROR] req_id={request_id} ip={client_ip} path={path} status={status_code} latency={latency_ms}ms")
        elif path.startswith("/api/auth"):
            logger.info(f"[AUTH_EVENT] req_id={request_id} ip={client_ip} path={path} status={status_code} latency={latency_ms}ms")

        return response
