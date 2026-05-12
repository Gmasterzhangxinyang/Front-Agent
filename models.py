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


class SkillExample(Base):
    __tablename__ = "skill_examples"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    skill_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    user_question: Mapped[str] = mapped_column(String, nullable=True)
    ai_answer: Mapped[str] = mapped_column(String, nullable=True)
    bobby_corrected_answer: Mapped[str] = mapped_column(String, nullable=True)
    bobby_suggestion: Mapped[str] = mapped_column(String, nullable=True)
    score: Mapped[int] = mapped_column(String, nullable=True)
    memory_type: Mapped[str] = mapped_column(String, nullable=True)  # semantic / episodic / procedural
    extracted_content: Mapped[str] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending / approved / stored
    confirmed_by: Mapped[str] = mapped_column(String, default="bobby")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class SkillSuggestion(Base):
    __tablename__ = "skill_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    skill_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    suggestion_type: Mapped[str] = mapped_column(String, nullable=True)  # add / modify / delete
    deleted_content: Mapped[str] = mapped_column(String, nullable=True)
    added_content: Mapped[str] = mapped_column(String, nullable=True)
    full_skill_content: Mapped[str] = mapped_column(String, nullable=True)
    reason: Mapped[str] = mapped_column(String, nullable=True)
    source_examples: Mapped[str] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending / approved / rejected
    submitted_by: Mapped[str] = mapped_column(String, default="ai")
    reviewed_by: Mapped[str] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SkillVersion(Base):
    __tablename__ = "skill_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    skill_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[int] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    change_count: Mapped[int] = mapped_column(String, default=0)
    created_by: Mapped[str] = mapped_column(String, default="ai")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SkillFeedback(Base):
    __tablename__ = "skill_feedback"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    skill_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    user_question: Mapped[str] = mapped_column(String, nullable=True)
    ai_answer: Mapped[str] = mapped_column(String, nullable=True)
    bobby_corrected_answer: Mapped[str] = mapped_column(String, nullable=True)
    bobby_suggestion: Mapped[str] = mapped_column(String, nullable=True)
    score: Mapped[int] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
