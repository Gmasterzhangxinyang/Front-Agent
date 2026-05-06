import json
import time
import httpx
import logging
from config import settings

logger = logging.getLogger(__name__)

# ── Tenant access token cache ──────────────────────────────────────────────
_tenant_token: str | None = None
_token_expires_at: float = 0.0


async def _get_tenant_token() -> str | None:
    global _tenant_token, _token_expires_at
    if _tenant_token and time.time() < _token_expires_at - 60:
        return _tenant_token
    if not settings.feishu_app_id or not settings.feishu_app_secret:
        return None
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": settings.feishu_app_id, "app_secret": settings.feishu_app_secret},
        )
        data = r.json()
        if data.get("code") == 0:
            _tenant_token = data["tenant_access_token"]
            _token_expires_at = time.time() + data.get("expire", 7200)
            return _tenant_token
    logger.error("Failed to get Feishu tenant token: %s", r.text)
    return None


# ── Send / update card messages ────────────────────────────────────────────

async def send_card(card: dict) -> str | None:
    """Send an interactive card to Bobby's chat. Returns message_id or None."""
    if not settings.feishu_bot_chat_id:
        logger.warning("feishu_bot_chat_id not configured")
        return None
    token = await _get_tenant_token()
    if not token:
        return None
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "receive_id": settings.feishu_bot_chat_id,
                "msg_type": "interactive",
                "content": json.dumps(card),
            },
        )
        data = r.json()
        if data.get("code") == 0:
            return data["data"]["message_id"]
        logger.error("Feishu send_card failed: %s", r.text)
        return None


async def update_card(message_id: str, card: dict) -> bool:
    """Update an existing card (e.g. mark as handled after Bobby clicks)."""
    token = await _get_tenant_token()
    if not token:
        return False
    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"content": json.dumps(card)},
        )
        return r.json().get("code") == 0


# ── Card builders ──────────────────────────────────────────────────────────

def _header(title: str, color: str = "blue") -> dict:
    return {"title": {"tag": "plain_text", "content": title}, "template": color}


def build_notify_card(
    conversation_id: str,
    summary: str,
    linear_url: str | None = None,
    card_type: str = "general",
    ai_draft: str | None = None,
    classification_options: list[dict] | None = None,
) -> dict:
    """
    card_type:
      general      → 已转告 / 已解决
      security     → 已转安全团队 / 已解决
      reply_needed → AI draft + 通过发送 / 我来改
      classify     → 分类不确定，让 Bobby 选择
    """
    elements: list[dict] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": summary}},
    ]

    if linear_url:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"📋 Linear: {linear_url}"},
        })

    elements.append({"tag": "hr"})

    if card_type == "classify" and classification_options:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "**AI 不确定分类，请选择正确类别：**"},
        })
        actions = []
        for opt in classification_options[:4]:  # Max 4 buttons
            actions.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": opt["label"]},
                "type": "default",
                "value": {
                    "action": "confirm_classification",
                    "conversation_id": conversation_id,
                    "category": opt["category"],
                    "sub_type": opt.get("sub_type"),
                    "email_summary": opt.get("email_summary", ""),
                },
            })
    elif card_type == "reply_needed" and ai_draft:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**AI 草稿：**\n{ai_draft}"},
        })
        elements.append({"tag": "hr"})
        actions = [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "✅ 通过，直接发送"},
                "type": "primary",
                "value": {"action": "approve_draft", "conversation_id": conversation_id, "draft": ai_draft},
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "✏️ 我来改"},
                "type": "default",
                "value": {"action": "rewrite_draft", "conversation_id": conversation_id},
            },
        ]
    elif card_type == "security":
        actions = [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🔒 已转安全团队"},
                "type": "primary",
                "value": {"action": "security_forwarded", "conversation_id": conversation_id},
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "✅ 已解决"},
                "type": "default",
                "value": {"action": "resolved", "conversation_id": conversation_id},
            },
        ]
    else:
        actions = [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "✅ 已转告"},
                "type": "primary",
                "value": {"action": "forwarded", "conversation_id": conversation_id},
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "✅ 已解决"},
                "type": "default",
                "value": {"action": "resolved", "conversation_id": conversation_id},
            },
        ]

    elements.append({"tag": "action", "actions": actions})

    color_map = {"security": "red", "reply_needed": "wathet", "general": "blue", "classify": "yellow"}
    title_map = {
        "security": "⚠️ 安全事件",
        "reply_needed": "💬 待确认回复",
        "general": "📬 新工单通知",
        "classify": "❓ 分类不确定",
    }

    return {
        "config": {"wide_screen_mode": True},
        "header": _header(title_map.get(card_type, "📬 新工单通知"), color_map.get(card_type, "blue")),
        "elements": elements,
    }


def build_forwarded_card(conversation_id: str, original_summary: str) -> dict:
    """Card shown after Bobby clicks 已转告 — shows forwarded status + keeps 已解决 button."""
    return {
        "config": {"wide_screen_mode": True},
        "header": _header("📬 已转告", "orange"),
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": original_summary}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**状态：** 已转告相关同事，等待处理完成"}},
            {"tag": "hr"},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✅ 已解决"},
                        "type": "primary",
                        "value": {"action": "resolved", "conversation_id": conversation_id},
                    },
                ],
            },
        ],
    }


def build_handled_card(original_summary: str, action_label: str) -> dict:
    """Card shown after Bobby clicks a button — replaces buttons with status."""
    return {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": _header("✅ 已处理", "green"),
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": original_summary}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**操作：** {action_label}"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**完成时间：** {time.strftime('%Y-%m-%d %H:%M:%S')}"}},
        ],
    }


def build_awaiting_reply_card(
    conversation_id: str,
    summary: str,
    polished_draft: str,
) -> dict:
    """Card sent after AI polishes Bobby's custom reply — Bobby confirms before sending."""
    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": summary}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**整理后的回复：**\n{polished_draft}"}},
        {"tag": "hr"},
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "✅ 确认发送"},
                    "type": "primary",
                    "value": {
                        "action": "confirm_send",
                        "conversation_id": conversation_id,
                        "draft": polished_draft,
                    },
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "❌ 取消"},
                    "type": "danger",
                    "value": {"action": "cancel_send", "conversation_id": conversation_id},
                },
            ],
        },
    ]
    return {
        "config": {"wide_screen_mode": True},
        "header": _header("📝 请确认回复内容", "wathet"),
        "elements": elements,
    }


# ── High-level notify helpers ──────────────────────────────────────────────

async def notify_bobby(
    message: str,
    conversation_id: str = "",
    linear_url: str | None = None,
    card_type: str = "general",
    classification_options: list[dict] | None = None,
    email_summary: str | None = None,
) -> bool:
    """
    Send Bobby a Feishu notification.
    If app is configured → interactive card; otherwise → plain webhook text.
    Returns True on success.
    """
    if settings.feishu_app_id and settings.feishu_bot_chat_id:
        # For classify cards, embed email_summary into each option's value
        if card_type == "classify" and classification_options and email_summary:
            for opt in classification_options:
                opt["email_summary"] = email_summary
        card = build_notify_card(
            conversation_id=conversation_id,
            summary=message,
            linear_url=linear_url,
            card_type=card_type,
            classification_options=classification_options,
        )
        msg_id = await send_card(card)
        if msg_id:
            return True
        # fall through to webhook on failure

    # Fallback: plain webhook
    return await _send_webhook(settings.feishu_webhook_bobby, message)


async def notify_yongle(message: str, conversation_id: str = "") -> bool:
    if settings.feishu_webhook_yongle:
        return await _send_webhook(settings.feishu_webhook_yongle, message)
    return await notify_bobby(f"[紧急安全-转杨永乐] {message}", conversation_id=conversation_id, card_type="security")


async def _send_webhook(webhook_url: str, message: str) -> bool:
    if not webhook_url:
        return False
    payload = {"msg_type": "text", "content": {"text": message}}
    async with httpx.AsyncClient() as client:
        r = await client.post(webhook_url, json=payload)
        return r.status_code == 200
