from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any

class SourceCitation(BaseModel):
    document_name: str
    page_number: int = 1
    chunk_id: str
    excerpt: str

class ChatSessionCreateRequest(BaseModel):
    business_slug_or_token: str
    channel: str = Field(default="public_link", pattern="^(public_link|widget|portal)$")
    customer_email: Optional[EmailStr] = None

class ChatSessionResponse(BaseModel):
    id: str
    business_id: str
    business_name: str
    business_slug: str
    channel: str
    started_at: datetime
    last_message_at: datetime

class ChatMessageRequest(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1, max_length=2000)

class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    sender: str
    content: str
    is_answered: bool
    feedback: Optional[str] = None
    confidence_score: float
    latency_ms: int
    llm_provider_used: str
    citations: List[SourceCitation] = []
    created_at: datetime

class FeedbackRequest(BaseModel):
    feedback: str = Field(..., pattern="^(up|down)$")

class LeadCaptureRequest(BaseModel):
    email: EmailStr
    message_id: Optional[str] = None
