import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    
    # Database URL
    DATABASE_URL: str = "sqlite+aiosqlite:///./idevify.db"
    
    # JWT Security
    JWT_SECRET: str = "super-secret-jwt-key-change-in-production-123456"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    
    # Sarvam AI Document Intelligence API
    SARVAM_API_KEY: str = ""
    SARVAM_API_URL: str = "https://api.sarvam.ai"
    
    # LLM Cascade Settings
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"
    
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    
    OPENAI_API_KEY: str = ""
    
    # Vector & Storage
    CHROMA_PERSIST_DIRECTORY: str = "./chroma_db"
    UPLOAD_DIRECTORY: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 25
    
    # RAG Tuning Parameters
    CONFIDENCE_THRESHOLD: float = 0.55
    RRF_K: int = 60
    TOP_K_CHUNKS: int = 4
    
    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"
    
    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Ensure critical local directories exist
os.makedirs(settings.UPLOAD_DIRECTORY, exist_ok=True)
os.makedirs(settings.CHROMA_PERSIST_DIRECTORY, exist_ok=True)
