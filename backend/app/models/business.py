import json
from sqlalchemy import Column, String, Text, Boolean
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
    avatar_url = Column(String(512), default="", nullable=False)
    widget_position = Column(String(20), default="bottom-right", nullable=False)
    welcome_message = Column(Text, default="Hello! How can I help you today?", nullable=False)
    custom_prompt = Column(Text, default="", nullable=False)
    whatsapp_number = Column(String(50), default="", nullable=False)
    enable_whatsapp = Column(Boolean, default=True, nullable=False)
    enable_callback = Column(Boolean, default=True, nullable=False)
    callback_channel = Column(String(50), default="phone_and_email", nullable=False)
    callback_button_text = Column(String(100), default="Request Callback", nullable=False)
    fallback_message = Column(
        Text, 
        default="I'm sorry, but I do not have this information in my documents. I have logged your question for our team to assist you.",
        nullable=False
    )
    _starter_questions = Column("starter_questions", Text, default='[]', nullable=False)

    # Relationships
    users = relationship("User", back_populates="business", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="business", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="business", cascade="all, delete-orphan")
    unanswered_questions = relationship("UnansweredQuestion", back_populates="business", cascade="all, delete-orphan")
    tickets = relationship("Ticket", back_populates="business", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="business", cascade="all, delete-orphan")

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
