import json
import logging
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from config import settings
from tools import state as state_tool
from tools.attachments import (
    bounded_attachments,
    fetch_attachments_as_base64,
    fetch_attachments_as_text,
)
from tools.front import get_conversation_messages
from agent.classification import ClassificationResult, normalize_classification, parse_classification_json
from agent.llm_client import chat_completion_kwargs, make_async_openai_client
from agent.routing import RouteDecision, decide_initial_route
from agent.tool_registry import (
    TOOL_SCHEMAS,
    ToolCallValidationError,
    ToolExecutionContext,
    execute_tool_call,
    prepare_llm_tool_call,
)
from services.case_memory import build_case_memory_context

logger = logging.getLogger(__name__)
client = make_async_openai_client(settings)
SKILLS_DIR = Path(__file__).parent.parent / "skills"
KEEP_OPEN_TERMINAL_STEPS = {"done", "closed_spam"}
KEEP_OPEN_HANDOFF_TOOLS = {
    "front_forward_to_bobby",
    "front_forward_to_limin",
    "front_forward_to_sybil",
    "feishu_notify_sybil_group",
}


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


def is_failed_retry_state(existing_state) -> bool:
    return bool(
        existing_state and existing_state.step == "failed_needs_review"
    )


async def handle_email(
    conversation_id: str,
    message_body: str,
    sender_email: str,
    attachments: list[dict],
    db: AsyncSession,
) -> None:
    existing_state = await state_tool.get_state(db, conversation_id)
    retrying_failed_state = is_failed_retry_state(existing_state)
    initial_flow = (
        not existing_state
        or existing_state.step in ("initial", "done", "failed_needs_review")
    )

    # Existing-state webhook events are replies on conversations we have already handled.
    # Education keeps its existing flow. Billing continues only for the one approved
    # invoice Credit Note confirmation step; all other billing replies stay ignored.
    if existing_state and not retrying_failed_state:
        category = existing_state.category or ""
        step = existing_state.step or ""
        billing_credit_note_confirmation = (
            category == "billing"
            and existing_state.sub_type == "invoice"
            and step == "awaiting_credit_note_confirmation"
        )
        if category != "education" and not billing_credit_note_confirmation:
            logger.info(
                "Skipping reply without an approved continuation for conv %s — step=%s category=%s",
                conversation_id, existing_state.step, existing_state.category,
            )
            return
        if step == "closed_spam":
            logger.info("Skipping closed spam conversation %s", conversation_id)
            return

    # Fetch full conversation history from Front
    all_messages = await get_conversation_messages(conversation_id)
    conversation_text = build_conversation_text(all_messages)

    # Download attachments for vision (images) and text extraction (PDF/Word)
    bounded = bounded_attachments(attachments)
    attachment_content = await fetch_attachments_as_base64(bounded)
    doc_attachments = await fetch_attachments_as_text(bounded)
    doc_text = "\n".join([f"[附件: {d['filename']}]\n{d['text']}" for d in doc_attachments]) if doc_attachments else ""

    case_memory_query = f"{conversation_text}\n\n{message_body}"
    classification_case_memory = ""
    skill_case_memory = ""

    # Check if we need user history (only for new conversations)
    user_history_text = ""
    if initial_flow:
        classification_case_memory = await build_case_memory_context(db, case_memory_query, limit=4)
        should_fetch = await _should_fetch_history(conversation_text, message_body, sender_email)
        if should_fetch:
            history = await state_tool.get_user_history(db, sender_email, days=30)
            if history:
                user_history_text = f"\n\n**User's conversation history (last 30 days):**\n{json.dumps(history, indent=2, ensure_ascii=False)}"
    elif existing_state.category:
        skill_case_memory = await build_case_memory_context(
            db,
            case_memory_query,
            category=existing_state.category,
            limit=4,
        )


    # Determine which skill to load
    if existing_state and not initial_flow:
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

{skill_case_memory}

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

{classification_case_memory}

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
    if initial_flow:
        classification = await _classify(
            conversation_text,
            message_body,
            sender_email,
            attachment_content,
            case_memory_context=classification_case_memory,
        )
        if not classification:
            return

        route = decide_initial_route(classification, conversation_id, sender_email)
        if route.handled_before_skill:
            await _execute_initial_route(route, classification, conversation_id, sender_email, db)
            return

        category = classification.category
        sub_type = classification.sub_type
        skill_md = load_skill(category)
        skill_case_memory = await build_case_memory_context(
            db,
            case_memory_query,
            category=category,
            limit=4,
        )
        system_prompt = f"""You are a Dify support email automation agent.

This email has been classified as:
- Category: {category}
- Sub-type: {classification.sub_type}
- Is paid user: {classification.is_paid_user}
- Is premium user: {classification.is_premium}
- Urgency: {classification.urgency}
- Flags: {classification.flags}
- Summary: {classification.summary}

Deterministic route policy selected by Python:
- Route: {route.name}
- Customer action policy: {route.customer_action}
- Internal target: {route.internal_target}
- Inbox target: {route.inbox_target}
- State step if handled: {route.state_step}
- Reason: {route.reason}

Global safety rules:
- Do not send direct customer replies unless the skill explicitly permits direct send for this exact case.
- When unsure, create a Front draft or no customer reply; keep the conversation open.
- Internal handoff must use dedicated allowlisted tools only; never invent recipients or use a generic forwarding tool.
- Non-spam handoffs must use state step forwarded_keep_open or manual_review, not done.
- After creating a Linear ticket, keep the Front conversation open; use draft_created or forwarded_keep_open state, never done.

Skill instructions for this category:
{skill_md}

{skill_case_memory}

Follow the skill instructions within the global safety rules. Call the appropriate tools to handle this email.
Always be polite, professional, and empathetic in all replies to users.
Conversation ID: {conversation_id}
Sender email: {sender_email}
{user_history_text}
"""
        # Handle special flags before main flow. Legal threats are routed by
        # decide_initial_route() to Geyan and should not notify Bobby here.
        flags = classification.flags
        if "emotional" in flags:
            from tools.handoff import forward_to_bobby
            await forward_to_bobby(f"⚠️ 特殊邮件需关注 - 发件人: {sender_email}, 标记: {flags}, 摘要: {classification.summary}", conversation_id=conversation_id)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        await _run_agent_loop(
            messages,
            db,
            conversation_id=conversation_id,
            sender_email=sender_email,
            message_body=message_body,
        )


        # If a skill took actions but never saved state, do not mark the case done.
        # Missing state means Bobby should review the route/tool outcome.
        _current_state = await state_tool.get_state(db, conversation_id)
        if _current_state is None:
            await state_tool.set_state(
                db,
                conversation_id,
                category,
                classification.sub_type,
                "failed_needs_review",
                {
                    "route": route.name,
                    "reason": "skill loop completed without state_set",
                    "summary": classification.summary,
                },
                waiting=False,
                sender_email=sender_email,
            )

    else:
        # Continuing conversation with existing state
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        await _run_agent_loop(
            messages,
            db,
            conversation_id=conversation_id,
            sender_email=sender_email,
            message_body=message_body,
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

    response = await client.chat.completions.create(**chat_completion_kwargs(
        settings.openai_model,
        [{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=100,
    ))
    answer = response.choices[0].message.content.strip().upper()
    return "YES" in answer


async def _classify(
    conversation_text: str,
    latest_message: str,
    sender_email: str,
    attachments: list,
    case_memory_context: str = "",
) -> ClassificationResult | None:
    classify_md = load_skill("classify")
    memory_section = f"\n\n{case_memory_context}" if case_memory_context else ""
    content = [{"type": "text", "text": f"Classify this support email.\n\nSender: {sender_email}\n\nConversation:\n{conversation_text}\n\nLatest message:\n{latest_message}{memory_section}\n\nReturn ONLY valid JSON matching the output format in the skill instructions."}]
    content.extend(attachments)

    response = await client.chat.completions.create(**chat_completion_kwargs(
        settings.openai_model,
        [
            {"role": "system", "content": classify_md},
            {"role": "user", "content": content},
        ],
        temperature=0,
    ))
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


def _tool_result_succeeded(result: str) -> bool:
    failed_markers = ("failed", "blocked", "unknown_tool")
    return not any(marker in result for marker in failed_markers)


def _remember_keep_open_step(current_step: str | None, tool_name: str, result: str) -> str | None:
    if not _tool_result_succeeded(result):
        return current_step
    if tool_name in KEEP_OPEN_HANDOFF_TOOLS:
        return "forwarded_keep_open"
    if tool_name == "linear_create_ticket":
        try:
            payload = json.loads(result)
        except (TypeError, json.JSONDecodeError):
            payload = {}
        if payload.get("status") == "ticket_created":
            return current_step or "draft_created"
    return current_step


def _coerce_keep_open_state_args(args: dict, preferred_step: str) -> dict:
    requested_step = args.get("step")
    if requested_step not in KEEP_OPEN_TERMINAL_STEPS:
        return args

    coerced = dict(args)
    if coerced.get("category") == "unclear":
        coerced["step"] = "manual_review"
    else:
        coerced["step"] = preferred_step if preferred_step != "manual_review" else "forwarded_keep_open"
    coerced["waiting"] = False

    payload = dict(coerced.get("payload") or {})
    payload.setdefault("keep_open_guard", "linear_or_bobby_handoff")
    payload.setdefault("requested_step", requested_step)
    coerced["payload"] = payload
    return coerced


async def _run_agent_loop(
    messages: list,
    db: AsyncSession,
    conversation_id: str,
    max_iterations: int = 10,
    sender_email: str = "",
    message_body: str = "",
) -> None:
    notified_conversations: set[str] = set()  # deduplicate Bobby handoff forwards per conv
    keep_open_state_step: str | None = None
    context = ToolExecutionContext(
        conversation_id=conversation_id,
        sender_email=sender_email,
        original_message=message_body,
    )
    for _ in range(max_iterations):
        response = await client.chat.completions.create(**chat_completion_kwargs(
            settings.openai_model,
            messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0,
        ))
        msg = response.choices[0].message

        if not msg.tool_calls:
            break

        messages.append({"role": "assistant", "content": msg.content, "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})

        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                raw_args = json.loads(tc.function.arguments)
                args = prepare_llm_tool_call(tool_name, raw_args, context)
            except (json.JSONDecodeError, TypeError, ToolCallValidationError) as exc:
                result = f"tool_validation_failed: {exc}"
                logger.warning("Rejected LLM tool call %s: %s", tool_name, exc)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
                continue

            # Reassert the trusted recipient immediately before side effects.
            if tool_name == "front_create_draft" and sender_email:
                args["to_email"] = sender_email

            # Deduplicate Bobby handoff forwards per conversation per agent run
            if tool_name == "front_forward_to_bobby":
                conv_id = args.get("conversation_id", "__no_conv__")
                if conv_id in notified_conversations:
                    logger.info("Skipping duplicate Bobby handoff for conv %s", conv_id)
                    result = "forwarded"
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                    continue
                notified_conversations.add(conv_id)

            if tool_name == "linear_create_ticket":
                if sender_email and not args.get("sender_email"):
                    args["sender_email"] = sender_email
                if message_body and not args.get("original_message"):
                    args["original_message"] = message_body

            if tool_name == "state_set" and keep_open_state_step:
                args = _coerce_keep_open_state_args(args, keep_open_state_step)

            result = await execute_tool_call(tool_name, args, db)
            logger.info(f"Tool {tool_name} → {result}")
            keep_open_state_step = _remember_keep_open_step(keep_open_state_step, tool_name, result)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

        if response.choices[0].finish_reason == "stop":
            break
