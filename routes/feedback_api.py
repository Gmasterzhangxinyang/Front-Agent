"""
Feedback API routes: list suggestions, approve/reject, feedbacks
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from database import AsyncSessionLocal
from models import SkillSuggestion, SkillFeedback, SkillVersion
from services.skill_analyzer import analyze_and_suggest
from services.file_git import update_skill_file
from pathlib import Path

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
        skill_path = Path(__file__).parent.parent / "skills" / f"{data.category}.md"
        current_skill_content = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""

        result = await analyze_and_suggest(
            skill_name=data.category,
            user_question="",
            ai_answer="",
            bobby_corrected=data.correct_reply,
            bobby_suggestion=data.suggestion,
            score=data.score,
            current_skill_content=current_skill_content,
        )
        return {"status": "ok", "suggestion_id": result.get("suggestion_id"), "reason": result.get("reason", "")}
    except Exception as e:
        logger.error("Feedback submit failed: %s", e, exc_info=True)
        return {"status": "error", "message": str(e)}


@router.get("/feedback/form")
async def feedback_form(conv: str = "", category: str = ""):
    """Serve the standalone feedback form HTML."""
    from fastapi.responses import FileResponse
    return FileResponse(Path(__file__).parent / "static" / "feedback.html")


@router.get("/feedback/api/suggestions")
async def list_suggestions(status: str = ""):
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        query = select(SkillSuggestion).order_by(SkillSuggestion.created_at.desc()).limit(100)
        if status:
            query = query.where(SkillSuggestion.status == status)
        result = await db.execute(query)
        rows = result.scalars().all()
        return [_suggestion_to_dict(r) for r in rows]


@router.get("/feedback/api/feedbacks")
async def list_feedbacks(limit: int = 200):
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SkillFeedback).order_by(SkillFeedback.created_at.desc()).limit(limit)
        )
        rows = result.scalars().all()
        return [_feedback_to_dict(r) for r in rows]


@router.post("/feedback/api/suggestions/{suggestion_id}/approve")
async def approve_suggestion(suggestion_id: int):
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SkillSuggestion).where(SkillSuggestion.id == suggestion_id)
        )
        sg = result.scalar_one_or_none()
        if not sg:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        if sg.status != "pending":
            return {"status": "error", "message": f"Already {sg.status}"}

        # Write skill file and push
        if sg.full_skill_content:
            success, msg = await update_skill_file(
                sg.skill_name, sg.full_skill_content,
                f"feat(skills): update {sg.skill_name}.md via skill evolution"
            )
            if not success:
                return {"status": "error", "message": f"Git push failed: {msg}"}

        sg.status = "approved"
        sg.reviewed_by = "bobby"
        from datetime import datetime
        sg.reviewed_at = datetime.utcnow()
        await db.commit()

        # Increment change count, snapshot every 3
        from services.skill_version_store import skill_version_store
        count = await skill_version_store.increment_change_count(sg.skill_name)
        if count >= 3:
            await skill_version_store.add_snapshot(sg.skill_name, sg.full_skill_content, "ai")
        return {"status": "ok", "change_count": count}


@router.post("/feedback/api/suggestions/{suggestion_id}/reject")
async def reject_suggestion(suggestion_id: int):
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SkillSuggestion).where(SkillSuggestion.id == suggestion_id)
        )
        sg = result.scalar_one_or_none()
        if not sg:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        sg.status = "rejected"
        sg.reviewed_by = "bobby"
        from datetime import datetime
        sg.reviewed_at = datetime.utcnow()
        await db.commit()
        return {"status": "ok"}


@router.get("/feedback/api/skills")
async def list_skills():
    """List all skill files with their content."""
    skills_dir = Path(__file__).parent.parent / "skills"
    result = []
    for f in sorted(skills_dir.glob("*.md")):
        result.append({
            "name": f.stem,
            "size": f.stat().st_size,
            "content": f.read_text(encoding="utf-8"),
        })
    return result


@router.get("/feedback/api/admin")
async def admin_page():
    """Serve the admin dashboard HTML."""
    from fastapi.responses import FileResponse
    return FileResponse(Path(__file__).parent / "static" / "admin.html")


def _suggestion_to_dict(r) -> dict:
    return {
        "id": r.id,
        "skill_name": r.skill_name,
        "suggestion_type": r.suggestion_type,
        "deleted_content": r.deleted_content,
        "added_content": r.added_content,
        "full_skill_content": r.full_skill_content,
        "reason": r.reason,
        "source_examples": r.source_examples,
        "status": r.status,
        "submitted_by": r.submitted_by,
        "reviewed_by": r.reviewed_by,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _feedback_to_dict(r) -> dict:
    return {
        "id": r.id,
        "skill_name": r.skill_name,
        "user_question": r.user_question,
        "ai_answer": r.ai_answer,
        "bobby_corrected_answer": r.bobby_corrected_answer,
        "bobby_suggestion": r.bobby_suggestion,
        "score": r.score,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }