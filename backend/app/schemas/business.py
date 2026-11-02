from pydantic import BaseModel, Field
from typing import Optional, List

class BusinessSettingsUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    tone: Optional[str] = Field(None, pattern="^(friendly|formal)$")
    brand_color: Optional[str] = Field(None, pattern="^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
    avatar_url: Optional[str] = Field(None, max_length=512)
    widget_position: Optional[str] = Field(None, pattern="^(bottom-right|bottom-left)$")
    welcome_message: Optional[str] = Field(None, min_length=2, max_length=500)
    custom_prompt: Optional[str] = Field(None, max_length=2000)
    fallback_message: Optional[str] = Field(None, min_length=5, max_length=1000)
    starter_questions: Optional[List[str]] = Field(None, max_length=8)
    whatsapp_number: Optional[str] = Field(None, max_length=50)
    enable_callback: Optional[bool] = None
    callback_channel: Optional[str] = Field(None, pattern="^(phone_and_email|phone|email|whatsapp)$")
    callback_button_text: Optional[str] = Field(None, max_length=100)

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
    custom_prompt: str = ""
    fallback_message: str
    starter_questions: List[str]
    whatsapp_number: str = ""
    enable_callback: bool = True
    callback_channel: str = "phone_and_email"
    callback_button_text: str = "Request Callback"
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
    custom_prompt: str = ""
    fallback_message: str
    starter_questions: List[str]
    whatsapp_number: str = ""
    enable_callback: bool = True
    callback_channel: str = "phone_and_email"
    callback_button_text: str = "Request Callback"
    document_count: int
