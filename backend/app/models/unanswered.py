from sqlalchemy import Column, String, Float, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import TimestampMixin, generate_uuid

class UnansweredQuestion(Base, TimestampMixin):
    __tablename__ = "unanswered_questions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    business_id = Column(String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(36), ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    message_id = Column(String(36), ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True, index=True)
    question_text = Column(Text, nullable=False)
    customer_email = Column(String(255), nullable=True)  # Lead capture
    top_retrieval_score = Column(Float, default=0.0, nullable=False)
    
    # Resolution Loop
    is_resolved = Column(Boolean, default=False, nullable=False, index=True)
    resolved_answer = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    business = relationship("Business", back_populates="unanswered_questions")
