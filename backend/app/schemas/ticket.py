from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_serializer

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

    @field_serializer("created_at")
    def serialize_created_at(self, dt: datetime, _info):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    @field_serializer("resolved_at")
    def serialize_resolved_at(self, dt: datetime | None, _info):
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    class Config:
        from_attributes = True

class TicketResolveRequest(BaseModel):
    resolved_answer: str = Field(..., min_length=3, description="Customer reply or resolution summary")
    train_ai: bool = Field(True, description="Whether to permanently index verified knowledge into the business RAG memory. Strictly for business owners.")
    verified_knowledge_fact: str | None = Field(None, description="Optional clean factual knowledge rule to index, distinct from customer greeting")

class ContactRequest(BaseModel):
    session_id: str | None = Field(None, description="Active chat session id")
    business_slug: str | None = Field(None, description="Business slug or share token if session not yet created")
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

    @field_serializer("created_at")
    def serialize_created_at(self, dt: datetime, _info):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    class Config:
        from_attributes = True

class PushSubscribeRequest(BaseModel):
    endpoint: str = Field(..., description="Browser PushSubscription endpoint URL")
    p256dh: str = Field(..., description="Client public encryption key")
    auth: str = Field(..., description="Client auth secret")
