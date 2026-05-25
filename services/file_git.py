"""
Skill 文件读写（本地操作，无 git push）
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_file_locks: dict[str, asyncio.Lock] = {}


def _get_file_lock(skill_path: str) -> asyncio.Lock:
    if skill_path not in _file_locks:
        _file_locks[skill_path] = asyncio.Lock()
    return _file_locks[skill_path]


async def update_skill_file(
    skill_name: str,
    new_content: str,
    message: Optional[str] = None,
) -> tuple[bool, str]:
    """
    写 skill 文件到本地（无 git push）。
    返回 (success, message)
    """
    skill_path = Path(__file__).parent.parent / "skills" / f"{skill_name}.md"
    lock = _get_file_lock(str(skill_path))

    async with lock:
        try:
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            skill_path.write_text(new_content, encoding="utf-8")
            logger.info("Skill %s updated (local write)", skill_name)
            return True, "更新成功"
        except Exception as e:
            logger.error("update_skill_file failed: %s", e)
            return False, str(e)


async def rollback_skill_file(
    skill_name: str,
    version: int,
    version_content: str,
) -> tuple[bool, str]:
    """回滚 skill 到指定版本"""
    return await update_skill_file(
        skill_name=skill_name,
        new_content=version_content,
        message=f"rollback: revert {skill_name}.md to version {version}",
    )
