from datetime import datetime
from sqlalchemy import String, DateTime, JSON, Text, UniqueConstraint, func
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


class SybilNotification(Base):
    __tablename__ = "sybil_notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    cc_email: Mapped[str] = mapped_column(String, default="")
    handoff_type: Mapped[str] = mapped_column(String, default="", index=True)
    linear_url: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class ConversationAction(Base):
    __tablename__ = "conversation_actions"
    __table_args__ = (UniqueConstraint("conversation_id", "action_type", "action_key", name="uq_conversation_action"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    action_key: Mapped[str] = mapped_column(String, nullable=False)
    result: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class DraftAdoption(Base):
    __tablename__ = "draft_adoptions"

    action_id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    action_key: Mapped[str] = mapped_column(String, nullable=False)
    draft_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    draft_created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class OpsReport(Base):
    __tablename__ = "ops_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String, nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
