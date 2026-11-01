import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.routers import auth, business

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("idevify-rag")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database Tables
    logger.info("Starting up Iveri AI Customer Support Assistant backend...")
    await init_db()
    yield
    # Shutdown
    logger.info("Shutting down backend services...")

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

# Mount Core Routers
app.include_router(auth.router)
app.include_router(business.router)

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
