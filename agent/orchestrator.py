import json
import logging
from pathlib import Path
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from config import settings
from tools import state as state_tool
from tools.attachments import fetch_attachments_as_base64, fetch_attachments_as_text
from tools.front import get_conversation_messages
from agent.tool_registry import TOOL_SCHEMAS, execute_tool_call

logger = logging.getLogger(__name__)
_base_url = settings.minimax_base_url if settings.minimax_api_key else None
client = AsyncOpenAI(
    api_key=settings.minimax_api_key or settings.openai_api_key,
    base_url=_base_url,
)
SKILLS_DIR = Path(__file__).parent.parent / "skills"


def load_skill(name: str) -> str:
    path = SKILLS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def build_conversation_text(messages: list[dict]) -> str:
    parts = []
    for msg in messages:
        role = "User" if msg.get("type") == "email" and not msg.get("is_draft") else "Support"
        body = msg.get("text") or msg.get("body") or ""
        parts.append(f"[{role}]: {body}")
    return "\n\n---\n\n".join(parts)


async def handle_email(
    conversation_id: str,
    message_body: str,
    sender_email: str,
    attachments: list[dict],
    db: AsyncSession,
) -> None:
    existing_state = await state_tool.get_state(db, conversation_id)

    # Only re-work if conversation is truly new (initial) or waiting for user input (awaiting_*)
    # "done" is terminal — a conversation that finished processing should not be
    # re-triggered simply because Front generated a new event_id (e.g. after
    # moving to another inbox).
    # Note: awaiting_classification_confirmation IS reworkable because Bobby's
    # confirmation needs to resume the agent loop.
    _REWORKABLE_STEPS = {"initial", "awaiting_classification_confirmation"}
    if existing_state and existing_state.step not in _REWORKABLE_STEPS:
        logger.info(
            "Skipping handle_email for conv %s — already in step '%s' (category=%s)",
            conversation_id, existing_state.step, existing_state.category,
        )
        return

    _TERMINAL_STEPS = {"bobby_forwarded", "bobby_resolved", "bobby_security_forwarded"}
    if existing_state and existing_state.step in _TERMINAL_STEPS:
        logger.info(
            "Skipping handle_email for conv %s — already in terminal state '%s'",
            conversation_id, existing_state.step,
        )
        return

    # Fetch full conversation history from Front
    all_messages = await get_conversation_messages(conversation_id)
    conversation_text = build_conversation_text(all_messages)

    # Download attachments for vision (images) and text extraction (PDF/Word)
    attachment_content = await fetch_attachments_as_base64(attachments)
    doc_attachments = await fetch_attachments_as_text(attachments)
    doc_text = "\n".join([f"[附件: {d['filename']}]\n{d['text']}" for d in doc_attachments]) if doc_attachments else ""

    # Check if we need user history (only for new conversations)
    user_history_text = ""
    if not existing_state or existing_state.step in ("initial", "done"):
        should_fetch = await _should_fetch_history(conversation_text, message_body, sender_email)
        if should_fetch:
            history = await state_tool.get_user_history(db, sender_email, days=30)
            if history:
                user_history_text = f"\n\n**User's conversation history (last 30 days):**\n{json.dumps(history, indent=2, ensure_ascii=False)}"

    # Determine which skill to load
    if existing_state and existing_state.step not in ("initial", "done"):
        skill_name = existing_state.category
        skill_md = load_skill(skill_name)
        system_prompt = f"""You are a Dify support email automation agent handling a multi-turn conversation.

Current conversation state:
- Category: {existing_state.category}
- Sub-type: {existing_state.sub_type}
- Step: {existing_state.step}
- Saved data: {json.dumps(existing_state.payload)}

Skill instructions:
{skill_md}

The user has replied. Continue the flow from the current step.
Always be polite, professional, and empathetic in all replies to users.
Conversation ID: {conversation_id}
Sender email: {sender_email}
"""
    else:
        classify_md = load_skill("classify")
        system_prompt = f"""You are a Dify support email automation agent.

Step 1: Classify this email using the classification skill below.
Step 2: Load the appropriate skill and execute the correct actions by calling the available tools.

Classification skill:
{classify_md}

After classifying, load and follow the skill for the identified category.
Always be polite, professional, and empathetic in all replies to users.
Conversation ID: {conversation_id}
Sender email: {sender_email}
{user_history_text}

Available skill categories and their instructions will be provided based on your classification.
Use the tools available to you to handle the email completely.
"""

    # Build user message content
    user_content = [{"type": "text", "text": f"Full conversation history:\n\n{conversation_text}\n\nLatest message from user:\n{message_body}"}]
    if doc_text:
        user_content.append({"type": "text", "text": f"\n\n[Document attachments text:]\n{doc_text}"})
    user_content.extend(attachment_content)

    # If classifying, do a two-step: first classify, then load skill and act
    if not existing_state or existing_state.step in ("initial", "done"):
        classification = await _classify(conversation_text, message_body, sender_email, attachment_content)
        if not classification:
            return

        category = classification.get("category", "unclear")
        confidence = classification.get("confidence", 1.0)
        sub_type = classification.get("sub_type", "")
        summary = classification.get("summary", "").lower()

        # Spam-like keywords in summary = auto archive (unsolicited cold outreach)
        spam_keywords = [
            "seo", "advertising", "广告", "推广", "sponsor", "pricelist", "price list",
            "pricing list", "视频合作",
        ]
        if any(kw in summary for kw in spam_keywords):
            await state_tool.set_state(db, conversation_id, "spam", None, "done", {}, waiting=False, sender_email=sender_email)
            from agent.tool_registry import execute_tool_call
            await execute_tool_call("front_close_conversation", {"conversation_id": conversation_id}, db)
            return

        # Unclear = auto archive (AI can't determine category)
        if category == "unclear":
            await state_tool.set_state(db, conversation_id, "unclear", None, "done", {}, waiting=False, sender_email=sender_email)
            from agent.tool_registry import execute_tool_call
            await execute_tool_call("front_close_conversation", {"conversation_id": conversation_id}, db)
            return

        # Truly uncertain (confidence < 0.3) = notify Bobby
        if confidence < 0.3:
            from tools.feishu import notify_bobby
            options = [
                {"label": "技术问题(technical)", "category": "technical"},
                {"label": "账号问题(account)", "category": "account"},
                {"label": "购买咨询(purchase)", "category": "purchase"},
                {"label": "教育版(education)", "category": "education"},
                {"label": "账单退款(billing)", "category": "billing"},
                {"label": "合作洽谈(partnership)", "category": "partnership"},
                {"label": "安全问题(security)", "category": "security"},
                {"label": "垃圾邮件(spam)", "category": "spam"},
                {"label": "法律相关(legal)", "category": "legal"},
                {"label": "产品路线(roadmap)", "category": "roadmap"},
                {"label": "投资融资(investment)", "category": "investment"},
                {"label": "数据导出(data_export)", "category": "data_export"},
                {"label": "无法分类(unclear)", "category": "unclear"},
            ]
            await notify_bobby(
                f"🤷 实在无法分类 ({confidence:.0%})\n\n邮件摘要: {classification.get('summary')}\n\nAI 猜测: {category}/{classification.get('sub_type')}",
                conversation_id=conversation_id,
                card_type="classify",
                classification_options=options,
                email_summary=classification.get('summary'),
            )
            await state_tool.set_state(
                db, conversation_id, category, classification.get('sub_type'),
                "awaiting_classification_confirmation", {}, waiting=True, sender_email=sender_email
            )
            return

        skill_md = load_skill(category)
        system_prompt = f"""You are a Dify support email automation agent.

This email has been classified as:
- Category: {category}
- Sub-type: {classification.get('sub_type')}
- Is paid user: {classification.get('is_paid_user')}
- Is premium user: {classification.get('is_premium')}
- Urgency: {classification.get('urgency')}
- Flags: {classification.get('flags', [])}
- Summary: {classification.get('summary')}

Skill instructions for this category:
{skill_md}

Follow the skill instructions exactly. Call the appropriate tools to handle this email.
Always be polite, professional, and empathetic in all replies to users.
Conversation ID: {conversation_id}
Sender email: {sender_email}
{user_history_text}
"""
        # Handle special flags before main flow
        flags = classification.get("flags", [])
        if "emotional" in flags or "legal_threat" in flags:
            from tools.feishu import notify_bobby
            await notify_bobby(f"⚠️ 特殊邮件需关注 - 发件人: {sender_email}, 标记: {flags}, 摘要: {classification.get('summary')}")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        await _run_agent_loop(messages, db, sender_email=sender_email, message_body=message_body)

        # After agent loop, send feedback comment
        await _send_feedback_comment(
            conversation_id=conversation_id,
            sender_email=sender_email,
            category=category,
            all_messages=messages,
        )

        # Ensure state is saved even if skill never called state_set
        # (e.g. billing/refund flow that only uses front_* tools)
        _current_state = await state_tool.get_state(db, conversation_id)
        if _current_state is None:
            await state_tool.set_state(
                db, conversation_id, category,
                classification.get("sub_type") if classification else None,
                "done", {}, waiting=False, sender_email=sender_email,
            )

    else:
        # Continuing conversation with existing state
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        await _run_agent_loop(messages, db, sender_email=sender_email, message_body=message_body)

        # After agent loop, send feedback comment
        await _send_feedback_comment(
            conversation_id=conversation_id,
            sender_email=sender_email,
            category=existing_state.category,
            all_messages=messages,
        )


async def _should_fetch_history(conversation_text: str, latest_message: str, sender_email: str) -> bool:
    """Ask AI if user history is needed for this email."""
    prompt = f"""Does this support email require knowledge of the user's previous conversations to handle properly?

Answer YES only if:
- User mentions "I already sent", "I contacted before", "still waiting", "follow up"
- User references a previous issue or ticket
- Context suggests this is a continuation of a past issue

Answer NO if:
- This is clearly a new, independent issue
- User is asking a general question
- No reference to past interactions

Email: {latest_message}

Answer with only YES or NO."""

    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=10,
    )
    answer = response.choices[0].message.content.strip().upper()
    return "YES" in answer


async def _classify(conversation_text: str, latest_message: str, sender_email: str, attachments: list) -> dict | None:
    import re
    classify_md = load_skill("classify")
    content = [{"type": "text", "text": f"Classify this support email.\n\nSender: {sender_email}\n\nConversation:\n{conversation_text}\n\nLatest message:\n{latest_message}\n\nReturn ONLY valid JSON matching the output format in the skill instructions."}]
    content.extend(attachments)

    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": classify_md},
            {"role": "user", "content": content},
        ],
        temperature=0,
    )
    raw = response.choices[0].message.content
    # Try direct JSON parse first
    try:
        return json.loads(raw)
    except Exception:
        pass
    # MiniMax may wrap JSON in markdown code blocks or add extra text
    try:
        match = re.search(r'\{[^{}]*\}', raw.replace('\n', ''))
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return None


async def _run_agent_loop(messages: list, db: AsyncSession, max_iterations: int = 10, sender_email: str = "", message_body: str = "") -> None:
    notified_conversations: set[str] = set()  # deduplicate feishu_notify_bobby per conv
    for _ in range(max_iterations):
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            break

        messages.append({"role": "assistant", "content": msg.content, "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})

        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except Exception:
                args = {}

            # Deduplicate Feishu card notifications per conversation per agent run
            if tool_name == "feishu_notify_bobby":
                conv_id = args.get("conversation_id", "__no_conv__")
                if conv_id in notified_conversations:
                    logger.info("Skipping duplicate feishu_notify_bobby for conv %s", conv_id)
                    result = "notified"
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                    continue
                notified_conversations.add(conv_id)

            # Auto-inject sender_email and original_message for linear tickets
            if tool_name == "linear_create_ticket":
                if sender_email and not args.get("sender_email"):
                    args["sender_email"] = sender_email
                if message_body and not args.get("original_message"):
                    args["original_message"] = message_body

            result = await execute_tool_call(tool_name, args, db)
            logger.info(f"Tool {tool_name} → {result}")

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

        if response.choices[0].finish_reason == "stop":
            break


async def _send_feedback_comment(
    conversation_id: str,
    sender_email: str,
    category: str,
    all_messages: list,
) -> None:
    """After agent loop completes, send a private comment in Front with feedback link."""
    from tools import front

    # Extract the last AI reply from conversation history
    last_ai_reply = ""
    last_user_question = ""
    for msg in all_messages:
        if isinstance(msg, dict):
            role = msg.get("role", "")
            content = msg.get("content", "") or ""
            if role == "user" and not last_user_question:
                last_user_question = content[:200]
            elif role == "assistant" and content and not last_ai_reply:
                last_ai_reply = content[:300]
                break

    # Get the base URL from config (Railway exposes PORT directly)
    from config import settings
    base_url = getattr(settings, "streamlit_url", "http://localhost:8000").replace(":8501", ":8000")
    # Use FastAPI-based feedback form (no Streamlit dependency)
    feedback_url = f"{base_url}/feedback/form?conv={conversation_id}&category={category}"

    comment_body = f"""👉 [点击评分]({feedback_url})"""
    try:
        await front.add_comment(conversation_id, comment_body)
    except Exception as e:
        logger.warning("Failed to send feedback comment: %s", e)
