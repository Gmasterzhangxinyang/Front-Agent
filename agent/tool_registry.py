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
            "name": "front_forward_to_partnerships",
            "description": "Create a draft email forwarding the conversation to the partnerships team (赵晗青 with cc to 赵雅雯). Use this for partnership, reseller, marketplace, and plugin inquiries. The draft will be created for Bobby to review before sending.",
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
            "description": "Create a draft email forwarding the conversation to community/partnership team with regional routing. The draft will be created for Bobby to review before sending.\n\nRegional routing:\n- 插件与模板生态 (plugins & templates): forward to 赵晗青, cc 赵雅雯\n- 日本 (Japan): forward to 赵雅雯, cc marudan.kj@dify.ai\n- CN & APAC Business Line: forward to 赵雅雯, cc lushachen@dify.ai + byron@dify.ai\n- EU Business Line: forward to 赵雅雯, cc xinruiliu@dify.ai",
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
            "name": "front_forward_to_investment",
            "description": "Create a draft email forwarding the conversation to Claudia Liu (刘景媛) for investment/investor relations inquiries. The draft will be created for Bobby to review before sending.",
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
            "name": "front_reply_with_template",
            "description": "Reply to the user with the X template (pre-written template for technical support). Use this for ALL technical category emails. This sends the template directly without draft review.",
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
            "name": "front_close_conversation",
            "description": "Archive/close the conversation in Front after sending template reply",
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
                    "conversation_id": {"type": "string", "description": "Front conversation ID, used to link card actions back — REQUIRED, always pass this"},
                },
                "required": ["message", "conversation_id"],
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
        ok = await front.forward_conversation(
            args["conversation_id"],
            args["to_email"],
            args.get("cc_email"),
            args.get("summary", "")
        )
        return "forwarded" if ok else "forward_failed"

    elif tool_name == "front_forward_to_partnerships":
        conversation_id = args["conversation_id"]
        summary = args.get("summary", "")
        if not settings.zhaohq_email:
            return "forward_failed: zhaohq_email not configured"
        ok = await front.forward_conversation(
            conversation_id,
            settings.zhaohq_email,
            settings.zhaoyawen_email if settings.zhaoyawen_email else None,
            summary
        )
        return "forward_draft_created" if ok else "forward_failed"

    elif tool_name == "front_forward_to_community":
        conversation_id = args["conversation_id"]
        summary = args.get("summary", "")
        region = args.get("region", "")

        # Regional routing
        if region == "plugins_templates":
            to_email = settings.zhaohq_email
            cc_email = settings.zhaoyawen_email or None
        elif region == "japan":
            to_email = settings.yawen_email
            cc_email = settings.marudan_kj_email or None
        elif region == "cn_apac":
            to_email = settings.yawen_email
            cc_parts = []
            if settings.lushachen_email:
                cc_parts.append(settings.lushachen_email)
            if settings.byron_email:
                cc_parts.append(settings.byron_email)
            cc_email = ", ".join(cc_parts) if cc_parts else None
        elif region == "eu":
            to_email = settings.yawen_email
            cc_email = settings.xinruiliu_email or None
        else:
            return "forward_failed: unknown region"

        if not to_email:
            return f"forward_failed: to_email not configured for region {region}"

        ok = await front.forward_conversation(conversation_id, to_email, cc_email, summary)
        return "forward_draft_created" if ok else "forward_failed"

    elif tool_name == "front_forward_to_investment":
        conversation_id = args["conversation_id"]
        summary = args.get("summary", "")
        if not settings.claudia_email:
            return "forward_failed: claudia_email not configured"
        ok = await front.forward_conversation(
            conversation_id,
            settings.claudia_email,
            None,  # No CC for investment inquiries
            summary
        )
        return "forward_draft_created" if ok else "forward_failed"

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
            await front.add_comment(
                conversation_id,
                f"[AI] Marketing type email - moved to marketing inbox. Summary: {summary}"
            )
        return "moved_to_marketing" if ok else "move_failed"

    elif tool_name == "front_add_comment":
        ok = await front.add_comment(args["conversation_id"], args["body"])
        return "comment_added" if ok else "comment_failed"

    elif tool_name == "front_reply_with_template":
        conversation_id = args["conversation_id"]
        template_body = """Dear Valued Customer,

Thank you for your inquiry. We appreciate your interest in Dify and would like to provide guidance on our support processes.

Priority technical support via "Contact Us" is available only for Dify Cloud Pro and Team subscribers.
If you are on a Pro or Team plan, please submit your request through Settings → Support → Contact Us in your dashboard.
When submitting the ticket, please do not remove the subscription verification details, as they are required for us to confirm your account status.

For Sandbox (Free Tier) users, we recommend consulting our comprehensive documentation at docs.dify.ai or submitting technical issues via GitHub at github.com/langgenius/dify/issues.

If you're interested in commercial collaboration or licensing, please email business@dify.ai with your company name, size, and specific use case. For verification purposes, kindly use your corporate email address when making business inquiries.

Please note that your use of Dify is permitted without additional commercial licensing when following our open source license terms and not creating products that directly compete with Dify's services. While not required, we appreciate "Powered by Dify" attribution in your implementations.

For efficient processing, we may be unable to respond to inquiries where the sender's identity cannot be verified. If you are a Dify partner, please contact us through your established partner channels.

Best regards,

The Dify Support Team"""
        ok = await front.reply_to_conversation(conversation_id, template_body)
        return "template_replied" if ok else "reply_failed"

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
        if sender_email or original_message:
            body += "\n\n---"
            if sender_email:
                body += f"\n\n**发件人：** {sender_email}"
            if original_message:
                body += f"\n\n**邮件原文：**\n{original_message}"
        result = await linear.create_ticket(args["title"], body)
        if result:
            url, identifier = result
            conversation_id = args.get("conversation_id")
            if conversation_id:
                await front.add_comment(conversation_id, f"Linear issue created: [{identifier}]({url})")
            return json.dumps({"status": "ticket_created", "url": url, "identifier": identifier})
        return "ticket_failed"

    elif tool_name == "feishu_notify_bobby":
        msg = args["message"]
        conv_id = args.get("conversation_id", "")
        ok = await feishu.notify_bobby(msg, conversation_id=conv_id)
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
