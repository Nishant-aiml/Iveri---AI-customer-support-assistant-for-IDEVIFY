import os
import sys
import logging

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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
    yield
    # Shutdown
    logger.info("Shutting down backend services...")
    await ingestion_queue.shutdown()

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

@app.get("/manifest.json", tags=["PWA"])
async def serve_pwa_manifest():
    """Serves the Progressive Web App Manifest."""
    return FileResponse(os.path.join(_static_dir, "manifest.json"), media_type="application/manifest+json")

@app.get("/sw.js", tags=["PWA"])
async def serve_pwa_service_worker():
    """Serves the Progressive Web App Service Worker."""
    return FileResponse(os.path.join(_static_dir, "sw.js"), media_type="application/javascript")

@app.get("/widget.js", tags=["Widget"])
async def serve_widget_script():
    """Serves the standalone embeddable chat widget script."""
    return FileResponse(os.path.join(_static_dir, "widget.js"), media_type="application/javascript")

@app.get("/dashboard", tags=["UI"])
@app.get("/", tags=["UI"])
async def serve_dashboard_ui():
    """Serves the Business Owner Analytics and Management Portal."""
    return FileResponse(os.path.join(_static_dir, "index.html"), media_type="text/html")

@app.get("/chat/{slug}", tags=["UI"])
async def serve_customer_chat_ui(slug: str):
    """Serves the Customer Support Chat Web Application."""
    return FileResponse(os.path.join(_static_dir, "chat.html"), media_type="text/html")

@app.get("/share/{session_id}", tags=["UI"])
@app.get("/share/unanswered/{unanswered_id}", tags=["UI"])
async def serve_shared_chat_ui(session_id: str | None = None, unanswered_id: str | None = None):
    """Serves the Public Read-Only Share Permalink Page."""
    return FileResponse(os.path.join(_static_dir, "share.html"), media_type="text/html")
