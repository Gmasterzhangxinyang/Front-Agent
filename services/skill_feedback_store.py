"""
Skill Feedback Store: skill_feedback 表的 CRUD（原始反馈记录，用于微调训练）
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import select, update, func
from database import AsyncSessionLocal
from models import SkillFeedback


class SkillFeedbackStore:
    async def add(
        self,
        skill_name: str,
        user_question: str,
        ai_answer: str,
        bobby_corrected_answer: str,
        bobby_suggestion: str,
        score: int,
    ) -> int:
        async with AsyncSessionLocal() as db:
            fb = SkillFeedback(
                skill_name=skill_name,
                user_question=user_question,
                ai_answer=ai_answer,
                bobby_corrected_answer=bobby_corrected_answer,
                bobby_suggestion=bobby_suggestion,
                score=score,
                status="active",
            )
            db.add(fb)
            await db.commit()
            await db.refresh(fb)
            return fb.id

    async def list_feedback(
        self,
        skill_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            query = select(SkillFeedback).order_by(SkillFeedback.created_at.desc())
            if skill_name:
                query = query.where(SkillFeedback.skill_name == skill_name)
            query = query.limit(limit)
            result = await db.execute(query)
            rows = result.scalars().all()
            return [self._to_dict(r) for r in rows]

    async def get_avg_score(self, skill_name: str) -> Optional[float]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(func.avg(SkillFeedback.score))
                .where(SkillFeedback.skill_name == skill_name)
                .where(SkillFeedback.status == "active")
            )
            val = result.scalar_one_or_none()
            return float(val) if val is not None else None

    def _to_dict(self, row) -> Dict[str, Any]:
        if not row:
            return {}
        return {
            "id": row.id,
            "skill_name": row.skill_name,
            "user_question": row.user_question,
            "ai_answer": row.ai_answer,
            "bobby_corrected_answer": row.bobby_corrected_answer,
            "bobby_suggestion": row.bobby_suggestion,
            "score": row.score,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


skill_feedback_store = SkillFeedbackStore()
