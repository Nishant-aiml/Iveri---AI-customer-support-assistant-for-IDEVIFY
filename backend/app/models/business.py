import uuid
import json
from sqlalchemy import Column, String, Text
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import TimestampMixin, generate_uuid

class Business(Base, TimestampMixin):
    __tablename__ = "businesses"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, index=True, nullable=False)
    share_token = Column(String(36), unique=True, index=True, default=generate_uuid, nullable=False)
    
    # Customization Settings
    tone = Column(String(50), default="friendly", nullable=False)
    brand_color = Column(String(20), default="#2563eb", nullable=False)
    fallback_message = Column(
        Text, 
        default="I'm sorry, but I do not have this information in my documents. I have logged your question for our team to assist you.",
        nullable=False
    )
    _starter_questions = Column("starter_questions", Text, default='["What are your business hours?", "What is your refund policy?", "How long does shipping take?"]', nullable=False)

    # Relationships
    users = relationship("User", back_populates="business", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="business", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="business", cascade="all, delete-orphan")
    unanswered_questions = relationship("UnansweredQuestion", back_populates="business", cascade="all, delete-orphan")

    @property
    def starter_questions(self):
        try:
            return json.loads(self._starter_questions) if self._starter_questions else []
        except Exception:
            return []

    @starter_questions.setter
    def starter_questions(self, value):
        if isinstance(value, list):
            self._starter_questions = json.dumps(value)
        else:
            self._starter_questions = json.dumps([])
