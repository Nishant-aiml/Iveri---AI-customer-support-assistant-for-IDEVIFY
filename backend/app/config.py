import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    
    # Database URL & Enterprise Connection Pooling
    DATABASE_URL: str = "sqlite+aiosqlite:///./idevify.db"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # Firebase Authentication
    FIREBASE_PROJECT_ID: str = "idevify-2d7f1"
    FIREBASE_CREDENTIALS_JSON: str = ""
    FIREBASE_AUTH_ONLY: bool = False
    
    # JWT Security
    JWT_SECRET: str = "super-secret-jwt-key-change-in-production-123456"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    
    # Sarvam AI Document Intelligence API
    SARVAM_API_KEY: str = ""
    SARVAM_API_URL: str = "https://api.sarvam.ai"
    SARVAM_FALLBACK_API_KEY: str = ""
    
    # LLM Cascade Settings
    # Tier 1: Google Gemini (Generous Free Tier)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    
    # Tier 2: Sarvam AI LLM (Indic & Multilingual Freemium)
    SARVAM_LLM_KEY: str = ""
    SARVAM_LLM_MODEL: str = "sarvam-105b-conversations"
    SARVAM_LLM_URL: str = "https://api.sarvam.ai/v1"
    
    # Tier 3: Groq Freemium Cloud LPU (Zero Cost Open-Source Weights: Qwen / Allam)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "qwen/qwen3.8-27b"
    
    # Twilio WhatsApp Gateway
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_API_KEY_SID: str = ""
    TWILIO_API_KEY_SECRET: str = ""
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+14155238886"
    
    # Optional Tier: OpenAI (if configured)
    OPENAI_API_KEY: str = ""
    
    # Vector & Storage
    CHROMA_PERSIST_DIRECTORY: str = "./chroma_db"
    UPLOAD_DIRECTORY: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 25
    
    # RAG Tuning Parameters
    CONFIDENCE_THRESHOLD: float = 0.55
    RRF_K: int = 60
    TOP_K_CHUNKS: int = 8
    
    # CORS (set to * or comma-separated origins)
    ALLOWED_ORIGINS: str = "*"
    
    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Ensure critical local directories exist
os.makedirs(settings.UPLOAD_DIRECTORY, exist_ok=True)
os.makedirs(settings.CHROMA_PERSIST_DIRECTORY, exist_ok=True)
