from sqlalchemy import Column, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import TimestampMixin, generate_uuid

class Ticket(Base, TimestampMixin):
    __tablename__ = "tickets"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    ticket_number = Column(String(20), unique=True, index=True, nullable=False)
    business_id = Column(String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(36), ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    message_id = Column(String(36), ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True)

    # Customer Contact Info
    customer_name = Column(String(255), nullable=True)
    customer_email = Column(String(255), nullable=True)
    customer_phone = Column(String(50), nullable=True)

    # Context & Channel
    channel = Column(String(50), default="widget", nullable=False)  # 'widget', 'whatsapp', 'public_link', 'portal'
    subject = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(String(20), default="medium", nullable=False)  # 'urgent', 'high', 'medium', 'low'
    status = Column(String(20), default="open", nullable=False, index=True)  # 'open', 'in_progress', 'resolved', 'closed'

    # Resolution
    resolved_answer = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    # Relationships
    business = relationship("Business", back_populates="tickets")
    session = relationship("ChatSession")
    notifications = relationship("Notification", back_populates="ticket", cascade="all, delete-orphan")
