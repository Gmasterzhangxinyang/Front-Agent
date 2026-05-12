"""
Skill Suggestion Store: skill_suggestions 表的 CRUD
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import select, update
from database import AsyncSessionLocal
from models import SkillSuggestion


class SkillSuggestionStore:
    async def add(
        self,
        skill_name: str,
        suggestion_type: str,
        deleted_content: str,
        added_content: str,
        full_skill_content: str,
        reason: str,
        source_examples: str,
        submitted_by: str = "ai",
    ) -> int:
        async with AsyncSessionLocal() as db:
            sg = SkillSuggestion(
                skill_name=skill_name,
                suggestion_type=suggestion_type,
                deleted_content=deleted_content,
                added_content=added_content,
                full_skill_content=full_skill_content,
                reason=reason,
                source_examples=source_examples,
                status="pending",
                submitted_by=submitted_by,
            )
            db.add(sg)
            await db.commit()
            await db.refresh(sg)
            return sg.id

    async def list_suggestions(
        self,
        skill_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            query = select(SkillSuggestion).order_by(SkillSuggestion.created_at.desc())
            if skill_name:
                query = query.where(SkillSuggestion.skill_name == skill_name)
            if status:
                query = query.where(SkillSuggestion.status == status)
            query = query.limit(limit)
            result = await db.execute(query)
            rows = result.scalars().all()
            return [self._to_dict(r) for r in rows]

    async def get_by_id(self, suggestion_id: int) -> Optional[Dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(SkillSuggestion).where(SkillSuggestion.id == suggestion_id)
            )
            row = result.scalar_one_or_none()
            return self._to_dict(row) if row else None

    async def approve(self, suggestion_id: int, reviewed_by: str = "bobby") -> bool:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(SkillSuggestion)
                .where(SkillSuggestion.id == suggestion_id)
                .values(
                    status="approved",
                    reviewed_by=reviewed_by,
                    reviewed_at=datetime.now(),
                )
            )
            await db.commit()
            return True

    async def reject(self, suggestion_id: int, reviewed_by: str = "bobby") -> bool:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(SkillSuggestion)
                .where(SkillSuggestion.id == suggestion_id)
                .values(
                    status="rejected",
                    reviewed_by=reviewed_by,
                    reviewed_at=datetime.now(),
                )
            )
            await db.commit()
            return True

    async def delete(self, suggestion_id: int) -> bool:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import delete
            await db.execute(
                delete(SkillSuggestion).where(SkillSuggestion.id == suggestion_id)
            )
            await db.commit()
            return True

    def _to_dict(self, row) -> Dict[str, Any]:
        if not row:
            return {}
        return {
            "id": row.id,
            "skill_name": row.skill_name,
            "suggestion_type": row.suggestion_type,
            "deleted_content": row.deleted_content,
            "added_content": row.added_content,
            "full_skill_content": row.full_skill_content,
            "reason": row.reason,
            "source_examples": row.source_examples,
            "status": row.status,
            "submitted_by": row.submitted_by,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


skill_suggestion_store = SkillSuggestionStore()
