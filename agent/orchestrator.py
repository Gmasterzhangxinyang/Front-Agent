import json
import logging
from pathlib import Path
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from config import settings
from tools import state as state_tool
from tools.attachments import fetch_attachments_as_base64, fetch_attachments_as_text
from tools.front import get_conversation_messages
from agent.classification import ClassificationResult, normalize_classification, parse_classification_json
from agent.routing import RouteDecision, decide_initial_route
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

    # Only re-work if conversation is new or explicitly waiting for user input.
    # Terminal/internal handoff states should not be re-triggered simply because
    # Front generated a new event_id after moving/forwarding/commenting.
    if existing_state:
        step = existing_state.step or ""
        is_reworkable = step == "initial" or step.startswith("awaiting_") or step == "waiting_user"
        if not is_reworkable:
            logger.info(
                "Skipping handle_email for conv %s — already in step '%s' (category=%s)",
                conversation_id, existing_state.step, existing_state.category,
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

        route = decide_initial_route(classification, conversation_id, sender_email)
        if route.handled_before_skill:
            await _execute_initial_route(route, classification, conversation_id, sender_email, db)
            if route.send_feedback_comment:
                await _send_feedback_comment(
                    conversation_id=conversation_id,
                    sender_email=sender_email,
                    category=route.state_category or classification.category,
                    all_messages=[],
                )
            return

        category = classification.category
        sub_type = classification.sub_type
        skill_md = load_skill(category)
        system_prompt = f"""You are a Dify support email automation agent.

This email has been classified as:
- Category: {category}
- Sub-type: {classification.sub_type}
- Is paid user: {classification.is_paid_user}
- Is premium user: {classification.is_premium}
- Urgency: {classification.urgency}
- Flags: {classification.flags}
- Summary: {classification.summary}

Skill instructions for this category:
{skill_md}

Follow the skill instructions exactly. Call the appropriate tools to handle this email.
Always be polite, professional, and empathetic in all replies to users.
Conversation ID: {conversation_id}
Sender email: {sender_email}
{user_history_text}
"""
        # Handle special flags before main flow
        flags = classification.flags
        if "emotional" in flags or "legal_threat" in flags:
            from tools.handoff import forward_to_bobby
            await forward_to_bobby(f"⚠️ 特殊邮件需关注 - 发件人: {sender_email}, 标记: {flags}, 摘要: {classification.summary}", conversation_id=conversation_id)

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
                classification.sub_type,
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


async def _classify(conversation_text: str, latest_message: str, sender_email: str, attachments: list) -> ClassificationResult | None:
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
    parsed = parse_classification_json(raw)
    if parsed is None:
        logger.warning("Classification parse failed for sender=%s raw=%r", sender_email, raw)
        return normalize_classification(None, fallback_sender_email=sender_email)
    return normalize_classification(parsed, fallback_sender_email=sender_email)


async def _execute_initial_route(
    route: RouteDecision,
    classification: ClassificationResult,
    conversation_id: str,
    sender_email: str,
    db: AsyncSession,
) -> None:
    result = "no_tool"
    if route.tool_name:
        result = await execute_tool_call(route.tool_name, route.tool_args, db)
        logger.info("Initial route %s via %s -> %s", route.name, route.tool_name, result)

        if _tool_result_failed(result):
            fallback_result = "not_attempted"
            if route.tool_name == "front_forward_to_security":
                fallback_result = await execute_tool_call(
                    "front_forward_to_bobby",
                    {
                        "conversation_id": conversation_id,
                        "message": (
                            "Security inbox routing failed; please review manually.\n"
                            f"Original route: {route.name}\n"
                            f"Tool result: {result}\n"
                            f"Summary: {classification.summary}"
                        ),
                    },
                    db,
                )
            await state_tool.set_state(
                db,
                conversation_id,
                route.state_category or classification.category,
                route.state_sub_type if route.state_sub_type is not None else classification.sub_type,
                "failed_needs_review",
                {
                    "route": route.name,
                    "reason": route.reason,
                    "confidence": classification.confidence,
                    "summary": classification.summary,
                    "tool_result": result,
                    "fallback_result": fallback_result,
                },
                waiting=False,
                sender_email=sender_email,
            )
            return

    await state_tool.set_state(
        db,
        conversation_id,
        route.state_category or classification.category,
        route.state_sub_type if route.state_sub_type is not None else classification.sub_type,
        route.state_step,
        {
            "route": route.name,
            "reason": route.reason,
            "confidence": classification.confidence,
            "summary": classification.summary,
            "tool_result": result,
        },
        waiting=route.waiting,
        sender_email=sender_email,
    )


def _tool_result_failed(result: str) -> bool:
    failed_markers = ("failed", "move_failed", "unknown_tool")
    return any(marker in result for marker in failed_markers)


async def _run_agent_loop(messages: list, db: AsyncSession, max_iterations: int = 10, sender_email: str = "", message_body: str = "") -> None:
    notified_conversations: set[str] = set()  # deduplicate Bobby handoff forwards per conv
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

            # Deduplicate Bobby handoff forwards per conversation per agent run
            if tool_name == "front_forward_to_bobby":
                conv_id = args.get("conversation_id", "__no_conv__")
                if conv_id in notified_conversations:
                    logger.info("Skipping duplicate Bobby handoff for conv %s", conv_id)
                    result = "forwarded"
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
