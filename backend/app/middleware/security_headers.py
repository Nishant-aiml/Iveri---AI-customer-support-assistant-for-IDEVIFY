from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds standard production HTTP security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # 1. Prevent MIME-Type Sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # 2. Clickjacking & Frame Protection:
        # Dashboard is strictly protected (SAMEORIGIN or DENY)
        # Standalone customer chat & widget allow embedding
        path = request.url.path
        if path.startswith("/dashboard") or path.startswith("/api/dashboard") or path.startswith("/api/business"):
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
        elif path.startswith("/widget.js") or path.startswith("/chat/"):
            # Permitted for widget integration on customer sites
            pass
        else:
            response.headers["X-Frame-Options"] = "SAMEORIGIN"

        # 3. Referrer Privacy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 4. Restrict Sensitive Browser Hardware Capabilities
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        # 5. Cross-Origin Opener Policy for Dashboard
        if path.startswith("/dashboard"):
            response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

        return response
