"""
Feishu interactive card callback handler.
Feishu POSTs here when Bobby clicks a button on a card.
"""
import asyncio
import logging

_action_locks: dict[str, asyncio.Lock] = {}

def _get_action_lock(key: str) -> asyncio.Lock:
    if key not in _action_locks:
        _action_locks[key] = asyncio.Lock()
    return _action_locks[key]

from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import update, select
from database import AsyncSessionLocal
from models import ConversationState
from tools import feishu, front
from tools.feishu import build_handled_card, build_forwarded_card, build_awaiting_reply_card, update_card

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
        event_type = body.get("header", {}).get("event_type")
        if event_type != "card.action.trigger":
            logger.info("Feishu non-card event body: %s", body)
            return {"code": 0}
        # Schema 2.0 card action — extract from event sub-object
        event = body.get("event", {})
        action_value: dict = event.get("action", {}).get("value", {})
        action = action_value.get("action")
        conversation_id = action_value.get("conversation_id", "")
        message_id = event.get("context", {}).get("open_message_id", "")
    else:
        # Old format callback — Feishu sends this alongside schema 2.0, ignore it
        return {"code": 0}

    logger.info("Card action: %s  conv: %s  msg: %s", action, conversation_id, message_id)

    if action == "forwarded":
        async with _get_action_lock(f"forwarded:{conversation_id}"):
            already_forwarded = await _check_and_set_forwarded(conversation_id)
            if already_forwarded:
                logger.info("Duplicate forwarded callback for %s, ignoring", conversation_id)
                return {"code": 0}
            summary = await _get_state_summary(conversation_id)
            card = build_forwarded_card(conversation_id, summary)
            if message_id:
                await update_card(message_id, card)
        return {
            "toast": {"type": "success", "content": "已转告相关同事"},
            "card": card,
        }

    if action == "security_forwarded":
        await _update_state_step(conversation_id, "bobby_security_forwarded")
        summary = await _get_state_summary(conversation_id)
        handled = build_handled_card(summary, "已转安全团队")
        if message_id:
            await update_card(message_id, handled)
        return {
            "toast": {"type": "success", "content": "已转安全团队"},
            "card": handled,
        }

    if action == "resolved":
        async with _get_action_lock(f"resolved:{conversation_id}"):
            already_resolved = await _check_and_set_resolved(conversation_id)
            if already_resolved:
                logger.info("Duplicate resolved callback for %s, ignoring", conversation_id)
                return {"code": 0}
            summary = await _get_state_summary(conversation_id)
            handled = build_handled_card(summary, "已解决 — 正在生成结案草稿...")
            if message_id:
                await update_card(message_id, handled)
        # Generate closing draft outside lock
        try:
            await _generate_closing_draft(conversation_id)
            final = build_handled_card(summary, "✅ 已解决 — 结案草稿已写入 Front")
        except Exception as e:
            logger.error("Failed to generate closing draft: %s", e)
            final = build_handled_card(summary, "✅ 已解决（结案草稿生成失败，请手动回复）")
        if message_id:
            await update_card(message_id, final)
        return {
            "toast": {"type": "success", "content": "已解决，结案草稿已写入 Front"},
            "card": final,
        }

    if action == "approve_draft":
        draft = action_value.get("draft", "")
        if draft and conversation_id:
            await front.reply_to_conversation(conversation_id, draft)
            await _update_state_step(conversation_id, "replied_approved")
            summary = await _get_state_summary(conversation_id)
            handled = build_handled_card(summary, "✅ 已发送 AI 草稿")
            if message_id:
                await update_card(message_id, handled)
            return {
                "toast": {"type": "success", "content": "已发送"},
                "card": handled,
            }
        return {"code": 0}

    if action == "rewrite_draft":
        await _update_state_step(conversation_id, "awaiting_bobby_custom_reply")
        summary = await _get_state_summary(conversation_id)
        handled = build_handled_card(summary, "✏️ 请在 Front 中直接回复")
        if message_id:
            await update_card(message_id, handled)
        return {
            "toast": {"type": "info", "content": "请在 Front 中直接回复"},
            "card": handled,
        }

    if action == "confirm_send":
        draft = action_value.get("draft", "")
        if draft and conversation_id:
            await front.reply_to_conversation(conversation_id, draft)
            await _update_state_step(conversation_id, "replied_confirmed")
            summary = await _get_state_summary(conversation_id)
            handled = build_handled_card(summary, "✅ 已发送确认回复")
            if message_id:
                await update_card(message_id, handled)
            return {
                "toast": {"type": "success", "content": "✅ 已发送确认回复"},
                "card": handled,
            }
        return {"code": 0}

    if action == "cancel_send":
        await _update_state_step(conversation_id, "send_cancelled")
        summary = await _get_state_summary(conversation_id)
        handled = build_handled_card(summary, "❌ 已取消发送")
        if message_id:
            await update_card(message_id, handled)
        return {
            "toast": {"type": "info", "content": "❌ 已取消发送"},
            "card": handled,
        }

    if action == "confirm_classification":
        category = action_value.get("category", "")
        sub_type = action_value.get("sub_type")
        email_summary = action_value.get("email_summary", "")
        if category and conversation_id:
            label = f"{category}/{sub_type}" if sub_type else category
            summary = await _get_state_summary(conversation_id)

            # Immediately update card to show processing state
            if message_id:
                processing_card = {
                    "config": {"wide_screen_mode": True},
                    "header": {"title": {"tag": "plain_text", "content": "⏳ 正在处理..."}, "template": "blue"},
                    "elements": [
                        {"tag": "div", "text": {"tag": "lark_md", "content": summary}},
                        {"tag": "hr"},
                        {"tag": "div", "text": {"tag": "lark_md", "content": f"**已确认分类：** {label}\n\n正在调用 AI 处理邮件，请稍候..."}},
                    ],
                }
                await update_card(message_id, processing_card)

            # Save the corrected classification to state
            await _update_state_classification(conversation_id, category, sub_type)

            # Append this as a new few-shot example to classify.md
            if email_summary:
                try:
                    await _append_classify_example(email_summary, category, sub_type)
                except Exception as e:
                    logger.warning("Failed to append classify example: %s", e)

            # Now run the agent with the confirmed classification
            try:
                await _run_agent_with_classification(conversation_id, category, sub_type, message_id)
                # Success - card already updated by agent or we update here
                if message_id:
                    success_card = build_handled_card(summary, f"✅ 已确认分类: {label}，处理完成")
                    await update_card(message_id, success_card)
                return {
                    "toast": {"type": "success", "content": f"已确认分类: {label}"},
                }
            except Exception as e:
                logger.error("Failed to run agent after classification: %s", e, exc_info=True)
                # Update card to show error
                if message_id:
                    error_card = {
                        "config": {"wide_screen_mode": True},
                        "header": {"title": {"tag": "plain_text", "content": "❌ 处理失败"}, "template": "red"},
                        "elements": [
                            {"tag": "div", "text": {"tag": "lark_md", "content": summary}},
                            {"tag": "hr"},
                            {"tag": "div", "text": {"tag": "lark_md", "content": f"**分类：** {label}\n\n**错误：** {str(e)[:200]}\n\n请在 Front 中手动处理"}},
                        ],
                    }
                    await update_card(message_id, error_card)
                return {
                    "toast": {"type": "error", "content": f"处理失败: {str(e)[:50]}"},
                }
        return {"code": 0}

    return {"code": 0}


async def _check_and_set_forwarded(conversation_id: str) -> bool:
    """Atomically check-and-set forwarded state. Returns True if already forwarded (duplicate)."""
    if not conversation_id:
        return False
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ConversationState).where(ConversationState.conversation_id == conversation_id)
        )
        state = result.scalar_one_or_none()
        if state and state.step == "bobby_forwarded":
            return True
        await db.execute(
            update(ConversationState)
            .where(ConversationState.conversation_id == conversation_id)
            .values(step="bobby_forwarded")
        )
        await db.commit()
        return False


async def _check_and_set_resolved(conversation_id: str) -> bool:
    """Atomically check-and-set resolved state. Returns True if already resolved (duplicate)."""
    if not conversation_id:
        return False
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ConversationState).where(ConversationState.conversation_id == conversation_id)
        )
        state = result.scalar_one_or_none()
        if state and state.step == "bobby_resolved":
            return True
        await db.execute(
            update(ConversationState)
            .where(ConversationState.conversation_id == conversation_id)
            .values(step="bobby_resolved")
        )
        await db.commit()
        return False


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


async def _generate_closing_draft(conversation_id: str) -> None:
    """Call GPT to generate a closing email draft and write it to Front."""
    from tools.front import get_conversation_messages, create_draft
    from agent.orchestrator import build_conversation_text
    from openai import AsyncOpenAI
    from config import settings

    all_messages = await get_conversation_messages(conversation_id)
    conversation_text = build_conversation_text(all_messages)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a Dify customer support agent. "
                    "Bobby has just resolved this support conversation. "
                    "Write a short, polite closing email to the user in English, "
                    "letting them know their issue has been resolved and inviting them to reach out if they need further help. "
                    "Do not repeat the full conversation. Keep it under 5 sentences. "
                    "Return only the email body text, no subject line."
                ),
            },
            {"role": "user", "content": conversation_text},
        ],
        temperature=0.4,
    )
    draft_body = resp.choices[0].message.content.strip()
    await create_draft(conversation_id, draft_body)


async def _run_agent_with_classification(conversation_id: str, category: str, sub_type: str | None, message_id: str = "") -> None:
    """Re-run the agent with Bobby's confirmed classification. Raises on failure."""
    from tools.front import get_conversation_messages
    from agent.orchestrator import build_conversation_text, load_skill, _run_agent_loop

    all_messages = await get_conversation_messages(conversation_id)
    conversation_text = build_conversation_text(all_messages)
    skill_md = load_skill(category)

    # Extract sender_email from state and latest user message for linear ticket injection
    sender_email = ""
    latest_user_message = ""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ConversationState).where(ConversationState.conversation_id == conversation_id)
        )
        state = result.scalar_one_or_none()
        if state and state.sender_email:
            sender_email = state.sender_email
    for msg in reversed(all_messages):
        if msg.get("type") == "email" and not msg.get("is_draft"):
            latest_user_message = msg.get("text") or msg.get("body") or ""
            break

    system_prompt = f"""You are a Dify support email automation agent.

This email has been manually classified by Bobby as:
- Category: {category}
- Sub-type: {sub_type}

Skill instructions for this category:
{skill_md}

Follow the skill instructions exactly. Call the appropriate tools to handle this email.
Always be polite, professional, and empathetic in all replies to users.
Conversation ID: {conversation_id}
Sender email: {sender_email}
"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": conversation_text},
    ]
    async with AsyncSessionLocal() as db:
        await _run_agent_loop(messages, db, sender_email=sender_email, message_body=latest_user_message)
