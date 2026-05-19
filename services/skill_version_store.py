"""
Skill Version Store: skill_versions 表 + 版本快照管理
每 3 次 skill 更新存一个快照
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import select, update
from database import AsyncSessionLocal
from models import SkillVersion

CHANGE_COUNT_THRESHOLD = 3


class SkillVersionStore:
    async def add_snapshot(
        self,
        skill_name: str,
        content: str,
        created_by: str = "ai",
    ) -> int:
        async with AsyncSessionLocal() as db:
            # Get latest version number for this skill
            result = await db.execute(
                select(SkillVersion)
                .where(SkillVersion.skill_name == skill_name)
                .order_by(SkillVersion.version.desc())
                .limit(1)
            )
            latest = result.scalar_one_or_none()
            next_version = (latest.version + 1) if latest else 1

            sv = SkillVersion(
                skill_name=skill_name,
                version=next_version,
                content=content,
                change_count=0,
                created_by=created_by,
            )
            db.add(sv)
            await db.commit()
            await db.refresh(sv)
            return sv.id

    async def increment_change_count(self, skill_name: str) -> int:
        """增加 change_count，达到阈值时自动存快照，返回当前 change_count"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(SkillVersion)
                .where(SkillVersion.skill_name == skill_name)
                .order_by(SkillVersion.version.desc())
                .limit(1)
            )
            latest = result.scalar_one_or_none()
            if not latest:
                # Create first version entry
                sv = SkillVersion(
                    skill_name=skill_name,
                    version=1,
                    content="",
                    change_count=1,
                    created_by="ai",
                )
                db.add(sv)
                await db.commit()
                return 1

            new_count = latest.change_count + 1
            await db.execute(
                update(SkillVersion)
                .where(SkillVersion.id == latest.id)
                .values(change_count=new_count)
            )
            await db.commit()
            return new_count

    async def list_versions(
        self,
        skill_name: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(SkillVersion)
                .where(SkillVersion.skill_name == skill_name)
                .order_by(SkillVersion.version.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
            return [self._to_dict(r) for r in rows]

    async def get_version(
        self,
        skill_name: str,
        version: int,
    ) -> Optional[Dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(SkillVersion)
                .where(SkillVersion.skill_name == skill_name)
                .where(SkillVersion.version == version)
            )
            row = result.scalar_one_or_none()
            return self._to_dict(row) if row else None

    def _to_dict(self, row) -> Dict[str, Any]:
        if not row:
            return {}
        return {
            "id": row.id,
            "skill_name": row.skill_name,
            "version": row.version,
            "content": row.content,
            "change_count": row.change_count,
            "created_by": row.created_by,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


skill_version_store = SkillVersionStore()
