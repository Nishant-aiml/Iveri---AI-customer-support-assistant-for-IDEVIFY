from sqlalchemy import Column, String, Text, ForeignKey
from app.database import Base
from app.models.base import TimestampMixin, generate_uuid

class PushSubscription(Base, TimestampMixin):
    __tablename__ = "push_subscriptions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    business_id = Column(String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    endpoint = Column(Text, nullable=False)
    p256dh = Column(String(255), nullable=False)
    auth = Column(String(255), nullable=False)
