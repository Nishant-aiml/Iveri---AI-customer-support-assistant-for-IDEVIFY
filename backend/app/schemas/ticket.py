from datetime import datetime
from pydantic import BaseModel, Field

class TicketResponse(BaseModel):
    id: str
    ticket_number: str
    business_id: str
    session_id: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    channel: str
    subject: str
    description: str
    priority: str
    status: str
    resolved_answer: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True

class TicketResolveRequest(BaseModel):
    resolved_answer: str = Field(..., min_length=3, description="Ground truth answer to resolve ticket and index into knowledge base")

class ContactRequest(BaseModel):
    session_id: str = Field(..., description="Active chat session id")
    customer_name: str | None = Field(None, description="Customer name")
    customer_contact: str = Field(..., min_length=3, description="Customer phone number or email address")
    message: str = Field(..., min_length=1, description="Customer message or callback reason")
    channel: str = Field("widget", description="Channel origin: 'widget', 'whatsapp', 'public_link'")

class NotificationResponse(BaseModel):
    id: str
    business_id: str
    ticket_id: str | None = None
    type: str
    title: str
    message: str
    link_url: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True

class PushSubscribeRequest(BaseModel):
    endpoint: str = Field(..., description="Browser PushSubscription endpoint URL")
    p256dh: str = Field(..., description="Client public encryption key")
    auth: str = Field(..., description="Client auth secret")
