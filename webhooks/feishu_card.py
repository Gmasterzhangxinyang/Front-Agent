"""
Feishu interactive card callback handler.
Feishu POSTs here when Bobby clicks a button on a card.
"""
import logging
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import update, select
from database import AsyncSessionLocal
from models import ConversationState
from tools import feishu, front
from tools.feishu import build_handled_card, build_awaiting_reply_card, update_card

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/webhook/feishu/card")
async def feishu_card_callback(request: Request):
    body = await request.json()

    # Feishu sends a challenge on first verification
    if "challenge" in body:
        return {"challenge": body["challenge"]}

    schema = body.get("schema")
    if schema == "2.0":
        # New format: deduplicate — old format handles the action first
        event_type = body.get("header", {}).get("event_type")
        if event_type == "card.action.trigger":
            return {"code": 0}  # already handled by old-format callback
        logger.info("Feishu non-card event body: %s", body)
        return {"code": 0}

    # Old card callback format: action is at top level
    if "action" not in body:
        logger.info("Feishu non-card event body: %s", body)
        return {"code": 0}

    action_value: dict = body.get("action", {}).get("value", {})
    action = action_value.get("action")
    conversation_id = action_value.get("conversation_id", "")
    message_id = body.get("open_message_id", "")

    logger.info("Card action: %s  conv: %s  msg: %s", action, conversation_id, message_id)

    if action in ("forwarded", "resolved", "security_forwarded"):
        label_map = {
            "forwarded": "已转告相关同事",
            "resolved": "已解决",
            "security_forwarded": "已转安全团队",
        }
        label = label_map[action]
        await _update_state_step(conversation_id, f"bobby_{action}")
        summary = await _get_state_summary(conversation_id)
        return {
            "toast": {"type": "success", "content": label},
            "card": build_handled_card(summary, label),
        }

    if action == "approve_draft":
        draft = action_value.get("draft", "")
        if draft and conversation_id:
            ok = await front.reply_to_conversation(conversation_id, draft)
            await _update_state_step(conversation_id, "replied_approved")
            summary = await _get_state_summary(conversation_id)
            return {
                "toast": {"type": "success", "content": "已发送"},
                "card": build_handled_card(summary, "✅ 已发送 AI 草稿"),
            }
        return {"code": 0}

    if action == "rewrite_draft":
        await _update_state_step(conversation_id, "awaiting_bobby_custom_reply")
        summary = await _get_state_summary(conversation_id)
        return {
            "toast": {"type": "info", "content": "请在 Front 中直接回复"},
            "card": build_handled_card(summary, "✏️ 请在 Front 中直接回复"),
        }

    if action == "confirm_send":
        draft = action_value.get("draft", "")
        if draft and conversation_id:
            ok = await front.reply_to_conversation(conversation_id, draft)
            await _update_state_step(conversation_id, "replied_confirmed")
            summary = await _get_state_summary(conversation_id)
            return {
                "toast": {"type": "success", "content": "✅ 已发送确认回复"},
                "card": build_handled_card(summary, "✅ 已发送确认回复"),
            }
        return {"code": 0}

    if action == "cancel_send":
        await _update_state_step(conversation_id, "send_cancelled")
        summary = await _get_state_summary(conversation_id)
        return {
            "toast": {"type": "info", "content": "❌ 已取消发送"},
            "card": build_handled_card(summary, "❌ 已取消发送"),
        }

    if action == "confirm_classification":
        category = action_value.get("category", "")
        sub_type = action_value.get("sub_type")
        email_summary = action_value.get("email_summary", "")
        if category and conversation_id:
            # Save the corrected classification to state
            await _update_state_classification(conversation_id, category, sub_type)
            # Append this as a new few-shot example to classify.md
            if email_summary:
                await _append_classify_example(email_summary, category, sub_type)
            # Now run the agent with the confirmed classification
            await _run_agent_with_classification(conversation_id, category, sub_type)
            label = f"{category}/{sub_type}" if sub_type else category
            summary = await _get_state_summary(conversation_id)
            return {
                "toast": {"type": "success", "content": f"已确认分类: {label}"},
                "card": build_handled_card(summary, f"✅ 已确认分类: {label}，正在处理..."),
            }
        return {"code": 0}

    return {"code": 0}


async def _update_state_step(conversation_id: str, step: str) -> None:
    if not conversation_id:
        return
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(ConversationState)
            .where(ConversationState.conversation_id == conversation_id)
            .values(step=step)
        )
        await db.commit()


async def _update_state_classification(conversation_id: str, category: str, sub_type: str | None) -> None:
    if not conversation_id:
        return
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(ConversationState)
            .where(ConversationState.conversation_id == conversation_id)
            .values(category=category, sub_type=sub_type, step="initial")
        )
        await db.commit()


async def _get_state_summary(conversation_id: str) -> str:
    if not conversation_id:
        return ""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ConversationState).where(ConversationState.conversation_id == conversation_id)
        )
        state = result.scalar_one_or_none()
        if state:
            return f"对话 {conversation_id} | {state.category or ''} / {state.sub_type or ''}"
    return f"对话 {conversation_id}"


async def _append_classify_example(email_summary: str, category: str, sub_type: str | None) -> None:
    """Append a new confirmed example to classify.md to improve future accuracy."""
    from pathlib import Path
    import json
    classify_path = Path(__file__).parent.parent / "skills" / "classify.md"
    if not classify_path.exists():
        return
    sub_type_str = sub_type or "null"
    example = f"""
### Bobby-Confirmed Example
**Email summary:** {email_summary}

**Classification:**
```json
{{
  "category": "{category}",
  "sub_type": "{sub_type_str}",
  "confidence": 1.0
}}
```
"""
    content = classify_path.read_text(encoding="utf-8")
    # Insert before the Categories table
    insert_marker = "## Categories and Sub-types"
    if insert_marker in content:
        content = content.replace(insert_marker, example + "\n" + insert_marker)
        classify_path.write_text(content, encoding="utf-8")
        logger.info("Appended new classify example: %s/%s", category, sub_type)


async def _run_agent_with_classification(conversation_id: str, category: str, sub_type: str | None) -> None:
    """Re-run the agent with Bobby's confirmed classification."""
    try:
        from tools.front import get_conversation_messages
        from agent.orchestrator import build_conversation_text, load_skill, _run_agent_loop
        from openai import AsyncOpenAI
        from config import settings
        import json

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        all_messages = await get_conversation_messages(conversation_id)
        conversation_text = build_conversation_text(all_messages)
        skill_md = load_skill(category)

        system_prompt = f"""You are a Dify support email automation agent.

This email has been manually classified by Bobby as:
- Category: {category}
- Sub-type: {sub_type}

Skill instructions for this category:
{skill_md}

Follow the skill instructions exactly. Call the appropriate tools to handle this email.
Always be polite, professional, and empathetic in all replies to users.
Conversation ID: {conversation_id}
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": conversation_text},
        ]
        async with AsyncSessionLocal() as db:
            await _run_agent_loop(messages, db)
    except Exception as e:
        logger.error("Failed to re-run agent after classification: %s", e)
