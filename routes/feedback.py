"""
Feedback submission API endpoint.
Receives POST from Streamlit feedback form and triggers skill_analyzer.
"""
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from database import AsyncSessionLocal
from models import ConversationState
from tools.front import get_conversation_messages
from services.skill_analyzer import analyze_and_suggest
from pathlib import Path
import json

logger = logging.getLogger(__name__)
router = APIRouter()


class FeedbackSubmit(BaseModel):
    conversation_id: str
    category: str
    score: int
    correct_reply: str = ""
    suggestion: str = ""


@router.post("/feedback/submit")
async def submit_feedback(data: FeedbackSubmit):
    try:
        # Load current skill content
        skill_path = Path(__file__).parent.parent / "skills" / f"{data.category}.md"
        if skill_path.exists():
            current_skill_content = skill_path.read_text(encoding="utf-8")
        else:
            current_skill_content = ""

        # Fetch conversation messages to get user question and AI answer
        all_messages = await get_conversation_messages(data.conversation_id)
        user_question = ""
        ai_answer = ""

        for msg in all_messages:
            if msg.get("type") == "email" and not msg.get("is_draft"):
                role = "user"
            else:
                role = "ai"
            body = msg.get("text") or msg.get("body") or ""
            if role == "user" and not user_question:
                user_question = body[:500]
            elif role == "ai" and not ai_answer:
                ai_answer = body[:500]

        # Run skill analyzer
        result = await analyze_and_suggest(
            skill_name=data.category,
            user_question=user_question,
            ai_answer=ai_answer,
            bobby_corrected=data.correct_reply,
            bobby_suggestion=data.suggestion,
            score=data.score,
            current_skill_content=current_skill_content,
        )

        return {
            "status": "ok",
            "suggestion_id": result["suggestion_id"],
            "reason": result.get("reason", ""),
        }

    except Exception as e:
        logger.error("Feedback submit failed: %s", e, exc_info=True)
        return {"status": "error", "message": str(e)}
