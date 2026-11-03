import os
import sys
import logging

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.middleware import (
    AuditLoggerMiddleware,
    SecurityHeadersMiddleware,
    SlidingWindowRateLimiter,
)
from app.routers import auth, business, chat, dashboard, documents, notifications, public_share, tickets, twilio, whatsapp
from app.services.bm25_store import bm25_store_service
from app.services.ingestion_queue import ingestion_queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("idevify-rag")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up Iveri AI Customer Support Assistant backend...")
    
    # Secret Entropy Guard
    if settings.ENVIRONMENT == "production" and (
        settings.JWT_SECRET == "super-secret-jwt-key-change-in-production-123456" or len(settings.JWT_SECRET) < 32
    ):
        logger.warning("SECURITY ALERT: Production environment is using default or weak JWT_SECRET! Generate a 32+ character secret.")

    await init_db()
    await bm25_store_service.warmup_from_db()
    ingestion_queue.start()

    # Pre-warm Laya System 1 Neural Router to eliminate cold start latency on first request
    try:
        from app.services.laya_router import laya_service
        laya_service.classify_intent("startup warmup ping")
        logger.info("Laya System 1 Neural Router pre-warmed successfully.")
    except Exception as e:
        logger.warning(f"Laya neural router pre-warmup notice: {e}")

    yield
    # Shutdown
    logger.info("Shutting down backend services...")
    await ingestion_queue.shutdown()
    try:
        from app.services.llm_client import close_shared_client
        await close_shared_client()
    except Exception:
        pass

app = FastAPI(
    title="Iveri - AI Customer Support Assistant API",
    description="Multi-tenant, hybrid RAG platform with deterministic guardrails and dual-engine ingestion.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware (supports wildcard origin reflection for cross-origin widget embeds)
_allow_all = "*" in settings.cors_origins or len(settings.cors_origins) == 0
if _allow_all:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://.*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# HTTP Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)

# Request ID & Audit Logging Middleware
app.add_middleware(AuditLoggerMiddleware)

# In-Memory Rate Limiting (Anti-DoS & Brute Force Defense)
app.add_middleware(SlidingWindowRateLimiter)

# Response GZip Compression (Reduces payload sizes by ~80% for fast surfing)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Mount Routers
app.include_router(auth.router)
app.include_router(business.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(dashboard.router)
app.include_router(public_share.router)
app.include_router(tickets.router)
app.include_router(notifications.router)
app.include_router(whatsapp.router)
app.include_router(twilio.router)

@app.get("/api/health", tags=["Health"])
async def health_check():
    """Health check endpoint for Render and monitoring."""
    db_type = "PostgreSQL" if "postgres" in settings.DATABASE_URL else "SQLite"
    return {
        "status": "healthy",
        "service": "Iveri Customer Support Assistant",
        "environment": settings.ENVIRONMENT,
        "database": db_type,
        "primary_parser": "Sarvam Document Intelligence API",
        "fallback_parser": "PyMuPDF (fitz)"
    }

# Static Asset Directory
_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

@app.get("/favicon.ico", include_in_schema=False)
async def serve_favicon():
    """Serves the favicon or returns 204 no content to eliminate browser 404 console errors."""
    icon_path = os.path.join(_static_dir, "icons", "icon-192.png")
    if os.path.exists(icon_path):
        return FileResponse(icon_path, media_type="image/png")
    from fastapi.responses import Response
    return Response(status_code=204)

@app.get("/manifest.json", tags=["PWA"])
async def serve_pwa_manifest():
    """Serves the Progressive Web App Manifest."""
    return FileResponse(os.path.join(_static_dir, "manifest.json"), media_type="application/manifest+json")

@app.get("/sw.js", tags=["PWA"])
async def serve_pwa_service_worker():
    """Serves the Progressive Web App Service Worker."""
    return FileResponse(
        os.path.join(_static_dir, "sw.js"),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"}
    )

@app.get("/widget.js", tags=["Widget"])
@app.get("/static/widget.js", tags=["Widget"])
async def serve_widget_script():
    """Serves the standalone embeddable chat widget script with aggressive no-cache headers."""
    return FileResponse(
        os.path.join(_static_dir, "widget.js"),
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@app.get("/dashboard", tags=["UI"])
@app.get("/", tags=["UI"])
async def serve_dashboard_ui():
    """Serves the Business Owner Analytics and Management Portal."""
    return FileResponse(os.path.join(_static_dir, "index.html"), media_type="text/html")

@app.get("/chat/{slug}", tags=["UI"])
async def serve_customer_chat_ui(slug: str):
    """Serves the Customer Support Chat Web Application with zero-flicker SSR hydration."""
    html_path = os.path.join(_static_dir, "chat.html")
    if not os.path.exists(html_path):
        return FileResponse(html_path, media_type="text/html")

    try:
        from app.database import AsyncSessionLocal
        from app.models.business import Business
        from sqlalchemy import select
        async with AsyncSessionLocal() as db_session:
            stmt = select(Business).where(
                (Business.slug == slug) | (Business.share_token == slug)
            )
            biz = (await db_session.execute(stmt)).scalar_one_or_none()
            if biz:
                with open(html_path, "r", encoding="utf-8") as f:
                    html_content = f.read()

                import json
                import html

                brand_color = biz.brand_color or "#4F46E5"
                c = brand_color.lstrip('#')
                if len(c) == 3:
                    c = ''.join([x * 2 for x in c])
                try:
                    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
                except Exception:
                    r, g, b = 79, 70, 229

                theme_css = f"""
<style id="chat-dynamic-theme-styles">
  .bg-primary {{ background-color: {brand_color} !important; }}
  .hover\\:bg-primary-hover:hover {{ filter: brightness(0.92); }}
  .text-primary {{ color: {brand_color} !important; }}
  .border-primary {{ border-color: {brand_color} !important; }}
  .chat-bubble-user {{ background-color: {brand_color} !important; color: #FFFFFF !important; box-shadow: 0 2px 6px rgba({r}, {g}, {b}, 0.35) !important; }}
  .focus\\:border-primary:focus {{ border-color: {brand_color} !important; }}
  .focus\\:ring-primary\\/20:focus {{ --tw-ring-color: rgba({r}, {g}, {b}, 0.25) !important; }}
</style>
"""
                biz_payload = {
                    "id": biz.id,
                    "name": biz.name,
                    "slug": biz.slug,
                    "brand_color": brand_color,
                    "avatar_url": biz.avatar_url or "",
                    "welcome_message": biz.welcome_message or "",
                    "starter_questions": biz.starter_questions or [],
                    "enable_callback": bool(biz.enable_callback),
                    "callback_button_text": biz.callback_button_text or "Request Callback",
                    "whatsapp_number": biz.whatsapp_number or ""
                }
                bootstrap_script = f"""
<script id="__IVERI_BIZ_BOOTSTRAP__">
  window.__INITIAL_BIZ__ = {json.dumps(biz_payload)};
</script>
"""
                html_content = html_content.replace(
                    "<title>Iveri - Verified AI Customer Support Assistant</title>",
                    f"<title>{html.escape(biz.name)} - Verified AI Customer Support Assistant</title>"
                )
                html_content = html_content.replace("</head>", f"{theme_css}\n{bootstrap_script}\n</head>")

                html_content = html_content.replace(
                    'id="biz-name" class="font-bold text-sm sm:text-base tracking-tight text-on-surface leading-snug truncate max-w-[150px] sm:max-w-xs">Iveri Assistant</h1>',
                    f'id="biz-name" class="font-bold text-sm sm:text-base tracking-tight text-on-surface leading-snug truncate max-w-[150px] sm:max-w-xs">{html.escape(biz.name)}</h1>'
                )

                if biz.enable_callback:
                    cb_label = html.escape(biz.callback_button_text or "Request Callback")
                    html_content = html_content.replace(
                        '<button id="btn-request-callback" onclick="openCallbackModal()" class="hidden inline-flex',
                        '<button id="btn-request-callback" onclick="openCallbackModal()" class="inline-flex'
                    )
                    html_content = html_content.replace(
                        '<span id="label-request-callback">Request Callback</span>',
                        f'<span id="label-request-callback">{cb_label}</span>'
                    )

                if biz.welcome_message:
                    escaped_welcome = html.escape(biz.welcome_message)
                    html_content = html_content.replace(
                        'Hello! I am your AI Support Assistant, indexed directly from store policies, product catalogs, and operating manuals. What questions can I answer for you today?',
                        escaped_welcome
                    )

                if biz.avatar_url:
                    escaped_avatar = html.escape(biz.avatar_url)
                    escaped_name = html.escape(biz.name)
                    html_content = html_content.replace(
                        '<span class="material-symbols-outlined text-[20px] sm:text-[22px]">support_agent</span>',
                        f'<img src="{escaped_avatar}" alt="{escaped_name}" class="w-full h-full object-cover rounded-xl" onerror="this.onerror=null; this.parentElement.innerHTML=\'<span class=\\\'material-symbols-outlined text-[20px] sm:text-[22px]\\\'>support_agent</span>\';">'
                    )

                if not biz.starter_questions:
                    html_content = html_content.replace(
                        'id="starter-container" class="pl-0 sm:pl-11 space-y-2 pt-1"',
                        'id="starter-container" class="hidden pl-0 sm:pl-11 space-y-2 pt-1"'
                    )

                return HTMLResponse(content=html_content, media_type="text/html")
    except Exception as e:
        logger.warning(f"SSR chat hydration fallback for {slug}: {e}")

    return FileResponse(html_path, media_type="text/html")

@app.get("/share/{session_id}", tags=["UI"])
@app.get("/share/unanswered/{unanswered_id}", tags=["UI"])
async def serve_shared_chat_ui(session_id: str | None = None, unanswered_id: str | None = None):
    """Serves the Public Read-Only Share Permalink Page."""
    return FileResponse(os.path.join(_static_dir, "share.html"), media_type="text/html")
