from sqlalchemy import Column, String, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import TimestampMixin, generate_uuid

class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    business_id = Column(String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True, index=True)

    type = Column(String(50), default="ticket_created", nullable=False)  # 'ticket_created', 'contact_request', 'whatsapp_message', 'ticket_resolved'
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    link_url = Column(String(512), default="/dashboard#tickets", nullable=False)
    is_read = Column(Boolean, default=False, nullable=False, index=True)

    # Relationships
    business = relationship("Business", back_populates="notifications")
    ticket = relationship("Ticket", back_populates="notifications")
