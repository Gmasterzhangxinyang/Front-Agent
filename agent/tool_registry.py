import json
import logging
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tools import front, linear, handoff, state as state_tool, github, docs_search
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def _safe_add_comment(conversation_id: str, body: str) -> bool:
    """Add an internal Front comment without blocking the primary action."""
    try:
        return await front.add_comment(conversation_id, body)
    except Exception as e:
        logger.warning("Non-blocking Front comment failed for %s: %s", conversation_id, e)
        return False


# Tool schemas for GPT-4o function calling
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "front_create_draft",
            "description": "Create a draft reply in Front for Bobby to review and send manually. Do NOT send directly. Always use this instead of sending.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "body": {"type": "string", "description": "The reply body in English, polite and professional"},
                    "category": {"type": "string", "description": "Email category/sub_type, e.g. technical/how_to or billing/refund"},
                    "reason_cn": {"type": "string", "description": "一句话说明为什么这样回复，中文，不超过30字，例如：用户询问工作流节点用法，引导至文档"},
                },
                "required": ["conversation_id", "body", "category", "reason_cn"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "front_assign",
            "description": "Assign the conversation to a specific teammate in Front",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "teammate_id": {"type": "string", "description": "Front teammate ID"},
                },
                "required": ["conversation_id", "teammate_id"],
            },
        },
    },
    # front_resolve removed — Bobby handles resolve manually
    {
        "type": "function",
        "function": {
            "name": "front_forward_to_partnerships",
            "description": "Forward partnership, reseller, marketplace, plugin, and community ecosystem inquiries to marketing@dify.ai. The forwarded email includes the original Front thread content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "summary": {"type": "string", "description": "Brief summary of the user's inquiry (1-2 sentences)"},
                },
                "required": ["conversation_id", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "front_forward_to_community",
            "description": "Forward community, Marketplace, plugin/template ecosystem, and external cooperation inquiries to marketing@dify.ai. The region parameter is kept for compatibility but no longer changes routing. The forwarded email includes the original Front thread content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "summary": {"type": "string", "description": "Brief summary of the user's inquiry (1-2 sentences)"},
                    "region": {"type": "string", "description": "Region: plugins_templates / japan / cn_apac / eu", "enum": ["plugins_templates", "japan", "cn_apac", "eu"]},
                },
                "required": ["conversation_id", "summary", "region"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "front_forward_to_marketing",
            "description": "Move the conversation to the marketing inbox in Front. Use the inbox name as shown in Front (e.g. 'Marketing'). This is for marketing-related inquiries, campaigns, events, or promotional requests.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "summary": {"type": "string", "description": "Brief summary of the user's inquiry (1-2 sentences)"},
                },
                "required": ["conversation_id", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "front_forward_to_security",
            "description": "Move the conversation to the security inbox in Front. Use the inbox name as shown in Front (e.g. 'Security'). This is for security-related reports and concerns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                },
                "required": ["conversation_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "front_forward_to_investment",
            "description": "Forward the original Front conversation directly to Claudia Liu (刘景媛) for investment/investor relations inquiries. This is an internal handoff and never emails the customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "summary": {"type": "string", "description": "Brief summary of the user's inquiry (1-2 sentences)"},
                },
                "required": ["conversation_id", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "front_forward_to_legal",
            "description": "Send a Front forward containing the original conversation and summary to 葛岩 (geyan@dify.ai) for legal threats, lawyer letters, or lawsuit inquiries. This is not a customer reply and keeps the conversation open.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "summary": {"type": "string", "description": "Brief summary of the legal issue (1-2 sentences)"},
                },
                "required": ["conversation_id", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "front_add_comment",
            "description": "Add an internal comment/note to the conversation (not visible to user)",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["conversation_id", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "front_add_tag",
            "description": "Add a tag to the conversation in Front",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "tag_id": {"type": "string"},
                },
                "required": ["conversation_id", "tag_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "linear_create_ticket",
            "description": "Create a Linear ticket in the CUS project",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string", "description": "Front conversation ID, used to link the ticket back"},
                    "title": {"type": "string"},
                    "body": {"type": "string", "description": "Ticket description in Chinese, include all relevant details"},
                    "sender_email": {"type": "string", "description": "The sender's email address"},
                    "original_message": {"type": "string", "description": "The original email body from the user"},
                    "attachment_content": {"type": "string", "description": "Attachment content for PDF/Word files (base64 encoded if image, otherwise text extracted from PDF/Word). For images, provide the base64 string. For PDF/Word, provide extracted text content."},
                },
                "required": ["conversation_id", "title", "body"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "front_forward_to_bobby",
            "description": "Forward the original Front conversation to Bobby through Front with an internal summary. This never emails the customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "conversation_id": {"type": "string", "description": "Front conversation ID, REQUIRED so Front can forward the original thread"},
                },
                "required": ["message", "conversation_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "front_forward_to_limin",
            "description": "Compatibility account handoff path: forward the original Front conversation to Bobby through Front for account verification or blacklist queries previously routed to 李敏. This never emails the customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "conversation_id": {"type": "string", "description": "Front conversation ID, REQUIRED so Front can forward the original thread"},
                },
                "required": ["message", "conversation_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "front_forward_to_sybil",
            "description": "Forward the original Front conversation to Sybil through Front for education plan handoff. This never emails the customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "conversation_id": {"type": "string", "description": "Front conversation ID, REQUIRED so Front can forward the original thread"},
                },
                "required": ["message", "conversation_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "state_set",
            "description": "Save the current conversation state for multi-turn flows",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "category": {"type": "string"},
                    "sub_type": {"type": "string"},
                    "step": {"type": "string", "description": "e.g. awaiting_identity_verification, awaiting_school_info, draft_created, forwarded_keep_open, manual_review, closed_spam, done"},
                    "payload": {"type": "object", "description": "Any extra data to persist"},
                    "waiting": {"type": "boolean", "description": "True if waiting for user reply (starts 10-day timer)"},
                    "sender_email": {"type": "string", "description": "User's email address"},
                },
                "required": ["conversation_id", "category", "step"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_search",
            "description": "Search GitHub issues and PRs in the langgenius/dify repo to find known bugs, workarounds, or fixes relevant to the user's issue",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keywords describing the user's issue"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "docs_search",
            "description": "Search Dify official documentation (docs.dify.ai) to find accurate answers about features, configuration, workflows, and how-to guides. Use this before replying to technical questions to ground your answer in official docs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords describing what the user wants to know, e.g. 'workflow node types', 'API rate limits', 'knowledge base retrieval'"},
                },
                "required": ["query"],
            },
        },
    },
]


async def execute_tool_call(tool_name: str, args: dict, db: AsyncSession) -> str:
    from config import settings

    if tool_name == "front_create_draft":
        conversation_id = args["conversation_id"]
        body = args["body"]
        category = args.get("category", "")
        reason_cn = args.get("reason_cn", "AI 自动生成草稿")
        comment = f"[AI草稿] 分类：{category}｜{reason_cn}"
        await _safe_add_comment(conversation_id, comment)
        ok = await front.create_draft(conversation_id, body)
        return "draft_created" if ok else "draft_failed"

    if tool_name == "front_reply":
        logger.warning("Blocked deprecated direct customer reply tool: %s", tool_name)
        return "blocked_deprecated_direct_reply_tool"

    elif tool_name == "front_assign":
        ok = await front.assign_conversation(args["conversation_id"], args["teammate_id"])
        return "assigned" if ok else "assign_failed"

    elif tool_name == "front_forward_to_partnerships":
        conversation_id = args["conversation_id"]
        summary = args.get("summary", "")
        to_email = settings.marketing_partnership_email or "marketing@dify.ai"
        ok = await front.forward_conversation_direct(
            conversation_id,
            to_email,
            None,
            summary,
        )
        return "forwarded_to_marketing" if ok else "forward_failed"

    elif tool_name == "front_forward_to_community":
        conversation_id = args["conversation_id"]
        summary = args.get("summary", "")
        to_email = settings.marketing_partnership_email or "marketing@dify.ai"
        ok = await front.forward_conversation_direct(
            conversation_id,
            to_email,
            None,
            summary,
        )
        return "forwarded_to_marketing" if ok else "forward_failed"

    elif tool_name == "front_forward_to_investment":
        conversation_id = args["conversation_id"]
        summary = args.get("summary", "")
        if not settings.claudia_email:
            return "forward_failed: claudia_email not configured"
        ok = await front.forward_conversation_direct(
            conversation_id,
            settings.claudia_email,
            None,
            summary
        )
        return "forwarded" if ok else "forward_failed"

    elif tool_name == "front_forward_to_legal":
        conversation_id = args["conversation_id"]
        summary = args.get("summary", "")
        if not settings.geyan_email:
            return "forward_failed: geyan_email not configured"
        ok = await front.forward_conversation_direct(
            conversation_id,
            settings.geyan_email,
            None,
            summary,
            label="legal handoff",
        )
        return "forwarded_to_geyan" if ok else "forward_failed"

    elif tool_name == "front_forward_to_marketing":
        conversation_id = args["conversation_id"]
        summary = args.get("summary", "")
        if not settings.marketing_inbox_name:
            return "forward_failed: marketing_inbox_name not configured"
        # Move to marketing inbox (no draft, no reply to user)
        ok = await front.move_conversation_to_inbox(
            conversation_id,
            settings.marketing_inbox_name
        )
        if ok:
            # Add internal comment with summary
            await _safe_add_comment(
                conversation_id,
                f"[AI] Marketing type email - moved to marketing inbox. Summary: {summary}"
            )
        return "moved_to_marketing" if ok else "move_failed"

    elif tool_name == "front_forward_to_security":
        conversation_id = args["conversation_id"]
        if not settings.security_inbox_name:
            return "forward_failed: security_inbox_name not configured"
        ok = await front.move_conversation_to_inbox(
            conversation_id,
            settings.security_inbox_name
        )
        if ok:
            await _safe_add_comment(
                conversation_id,
                f"[AI] Security concern - moved to security inbox."
            )
        return "moved_to_security" if ok else "move_failed"

    elif tool_name == "front_add_comment":
        ok = await _safe_add_comment(args["conversation_id"], args["body"])
        return "comment_added" if ok else "comment_failed"

    elif tool_name == "front_reply_with_template":
        logger.warning("Blocked deprecated direct customer reply tool: %s", tool_name)
        return "blocked_deprecated_direct_reply_tool"

    elif tool_name == "front_close_conversation":
        conversation_id = args["conversation_id"]
        ok = await front.resolve_conversation(conversation_id)
        return "conversation_closed" if ok else "close_failed"

    elif tool_name == "front_add_tag":
        ok = await front.add_tag(args["conversation_id"], args["tag_id"])
        return "tag_added" if ok else "tag_failed"

    elif tool_name == "linear_create_ticket":
        body = args["body"]
        sender_email = args.get("sender_email", "")
        original_message = args.get("original_message", "")
        attachment_content = args.get("attachment_content", "")
        if sender_email or original_message or attachment_content:
            body += "\n\n---"
            if sender_email:
                body += f"\n\n**发件人：** {sender_email}"
            if original_message:
                body += f"\n\n**邮件原文：**\n{original_message}"
            if attachment_content:
                body += f"\n\n**附件内容：**\n{attachment_content}"
        result = await linear.create_ticket(args["title"], body)
        if result:
            url, identifier = result
            conversation_id = args.get("conversation_id")
            if conversation_id:
                await _safe_add_comment(conversation_id, f"Linear issue created: [{identifier}]({url})")
            return json.dumps({"status": "ticket_created", "url": url, "identifier": identifier})
        return "ticket_failed"

    elif tool_name == "front_forward_to_bobby":
        msg = args["message"]
        conv_id = args.get("conversation_id", "")
        ok = await handoff.forward_to_bobby(msg, conversation_id=conv_id)
        return "forwarded" if ok else "forward_failed"

    elif tool_name == "front_forward_to_limin":
        ok = await handoff.forward_to_limin(
            args["message"],
            conversation_id=args.get("conversation_id", ""),
        )
        return "forwarded" if ok else "forward_failed"

    elif tool_name == "front_forward_to_sybil":
        ok = await handoff.forward_to_sybil(
            args["message"],
            conversation_id=args.get("conversation_id", ""),
        )
        return "forwarded" if ok else "forward_failed"

    elif tool_name == "state_set":
        await state_tool.set_state(
            db,
            args["conversation_id"],
            args.get("category", ""),
            args.get("sub_type"),
            args["step"],
            args.get("payload", {}),
            args.get("waiting", False),
            args.get("sender_email"),
        )
        return "state_saved"

    elif tool_name == "github_search":
        results = await github.search_issues(args["query"])
        return json.dumps(results, ensure_ascii=False)

    elif tool_name == "docs_search":
        results = await docs_search.search_docs(args["query"])
        return json.dumps(results, ensure_ascii=False)

    return f"unknown_tool: {tool_name}"
