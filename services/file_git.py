"""
Git operations: 写 skill 文件 + git add + commit + push
"""
import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 全局锁，防止并发提交同一个文件
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
    原子性更新 skill 文件并 commit+push。
    返回 (success, message)
    """
    skill_path = Path(__file__).parent.parent / "skills" / f"{skill_name}.md"
    lock = _get_file_lock(str(skill_path))

    async with lock:
        try:
            # 1. Fetch 并检测冲突
            proc = await asyncio.create_subprocess_shell(
                "git fetch origin main 2>&1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            # 2. 读取远程版本
            proc2 = await asyncio.create_subprocess_shell(
                f"git show origin/main:skills/{skill_name}.md 2>/dev/null || echo ''",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            remote_content, _ = await proc2.communicate()
            remote_text = remote_content.decode("utf-8", errors="replace")

            # 3. 比较是否有冲突（远程和本地都变了）
            local_path = skill_path
            if local_path.exists():
                local_text = local_path.read_text(encoding="utf-8")
            else:
                local_text = ""

            if remote_text and remote_text != local_text and new_content != remote_text:
                logger.warning("Remote skill %s has changed, will force overwrite", skill_name)

            # 4. 写文件
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            skill_path.write_text(new_content, encoding="utf-8")

            # 5. Git add + commit + push
            commit_msg = message or f"feat(skills): update {skill_name}.md via skill evolution system"

            add_proc = await asyncio.create_subprocess_shell(
                f"git add skills/{skill_name}.md",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await add_proc.communicate()

            commit_proc = await asyncio.create_subprocess_shell(
                f'git commit -m "{commit_msg}"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            commit_out, commit_err = await commit_proc.communicate()

            if commit_proc.returncode != 0:
                logger.error("Git commit failed: %s", commit_err.decode())
                return False, f"Git commit failed: {commit_err.decode()}"

            push_proc = await asyncio.create_subprocess_shell(
                "git push origin main",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            push_out, push_err = await push_proc.communicate()

            if push_proc.returncode != 0:
                logger.error("Git push failed: %s", push_err.decode())
                return False, f"Git push failed: {push_err.decode()}"

            logger.info("Skill %s updated and pushed successfully", skill_name)
            return True, "更新并推送成功"

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
