"""
Skill Example Store: skill_examples 表的 CRUD + 向量检索
"""
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import select, update
from database import AsyncSessionLocal
from models import SkillExample


class SkillExampleStore:
    async def add(
        self,
        skill_name: str,
        user_question: str,
        ai_answer: str,
        bobby_corrected: str,
        bobby_suggestion: str,
        score: int,
        memory_type: str,
        extracted_content: str,
    ) -> int:
        async with AsyncSessionLocal() as db:
            ex = SkillExample(
                skill_name=skill_name,
                user_question=user_question,
                ai_answer=ai_answer,
                bobby_corrected_answer=bobby_corrected,
                bobby_suggestion=bobby_suggestion,
                score=score,
                memory_type=memory_type,
                extracted_content=extracted_content,
                status="pending",
            )
            db.add(ex)
            await db.commit()
            await db.refresh(ex)
            return ex.id

    async def list_examples(
        self,
        skill_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            query = select(SkillExample).order_by(SkillExample.created_at.desc())
            if skill_name:
                query = query.where(SkillExample.skill_name == skill_name)
            if status:
                query = query.where(SkillExample.status == status)
            query = query.limit(limit)
            result = await db.execute(query)
            rows = result.scalars().all()
            return [self._to_dict(r) for r in rows]

    async def get_by_id(self, example_id: int) -> Optional[Dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(SkillExample).where(SkillExample.id == example_id))
            row = result.scalar_one_or_none()
            return self._to_dict(row) if row else None

    async def update_status(self, example_id: int, status: str) -> bool:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(SkillExample)
                .where(SkillExample.id == example_id)
                .values(status=status, updated_at=datetime.now())
            )
            await db.commit()
            return True

    async def deprecate(self, example_id: int) -> bool:
        return await self.update_status(example_id, "deprecated")

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
            "memory_type": row.memory_type,
            "extracted_content": row.extracted_content,
            "status": row.status,
            "confirmed_by": row.confirmed_by,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


skill_example_store = SkillExampleStore()
