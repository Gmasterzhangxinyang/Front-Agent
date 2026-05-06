import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tools import front, linear, feishu, state as state_tool, github, docs_search
from sqlalchemy.ext.asyncio import AsyncSession

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
            "name": "front_forward",
            "description": "Forward the conversation to another email address",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "to_email": {"type": "string"},
                    "cc_email": {"type": "string"},
                },
                "required": ["conversation_id", "to_email"],
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
                },
                "required": ["conversation_id", "title", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "feishu_notify_bobby",
            "description": "Send a Feishu notification to Bobby (interactive card with action buttons)",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "conversation_id": {"type": "string", "description": "Front conversation ID, used to link card actions back"},
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "feishu_notify_yongle",
            "description": "Send an urgent Feishu notification to 杨永乐 (security emergencies)",
            "parameters": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
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
                    "step": {"type": "string", "description": "e.g. awaiting_identity_verification, awaiting_school_info, ticket_created, done"},
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
        await front.add_comment(conversation_id, comment)
        ok = await front.create_draft(conversation_id, body)
        return "draft_created" if ok else "draft_failed"

    if tool_name == "front_reply":
        # Legacy path — only used when Bobby approves from Feishu card
        ok = await front.reply_to_conversation(args["conversation_id"], args["body"])
        return "replied" if ok else "reply_failed"

    elif tool_name == "front_assign":
        ok = await front.assign_conversation(args["conversation_id"], args["teammate_id"])
        return "assigned" if ok else "assign_failed"

    elif tool_name == "front_forward":
        ok = await front.forward_conversation(args["conversation_id"], args["to_email"], args.get("cc_email"))
        return "forwarded" if ok else "forward_failed"

    elif tool_name == "front_add_comment":
        ok = await front.add_comment(args["conversation_id"], args["body"])
        return "comment_added" if ok else "comment_failed"

    elif tool_name == "front_add_tag":
        ok = await front.add_tag(args["conversation_id"], args["tag_id"])
        return "tag_added" if ok else "tag_failed"

    elif tool_name == "linear_create_ticket":
        result = await linear.create_ticket(args["title"], args["body"])
        if result:
            url, identifier = result
            conversation_id = args.get("conversation_id")
            if conversation_id:
                await front.add_comment(conversation_id, f"Linear issue created: [{identifier}]({url})")
            return json.dumps({"status": "ticket_created", "url": url, "identifier": identifier})
        return "ticket_failed"

    elif tool_name == "feishu_notify_bobby":
        # Extract linear_url from message if present (AI puts it inline)
        msg = args["message"]
        linear_url = None
        conv_id = args.get("conversation_id", "")
        import re
        m = re.search(r'https://linear\.app/\S+', msg)
        if m:
            linear_url = m.group(0)
        ok = await feishu.notify_bobby(
            msg,
            conversation_id=conv_id,
            linear_url=linear_url,
        )
        return "notified" if ok else "notify_failed"

    elif tool_name == "feishu_notify_yongle":
        ok = await feishu.notify_yongle(
            args["message"],
            conversation_id=args.get("conversation_id", ""),
        )
        return "notified" if ok else "notify_failed"

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
