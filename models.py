from datetime import datetime
from sqlalchemy import String, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class ConversationState(Base):
    __tablename__ = "conversation_states"

    conversation_id: Mapped[str] = mapped_column(String, primary_key=True)
    sender_email: Mapped[str] = mapped_column(String, nullable=True, index=True)
    category: Mapped[str] = mapped_column(String, nullable=True)
    sub_type: Mapped[str] = mapped_column(String, nullable=True)
    step: Mapped[str] = mapped_column(String, default="initial")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    waiting_since: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
