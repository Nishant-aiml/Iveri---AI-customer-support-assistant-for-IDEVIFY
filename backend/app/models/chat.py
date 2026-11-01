import json
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import TimestampMixin, generate_uuid

class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    business_id = Column(String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_email = Column(String(255), nullable=True)  # Captured on fallback
    channel = Column(String(50), default="public_link", nullable=False)  # 'public_link', 'widget', 'portal'
    sentiment = Column(String(20), default="neutral", nullable=False)  # 'positive', 'neutral', 'negative'
    primary_topic = Column(String(50), default="general", nullable=False)  # 'pricing', 'shipping', 'returns', etc.
    last_message_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    business = relationship("Business", back_populates="chat_sessions")
    customer = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at")

class ChatMessage(Base, TimestampMixin):
    __tablename__ = "chat_messages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    sender = Column(String(50), nullable=False)  # 'customer', 'assistant', 'system'
    content = Column(Text, nullable=False)
    is_answered = Column(Boolean, default=True, nullable=False)
    feedback = Column(String(10), nullable=True)  # 'up', 'down', or None
    sentiment = Column(String(20), default="neutral", nullable=False)  # 'positive', 'neutral', 'negative'
    topic = Column(String(50), default="general", nullable=False)
    confidence_score = Column(Float, default=1.0, nullable=False)
    latency_ms = Column(Integer, default=0, nullable=False)
    llm_provider_used = Column(String(50), default="none", nullable=False)
    _source_citations = Column("source_citations", Text, default="[]", nullable=False)

    session = relationship("ChatSession", back_populates="messages")

    @property
    def source_citations(self):
        try:
            return json.loads(self._source_citations) if self._source_citations else []
        except Exception:
            return []

    @source_citations.setter
    def source_citations(self, value):
        if isinstance(value, list):
            self._source_citations = json.dumps(value)
        else:
            self._source_citations = json.dumps([])
