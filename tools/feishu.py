import json
import logging
import re

import httpx

from config import settings

BASE_URL = "https://open.feishu.cn/open-apis"

logger = logging.getLogger(__name__)


def _clip(value: str, limit: int = 3500) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n...[truncated]"


def _front_url(conversation_id: str) -> str:
    if not conversation_id:
        return ""
    return f"{settings.front_app_base_url.rstrip('/')}/{conversation_id}"


async def send_webhook_text(webhook_url: str, text: str) -> bool:
    if not webhook_url:
        logger.warning("Cannot send Feishu webhook message without webhook_url")
        return False

    payload = {
        "msg_type": "text",
        "content": {"text": _clip(text)},
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(webhook_url.strip(), json=payload)

    if response.status_code != 200:
        logger.error("Feishu webhook send failed: %s %s", response.status_code, response.text)
        return False

    data = response.json()
    if data.get("code") not in (None, 0):
        logger.error("Feishu webhook send rejected: %s", data)
        return False
    return True


async def _tenant_access_token() -> str | None:
    if not settings.feishu_app_id or not settings.feishu_app_secret:
        logger.warning("Feishu app credentials are not configured")
        return None

    payload = {
        "app_id": settings.feishu_app_id,
        "app_secret": settings.feishu_app_secret,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{BASE_URL}/auth/v3/tenant_access_token/internal",
            json=payload,
        )
    if response.status_code != 200:
        logger.error("Feishu token request failed: %s %s", response.status_code, response.text)
        return None

    data = response.json()
    token = data.get("tenant_access_token")
    if not token:
        logger.error("Feishu token response missing tenant_access_token: %s", data)
        return None
    return token


async def send_text(receive_id: str, receive_id_type: str, text: str) -> bool:
    token = await _tenant_access_token()
    if not token:
        return False
    if not receive_id:
        logger.warning("Cannot send Feishu message without receive_id")
        return False

    payload = {
        "receive_id": receive_id,
        "msg_type": "text",
        "content": json.dumps({"text": _clip(text)}, ensure_ascii=False),
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{BASE_URL}/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            headers=headers,
            json=payload,
        )

    if response.status_code != 200:
        logger.error("Feishu message send failed: %s %s", response.status_code, response.text)
        return False

    data = response.json()
    if data.get("code") != 0:
        logger.error("Feishu message send rejected: %s", data)
        return False
    return True


def _sybil_mention() -> str:
    if not settings.feishu_sybil_open_id:
        return "@Sybil"
    return f'<at user_id="{settings.feishu_sybil_open_id}">Sybil</at>'


def sybil_mention() -> str:
    return _sybil_mention()


def _extract_linear_url(message: str) -> str:
    for pattern in (
        r"\bLinear\s*[:：]\s*(https?://[^\s)>\]]+)",
        r"(https?://[^\s)>\]]*linear[^\s)>\]]*)",
    ):
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            return match.group(1).rstrip(".,，。")
    return ""


def _extract_handoff_type(message: str) -> str:
    match = re.search(r"(?:类型|Type)\s*[:：]\s*([^\n。；;,.，]+)", message, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()

    lowered = message.lower()
    if "教育版" in message and ("邮箱失效" in message or "毕业" in message):
        return "education_email_expired"
    if "教育版" in message and ("审核" in message or "申请" in message):
        return "education_review"
    if "账号" in message and ("额度" in message or "计划" in message or "异常" in message):
        return "account_anomaly"
    if "login" in lowered or "登录" in message:
        return "account_login"
    return "sybil_handoff"


def build_sybil_group_message(
    message: str,
    conversation_id: str = "",
    cc_note: str = "",
    handoff_type: str = "",
    linear_url: str = "",
) -> str:
    normalized_message = " ".join(message.strip().split())
    normalized_type = (handoff_type or _extract_handoff_type(normalized_message)).strip()
    normalized_linear = (linear_url or _extract_linear_url(normalized_message)).strip()

    if normalized_type and "类型:" not in normalized_message and "类型：" not in normalized_message:
        normalized_message = f"类型: {normalized_type}。{normalized_message}"

    has_linear_url = bool(_extract_linear_url(normalized_message))
    if normalized_linear and not has_linear_url:
        placeholder_pattern = r"(?i)\bLinear\s*[:：]\s*(?:\[[^\]]+\]|<[^>]+>|\S+)"
        if re.search(placeholder_pattern, normalized_message):
            normalized_message = re.sub(
                placeholder_pattern,
                f"Linear: {normalized_linear}",
                normalized_message,
                count=1,
            )
        else:
            normalized_message = f"{normalized_message} Linear: {normalized_linear}"

    mention = _sybil_mention()
    if normalized_message.startswith(mention):
        return normalized_message
    return f"{mention} {normalized_message}".strip()


async def send_sybil_group_text(text: str) -> bool:
    # Prefer the Feishu app-bot group route for Sybil handoffs. This is the
    # bobby的小猫 path and avoids accidentally sending to an unrelated webhook group.
    if settings.feishu_education_group_chat_id:
        ok = await send_text(settings.feishu_education_group_chat_id, "chat_id", text)
        if ok:
            return True

    if settings.feishu_webhook_bobby:
        ok = await send_webhook_text(settings.feishu_webhook_bobby, text)
        if ok:
            return True

    logger.warning("No Feishu group recipient configured for Sybil handoff")
    return False


async def notify_sybil_group(
    message: str,
    conversation_id: str = "",
    cc_note: str = "",
    handoff_type: str = "",
    linear_url: str = "",
) -> bool:
    text = build_sybil_group_message(
        message,
        conversation_id=conversation_id,
        cc_note=cc_note,
        handoff_type=handoff_type,
        linear_url=linear_url,
    )

    return await send_sybil_group_text(text)

async def notify_sybil(message: str, conversation_id: str = "", cc_note: str = "") -> bool:
    return await notify_sybil_group(message, conversation_id=conversation_id, cc_note=cc_note)
