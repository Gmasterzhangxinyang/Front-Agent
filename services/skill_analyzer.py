"""
Skill Analyzer: 分析 Bobby 的反馈，生成 skill 修改建议（diff 格式）
参考节水方案的 Memory Extractor 三层架构
"""
import json
import logging
from typing import Dict, Any, Optional
from openai import AsyncOpenAI
from config import settings

logger = logging.getLogger(__name__)
_base_url = settings.minimax_base_url if settings.minimax_api_key else None
client = AsyncOpenAI(
    api_key=settings.minimax_api_key or settings.openai_api_key,
    base_url=_base_url,
)

SKILL_ANALYZER_PROMPT = """你是 Dify 邮件系统的 Skill 学习引擎。

你的任务：分析 Bobby 对 AI 回复的反馈，提取三层记忆并生成 skill 文件修改建议。

## 任务步骤

### 第一步：三层记忆提取
分析 Bobby 的正确回复和建议，判断这条反馈教会了我们什么：

1. **semantic_memories（关键知识）**
   - 这条 skill 需要补充/修正的关键知识是什么
   - 比如："education plan 只给全日制高等教育机构，不给中学和培训机构"

2. **episodic_memories（具体案例）**
   - 这个具体案例教会我们什么流程/判断标准
   - 比如："当用户提到'我不是学生'时，不应该直接拒绝，而要先确认机构类型"

3. **procedural_memories（操作规则）**
   - 未来遇到类似情况应遵循的流程
   - 比如："处理 partnership 邮件时，必须先确认对方是插件开发还是商业合作"

### 第二步：生成 Skill 修改建议
基于三层提取和当前 skill 内容，生成修改建议：

1. **deleted_content**：从 skill 中删除哪些内容（如果有）
2. **added_content**：新增到 skill 中的内容（如果有）
3. **full_skill_content**：修改后的完整 skill 文件内容（必须包含所有现有内容 + 新增修改）
4. **reason**：说明为什么要这样改
5. **change_type**：add / modify / delete

## 输出格式（严格 JSON）
{{
  "semantic_memories": ["关键知识1", "关键知识2"],
  "episodic_memories": ["案例教会我们的1", "案例教会我们的2"],
  "procedural_memories": ["操作规则1", "操作规则2"],
  "deleted_content": "需要删除的内容，没有则为空字符串",
  "added_content": "需要新增的内容，没有则为空字符串",
  "full_skill_content": "修改后的完整 skill 文件内容",
  "reason": "为什么要这样修改的说明",
  "change_type": "add | modify | delete"
}}

## 注意事项
- full_skill_content 必须包含 skill 的完整内容，包括所有原有的部分
- 只修改确实需要改的地方，不要重写整个文件
- 语言和格式保持与原 skill 一致
- 如果反馈只是小问题，change_type 可能是 "modify"，deleted_content 为空
"""


async def analyze_and_suggest(
    skill_name: str,
    user_question: str,
    ai_answer: str,
    bobby_corrected: str,
    bobby_suggestion: str,
    score: int,
    current_skill_content: str,
) -> Dict[str, Any]:
    """
    分析 Bobby 反馈，生成 skill 修改建议
    返回 dict 包含三层提取结果和 diff
    """
    from services.skill_feedback_store import skill_feedback_store
    from services.skill_example_store import skill_example_store
    from services.skill_suggestion_store import skill_suggestion_store

    # 1. 写原始反馈到 skill_feedback（用于微调训练）
    feedback_id = await skill_feedback_store.add(
        skill_name=skill_name,
        user_question=user_question,
        ai_answer=ai_answer,
        bobby_corrected_answer=bobby_corrected,
        bobby_suggestion=bobby_suggestion,
        score=score,
    )

    # 2. LLM 三层分析
    skill_snippet = current_skill_content[:3000] + ("..." if len(current_skill_content) > 3000 else "")
    user_q = user_question[:500] if user_question else ""
    ai_a = ai_answer[:500] if ai_answer else ""
    bobby_c = bobby_corrected[:500] if bobby_corrected else ""
    bobby_s = bobby_suggestion[:300] if bobby_suggestion else ""

    prompt = f"""当前 Skill 内容（{skill_name}）：

```markdown
{skill_snippet}
```

---

用户问题：{user_q}
AI 原回答：{ai_a}
Bobby 正确回复：{bobby_c}
Bobby 修改建议：{bobby_s}
Bobby 评分：{score}/10

{SKILL_ANALYZER_PROMPT}
"""

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SKILL_ANALYZER_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        raw = response.choices[0].message.content
        try:
            result = json.loads(raw)
        except Exception:
            import re
            match = re.search(r'\{[^{}]*\}', raw.replace('\n', ''))
            result = json.loads(match.group()) if match else {}
    except Exception as e:
        logger.error("Skill analyzer LLM call failed: %s", e)
        result = {
            "semantic_memories": [],
            "episodic_memories": [],
            "procedural_memories": [],
            "deleted_content": "",
            "added_content": "",
            "full_skill_content": current_skill_content,
            "reason": f"LLM 分析失败: {e}",
            "change_type": "modify",
        }

    # 3. 写 skill_examples（pending，存储三层提取结果）
    for mem_type in ["semantic", "episodic", "procedural"]:
        key = f"{mem_type}_memories"
        contents = result.get(key, [])
        if isinstance(contents, list):
            for content in contents:
                if content:
                    await skill_example_store.add(
                        skill_name=skill_name,
                        user_question=user_question,
                        ai_answer=ai_answer,
                        bobby_corrected=bobby_corrected,
                        bobby_suggestion=bobby_suggestion,
                        score=score,
                        memory_type=mem_type,
                        extracted_content=content,
                    )

    # 4. 写 skill_suggestions
    source = json.dumps(
        {
            "user_question": user_question,
            "ai_answer": ai_answer,
            "bobby_corrected": bobby_corrected,
            "bobby_suggestion": bobby_suggestion,
            "score": score,
            "feedback_id": feedback_id,
        },
        ensure_ascii=False,
    )

    suggestion_id = await skill_suggestion_store.add(
        skill_name=skill_name,
        suggestion_type=result.get("change_type", "modify"),
        deleted_content=result.get("deleted_content", ""),
        added_content=result.get("added_content", ""),
        full_skill_content=result.get("full_skill_content", current_skill_content),
        reason=result.get("reason", ""),
        source_examples=source,
        submitted_by="ai",
    )

    return {
        "suggestion_id": suggestion_id,
        "semantic_memories": result.get("semantic_memories", []),
        "episodic_memories": result.get("episodic_memories", []),
        "procedural_memories": result.get("procedural_memories", []),
        "change_type": result.get("change_type", "modify"),
        "reason": result.get("reason", ""),
    }
