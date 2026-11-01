import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.routers import auth, business, documents, chat
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
    await init_db()
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

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(auth.router)
app.include_router(business.router)
app.include_router(documents.router)
app.include_router(chat.router)

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
