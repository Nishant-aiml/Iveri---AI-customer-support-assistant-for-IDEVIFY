import logging
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.config import settings

logger = logging.getLogger(__name__)

# Normalize DATABASE_URL for async drivers if needed
database_url = settings.DATABASE_URL
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif database_url.startswith("postgresql://") and not database_url.startswith("postgresql+asyncpg://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif database_url.startswith("sqlite:///") and not database_url.startswith("sqlite+aiosqlite:///"):
    database_url = database_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

# Normalize SSL parameters for cloud PostgreSQL (Render, Neon, Supabase, AWS RDS)
# asyncpg accepts ssl=require / ssl=prefer / ssl=verify-full
if "postgresql+asyncpg" in database_url and "sslmode=" in database_url:
    database_url = database_url.replace("sslmode=require", "ssl=require").replace("sslmode=prefer", "ssl=prefer").replace("sslmode=verify-full", "ssl=verify-full")

# Configure Engine according to database backend
if "sqlite" in database_url:
    # High-concurrency SQLite setup: WAL mode + busy_timeout
    engine = create_async_engine(
        database_url,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False, "timeout": 60}
    )

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=60000")
            cursor.close()
        except Exception as e:
            logger.warning(f"Failed to apply SQLite WAL pragmas: {e}")

    logger.info("Database configured with SQLite (WAL mode enabled for concurrent read/write throughput).")
else:
    # Enterprise PostgreSQL setup with asyncpg connection pool & auto-reconnect
    pg_connect_args = {}
    if "ssl=require" in database_url or "sslmode=require" in settings.DATABASE_URL or "supabase" in database_url:
        import ssl
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        pg_connect_args["ssl"] = ssl_ctx

    # Supabase Supavisor / PgBouncer pooler (port 6543 or pooler hostname) requires statement_cache_size=0 for asyncpg
    if ":6543" in database_url or "pooler.supabase.com" in database_url:
        pg_connect_args["statement_cache_size"] = 0

    engine = create_async_engine(
        database_url,
        echo=False,
        future=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_pre_ping=True,
        connect_args=pg_connect_args if pg_connect_args else {}
    )
    logger.info(
        f"Database configured with PostgreSQL asyncpg connection pool "
        f"(pool_size={settings.DB_POOL_SIZE}, max_overflow={settings.DB_MAX_OVERFLOW})."
    )

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for providing database sessions per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    """Initializes tables in database and applies non-destructive column migrations."""
    async with engine.begin() as conn:
        # Import all models here so metadata is fully populated
        import app.models  # noqa
        await conn.run_sync(Base.metadata.create_all)

        # Safe schema auto-migration for newly added columns in SQLite
        try:
            if "sqlite" in database_url:
                # Helper for conditional column addition
                async def add_column_if_missing(table_name: str, col_name: str, col_type: str):
                    r = await conn.execute(text(f"PRAGMA table_info({table_name})"))
                    cols = [row[1] for row in r.fetchall()]
                    if col_name not in cols:
                        await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"))
                        logger.info(f"Migrated {table_name}: added {col_name} column.")

                # users migrations
                await add_column_if_missing("users", "firebase_uid", "VARCHAR(128)")
                await add_column_if_missing("users", "auth_provider", "VARCHAR(50) DEFAULT 'local'")

                # documents migrations
                await add_column_if_missing("documents", "total_pages", "INTEGER DEFAULT 0")
                await add_column_if_missing("documents", "processed_pages", "INTEGER DEFAULT 0")
                await add_column_if_missing("documents", "processing_progress", "INTEGER DEFAULT 0")

                # businesses migrations
                await add_column_if_missing("businesses", "avatar_url", "VARCHAR(512) DEFAULT ''")
                await add_column_if_missing("businesses", "widget_position", "VARCHAR(20) DEFAULT 'bottom-right'")
                await add_column_if_missing("businesses", "welcome_message", "TEXT DEFAULT 'Hello! How can I help you today?'")
                await add_column_if_missing("businesses", "custom_prompt", "TEXT DEFAULT ''")
                await add_column_if_missing("businesses", "whatsapp_number", "VARCHAR(50) DEFAULT ''")
                await add_column_if_missing("businesses", "enable_whatsapp", "BOOLEAN DEFAULT 1")
                await add_column_if_missing("businesses", "enable_callback", "BOOLEAN DEFAULT 1")
                await add_column_if_missing("businesses", "callback_channel", "VARCHAR(50) DEFAULT 'phone_and_email'")
                await add_column_if_missing("businesses", "callback_button_text", "VARCHAR(100) DEFAULT 'Request Callback'")

                # chat_messages migrations
                await add_column_if_missing("chat_messages", "sentiment", "VARCHAR(20) DEFAULT 'neutral'")
                await add_column_if_missing("chat_messages", "topic", "VARCHAR(50) DEFAULT 'general'")

                # chat_sessions migrations
                await add_column_if_missing("chat_sessions", "sentiment", "VARCHAR(20) DEFAULT 'neutral'")
                await add_column_if_missing("chat_sessions", "primary_topic", "VARCHAR(50) DEFAULT 'general'")
            else:
                # PostgreSQL native ADD COLUMN IF NOT EXISTS (supported on all modern PostgreSQL engines)
                pg_migrations = [
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS firebase_uid VARCHAR(128)",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(50) DEFAULT 'local'",
                    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS total_pages INTEGER DEFAULT 0",
                    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS processed_pages INTEGER DEFAULT 0",
                    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS processing_progress INTEGER DEFAULT 0",
                    "ALTER TABLE businesses ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(512) DEFAULT ''",
                    "ALTER TABLE businesses ADD COLUMN IF NOT EXISTS widget_position VARCHAR(20) DEFAULT 'bottom-right'",
                    "ALTER TABLE businesses ADD COLUMN IF NOT EXISTS welcome_message TEXT DEFAULT 'Hello! How can I help you today?'",
                    "ALTER TABLE businesses ADD COLUMN IF NOT EXISTS custom_prompt TEXT DEFAULT ''",
                    "ALTER TABLE businesses ADD COLUMN IF NOT EXISTS whatsapp_number VARCHAR(50) DEFAULT ''",
                    "ALTER TABLE businesses ADD COLUMN IF NOT EXISTS enable_whatsapp BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE businesses ADD COLUMN IF NOT EXISTS enable_callback BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE businesses ADD COLUMN IF NOT EXISTS callback_channel VARCHAR(50) DEFAULT 'phone_and_email'",
                    "ALTER TABLE businesses ADD COLUMN IF NOT EXISTS callback_button_text VARCHAR(100) DEFAULT 'Request Callback'",
                    "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS sentiment VARCHAR(20) DEFAULT 'neutral'",
                    "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS topic VARCHAR(50) DEFAULT 'general'",
                    "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS sentiment VARCHAR(20) DEFAULT 'neutral'",
                    "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS primary_topic VARCHAR(50) DEFAULT 'general'"
                ]
                for stmt in pg_migrations:
                    await conn.execute(text(stmt))
                logger.info("PostgreSQL cloud schema verified and auto-migrated.")
        except Exception as e:
            logger.warning(f"Column migration check note: {e}")

    logger.info("Database initialized successfully.")

async def get_database_health() -> dict[str, Any]:
    """Checks database connectivity and returns telemetry."""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            val = result.scalar()
            is_postgres = "postgres" in database_url
            return {
                "status": "healthy" if val == 1 else "unhealthy",
                "database_type": "postgresql" if is_postgres else "sqlite",
                "driver": "asyncpg" if is_postgres else "aiosqlite",
                "concurrency_mode": "connection_pool" if is_postgres else "wal_journal",
                "pool_size": settings.DB_POOL_SIZE if is_postgres else 1,
                "max_overflow": settings.DB_MAX_OVERFLOW if is_postgres else 0
            }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }
