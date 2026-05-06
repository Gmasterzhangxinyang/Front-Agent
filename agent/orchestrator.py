import json
import logging
from pathlib import Path
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from config import settings
from tools import state as state_tool
from tools.attachments import fetch_attachments_as_base64
from tools.front import get_conversation_messages
from agent.tool_registry import TOOL_SCHEMAS, execute_tool_call

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)
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

    # Fetch full conversation history from Front
    all_messages = await get_conversation_messages(conversation_id)
    conversation_text = build_conversation_text(all_messages)

    # Download attachments for vision
    attachment_content = await fetch_attachments_as_base64(attachments)

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
    user_content.extend(attachment_content)

    # If classifying, do a two-step: first classify, then load skill and act
    if not existing_state or existing_state.step in ("initial", "done"):
        classification = await _classify(conversation_text, message_body, sender_email, attachment_content)
        if classification:
            category = classification.get("category", "unclear")
            confidence = classification.get("confidence", 1.0)

            # If confidence is low, ask Bobby to confirm classification
            if confidence < 0.75:
                from tools.feishu import notify_bobby
                options = [
                    {"label": "教育版", "category": "education", "sub_type": "rejected"},
                    {"label": "技术问题", "category": "technical", "sub_type": "workflow_issue"},
                    {"label": "账号问题", "category": "account", "sub_type": "cant_login"},
                    {"label": "退款/账单", "category": "billing", "sub_type": "refund"},
                ]
                await notify_bobby(
                    f"⚠️ 分类置信度低 ({confidence:.0%})\n\n邮件摘要: {classification.get('summary')}\n\nAI 猜测: {category}/{classification.get('sub_type')}",
                    conversation_id=conversation_id,
                    card_type="classify",
                    classification_options=options,
                    email_summary=classification.get('summary'),
                )
                # Save the uncertain classification to state, wait for Bobby's confirmation
                await state_tool.set_state(
                    db, conversation_id, category, classification.get('sub_type'),
                    "awaiting_classification_confirmation", {}, waiting=True, sender_email=sender_email
                )
                return  # Stop here, wait for Bobby to click button

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

    await _run_agent_loop(messages, db)


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
    classify_md = load_skill("classify")
    content = [{"type": "text", "text": f"Classify this support email.\n\nSender: {sender_email}\n\nConversation:\n{conversation_text}\n\nLatest message:\n{latest_message}\n\nReturn ONLY valid JSON matching the output format in the skill instructions."}]
    content.extend(attachments)

    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": classify_md},
            {"role": "user", "content": content},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    try:
        return json.loads(response.choices[0].message.content)
    except Exception:
        return None


async def _run_agent_loop(messages: list, db: AsyncSession, max_iterations: int = 10) -> None:
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

            result = await execute_tool_call(tool_name, args, db)
            logger.info(f"Tool {tool_name} → {result}")

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

        if response.choices[0].finish_reason == "stop":
            break
