from pydantic import BaseModel, Field
from typing import Optional, List

class BusinessSettingsUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    tone: Optional[str] = Field(None, pattern="^(friendly|formal)$")
    brand_color: Optional[str] = Field(None, pattern="^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
    avatar_url: Optional[str] = Field(None, max_length=512)
    widget_position: Optional[str] = Field(None, pattern="^(bottom-right|bottom-left)$")
    welcome_message: Optional[str] = Field(None, min_length=2, max_length=500)
    fallback_message: Optional[str] = Field(None, min_length=5, max_length=1000)
    starter_questions: Optional[List[str]] = Field(None, max_length=8)

class BusinessSettingsResponse(BaseModel):
    id: str
    name: str
    slug: str
    share_token: str
    tone: str
    brand_color: str
    avatar_url: str = ""
    widget_position: str = "bottom-right"
    welcome_message: str = "Hello! How can I help you today?"
    fallback_message: str
    starter_questions: List[str]
    shareable_link: str
    embed_snippet: str

class PublicBusinessInfoResponse(BaseModel):
    id: str
    name: str
    slug: str
    tone: str
    brand_color: str
    avatar_url: str = ""
    widget_position: str = "bottom-right"
    welcome_message: str = "Hello! How can I help you today?"
    fallback_message: str
    starter_questions: List[str]
    document_count: int
