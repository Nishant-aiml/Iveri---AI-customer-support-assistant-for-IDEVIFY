import os
import sys
import logging

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.middleware import SecurityHeadersMiddleware, SlidingWindowRateLimiter, AuditLoggerMiddleware
from app.routers import auth, business, documents, chat, dashboard, public_share
from app.services.ingestion_queue import ingestion_queue
from app.services.bm25_store import bm25_store_service

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
    if settings.ENVIRONMENT == "production":
        if settings.JWT_SECRET == "super-secret-jwt-key-change-in-production-123456" or len(settings.JWT_SECRET) < 32:
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

@app.get("/widget.js", tags=["Widget"])
async def serve_widget_script():
    """Serves the standalone embeddable chat widget script."""
    widget_path = os.path.join(os.path.dirname(__file__), "static", "widget.js")
    return FileResponse(widget_path, media_type="application/javascript")

@app.get("/dashboard", tags=["UI"])
@app.get("/", tags=["UI"])
async def serve_dashboard_ui():
    """Serves the Business Owner Analytics and Management Portal."""
    index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    return FileResponse(index_path, media_type="text/html")

@app.get("/chat/{slug}", tags=["UI"])
async def serve_customer_chat_ui(slug: str):
    """Serves the Customer Support Chat Web Application."""
    chat_path = os.path.join(os.path.dirname(__file__), "static", "chat.html")
    return FileResponse(chat_path, media_type="text/html")

@app.get("/share/{session_id}", tags=["UI"])
@app.get("/share/unanswered/{unanswered_id}", tags=["UI"])
async def serve_shared_chat_ui(session_id: str = None, unanswered_id: str = None):
    """Serves the Public Read-Only Share Permalink Page."""
    share_path = os.path.join(os.path.dirname(__file__), "static", "share.html")
    return FileResponse(share_path, media_type="text/html")
