import asyncio
import html
import logging
import re
from urllib.parse import urlsplit

import httpx
import markdown
from bs4 import BeautifulSoup, Comment
from config import settings

BASE_URL = "https://api2.frontapp.com"
HEADERS = {
    "Authorization": f"Bearer {settings.front_api_token}",
    "Content-Type": "application/json",
}

FRONT_TIMEOUT = httpx.Timeout(30.0, connect=8.0, read=20.0, write=10.0, pool=5.0)
FRONT_TRANSIENT_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}
FRONT_TRANSIENT_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
    httpx.NetworkError,
)


class AttachmentDownloadRejected(ValueError):
    pass


class AttachmentTooLarge(ValueError):
    pass


def _attachment_allowed_hosts() -> set[str]:
    return {
        host.strip().lower().rstrip(".")
        for host in settings.front_attachment_allowed_hosts.split(",")
        if host.strip()
    }


def validate_attachment_url(attachment_url: str) -> str:
    try:
        parsed = urlsplit(attachment_url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise AttachmentDownloadRejected("invalid attachment URL") from exc

    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() != "https":
        raise AttachmentDownloadRejected("attachment URL must use HTTPS")
    if parsed.username or parsed.password:
        raise AttachmentDownloadRejected(
            "attachment URL cannot contain credentials"
        )
    if port not in (None, 443):
        raise AttachmentDownloadRejected(
            "attachment URL uses a non-default port"
        )
    if hostname not in _attachment_allowed_hosts():
        raise AttachmentDownloadRejected(
            f"attachment host is not allowed: {hostname or '<missing>'}"
        )
    return attachment_url


async def read_limited_attachment(
    response: httpx.Response,
    max_bytes: int,
) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = 0
        if declared_size > max_bytes:
            raise AttachmentTooLarge(
                f"attachment exceeds {max_bytes} bytes"
            )

    content = bytearray()
    async for chunk in response.aiter_bytes():
        if len(content) + len(chunk) > max_bytes:
            raise AttachmentTooLarge(
                f"attachment exceeds {max_bytes} bytes"
            )
        content.extend(chunk)
    return bytes(content)


async def front_request(method: str, url: str, *, retries: int = 5, headers: dict | None = None, **kwargs) -> httpx.Response:
    """Call Front with retries for transient proxy/network failures."""
    request_headers = headers or HEADERS
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=FRONT_TIMEOUT) as client:
                response = await client.request(method, url, headers=request_headers, **kwargs)
            if response.status_code not in FRONT_TRANSIENT_STATUSES or attempt == retries:
                return response
            logging.warning(
                "Front API transient status %s for %s %s (%s/%s): %s",
                response.status_code,
                method,
                url,
                attempt,
                retries,
                response.text[:500],
            )
        except FRONT_TRANSIENT_EXCEPTIONS as exc:
            last_error = exc
            if attempt == retries:
                raise
            logging.warning("Front API transient error for %s %s (%s/%s): %r", method, url, attempt, retries, exc)

        await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

    assert last_error is not None
    raise last_error


async def get_conversation_messages(conversation_id: str) -> list[dict]:
    r = await front_request("GET", f"{BASE_URL}/conversations/{conversation_id}/messages")
    r.raise_for_status()
    return r.json().get("_results", [])


async def get_conversation(conversation_id: str) -> dict:
    r = await front_request("GET", f"{BASE_URL}/conversations/{conversation_id}")
    r.raise_for_status()
    return r.json()


def _email_list(value: str | list[str] | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [item.strip() for item in value if item and item.strip()]
    return [item.strip() for item in value.split(",") if item.strip()]


def _message_sender(msg: dict) -> str:
    sender = msg.get("sender") or msg.get("from") or {}
    if isinstance(sender, dict):
        return sender.get("handle") or sender.get("email") or sender.get("name") or "Unknown sender"
    return str(sender) if sender else "Unknown sender"


def _message_timestamp(msg: dict) -> str:
    return msg.get("created_at") or msg.get("date") or msg.get("timestamp") or ""


def _message_role(msg: dict) -> str:
    if msg.get("is_inbound") is True:
        return "Customer"
    if msg.get("is_inbound") is False:
        return "Dify/Support"
    if msg.get("type") == "email" and not msg.get("is_draft"):
        return "Customer"
    return "Dify/Support"



def _message_subject(msg: dict) -> str:
    if msg.get("subject"):
        return str(msg.get("subject")).strip()
    headers = msg.get("headers") or {}
    if isinstance(headers, dict) and headers.get("subject"):
        return str(headers.get("subject")).strip()
    return "No subject"


def _message_recipients(msg: dict, field: str) -> str:
    values = msg.get(field) or []
    recipients = []

    if isinstance(values, str):
        values = [item.strip() for item in values.split(",") if item.strip()]

    if isinstance(values, list):
        for item in values:
            if isinstance(item, str):
                if item.strip():
                    recipients.append(item.strip())
            elif isinstance(item, dict):
                for key in ("handle", "email", "name"):
                    value = item.get(key)
                    if value:
                        recipients.append(str(value).strip())
                        break
            else:
                recipients.append(str(item).strip())

    return ", ".join([r for r in recipients if r])

def _message_text(msg: dict) -> str:

    raw = msg.get("text") or msg.get("body") or ""
    text = str(raw).strip()
    if "<" in text and ">" in text:
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text = re.sub(r"(?i)</p\s*>", "\n\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = html.unescape(text)
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _attachment_lines(msg: dict) -> list[str]:
    attachments = msg.get("attachments") or []
    lines = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        name = attachment.get("filename") or attachment.get("name") or attachment.get("id") or "attachment"
        url = attachment.get("url") or attachment.get("download_url") or ""
        lines.append(f"- {name}" + (f" ({url})" if url else ""))
    return lines


def _plain_to_html(body: str) -> str:
    blocks = [block.strip() for block in body.split("\n\n") if block.strip()]
    if not blocks:
        return ""
    return "".join(f"<p>{html.escape(block).replace(chr(10), '<br>')}</p>" for block in blocks)


_MARKDOWN_ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "del",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
_MARKDOWN_DROP_TAGS = {"embed", "iframe", "math", "object", "script", "style", "svg"}
_MARKDOWN_LINK_SCHEMES = {"http", "https", "mailto"}
_MARKDOWN_LIST_ITEM_RE = re.compile(r"^ {0,3}(?:[-+*]|\d+[.)])\s+")


def _normalize_markdown_lists(body: str) -> str:
    """Let common email-style lists interrupt paragraphs without requiring blank lines."""
    normalized: list[str] = []
    in_list = False

    for line in body.splitlines():
        stripped = line.strip()
        is_list_item = bool(_MARKDOWN_LIST_ITEM_RE.match(line))

        if is_list_item:
            if normalized and normalized[-1].strip() and not in_list:
                normalized.append("")
            in_list = True
        elif in_list:
            if not stripped:
                in_list = False
            elif not line.startswith((" ", "\t")):
                normalized.append("")
                in_list = False

        normalized.append(line)

    return "\n".join(normalized)


def markdown_to_safe_html(body: str) -> str:
    """Render model-authored Markdown as the safe HTML expected by Front email bodies."""
    rendered = markdown.markdown(
        _normalize_markdown_lists(body or ""),
        extensions=["extra", "sane_lists", "nl2br"],
        output_format="html",
    )
    soup = BeautifulSoup(rendered, "html.parser")

    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for tag in soup.find_all(_MARKDOWN_DROP_TAGS):
        tag.decompose()

    for tag in soup.find_all(True):
        if tag.name not in _MARKDOWN_ALLOWED_TAGS:
            tag.unwrap()
            continue

        allowed_attributes = {"href", "title"} if tag.name == "a" else set()
        if tag.name == "ol":
            allowed_attributes.add("start")
        for attribute in list(tag.attrs):
            if attribute not in allowed_attributes:
                del tag.attrs[attribute]

        if tag.name == "a":
            href = str(tag.get("href") or "").strip()
            if urlsplit(href).scheme.lower() not in _MARKDOWN_LINK_SCHEMES:
                tag.unwrap()
                continue
            tag["href"] = href
            tag["target"] = "_blank"
            tag["rel"] = "noopener noreferrer"

    return str(soup)


async def _build_forward_body(conversation_id: str, summary: str, label: str) -> str:
    sender_email = ""
    try:
        conv = await get_conversation(conversation_id)
        recipient = conv.get("recipient", {})
        sender_email = recipient.get("handle", "")
    except Exception as e:
        logging.error("_build_forward_body: failed to get conversation %s: %s", conversation_id, e)

    lines = [
        f"Forwarding {label} inquiry.",
        f"Conversation ID: {conversation_id}",
    ]
    if sender_email:
        lines.append(f"Original sender: {sender_email}")
    if summary:
        lines.extend(["", "Summary:", summary])

    lines.extend(["", "Original Front conversation:"])

    try:
        messages = await get_conversation_messages(conversation_id)
    except Exception as e:
        logging.error("_build_forward_body: failed to get messages %s: %s", conversation_id, e)
        messages = []

    if not messages:
        lines.append("No message content could be fetched from Front. Please open the conversation in Front using the conversation ID above.")
        return "\n".join(lines)

    # Front returns newest first in this service; reverse for chronological timeline
    lines.append(f"Total messages: {len(messages)}")
    for index, msg in enumerate(reversed(messages), start=1):
        sender = _message_sender(msg)
        timestamp = _message_timestamp(msg)
        role = _message_role(msg)
        subject = _message_subject(msg)
        to_line = _message_recipients(msg, "to")
        cc_line = _message_recipients(msg, "cc")
        body = _message_text(msg) or "[No text body]"

        lines.extend([
            "",
            f"--- Message {index} | {role} | {sender}" + (f" | {timestamp}" if timestamp else ""),
            f"From: {sender}",
            f"To: {to_line if to_line else 'N/A'}",
            f"CC: {cc_line if cc_line else 'N/A'}",
            f"Date: {timestamp or 'N/A'}",
            f"Subject: {subject}",
            body,
        ])
        attachment_lines = _attachment_lines(msg)
        if attachment_lines:
            lines.append("Attachments:")
            lines.extend(attachment_lines)

    return "\n".join(lines)


async def create_draft(conversation_id: str, body: str, author_id: str = None, to_email: str | None = None) -> bool:
    import logging
    sender_email = to_email or ""
    channel_id = None

    try:
        conv = await get_conversation(conversation_id)
        recipient = conv.get("recipient", {})
        if not sender_email:
            sender_email = recipient.get("handle", "")
    except Exception as e:
        logging.error("create_draft: failed to get conversation: %s", e)

    # Fetch channel_id from inboxes
    try:
        ri = await front_request("GET", f"{BASE_URL}/conversations/{conversation_id}/inboxes")
        if ri.status_code == 200:
            results = ri.json().get("_results", [])
            # Prefer support or hello inbox
            for r in results:
                send_as = r.get("send_as", "")
                if send_as in ("support@dify.ai", "hello@dify.ai"):
                    channel_id = f"alt:address:{send_as}"
                    break
            if not channel_id and results:
                address = results[0].get("address") or results[0].get("send_as")
                if address:
                    channel_id = f"alt:address:{address}"
    except Exception as e:
        logging.error("create_draft: failed to get channel_id: %r", e)

    if not channel_id:
        logging.error("create_draft: channel_id is None, draft will likely fail")

    html_body = markdown_to_safe_html(body)
    payload = {"body": html_body, "mode": "shared"}
    if channel_id:
        payload["channel_id"] = channel_id
    if sender_email:
        payload["to"] = [sender_email]
    if author_id:
        payload["author_id"] = author_id

    try:
        r = await front_request(
            "POST",
            f"{BASE_URL}/conversations/{conversation_id}/drafts",
            json=payload,
        )
        if r.status_code not in (200, 201, 202, 204):
            logging.error("Front draft failed: %s %s", r.status_code, r.text)
        return r.status_code in (200, 201, 202, 204)
    except Exception as e:
        logging.error("create_draft: request failed: %r", e)
        return False


async def reply_to_conversation(conversation_id: str, body: str, author_id: str = None) -> bool:
    import logging
    sender_email = ""
    channel_id = None

    try:
        conv = await get_conversation(conversation_id)
        recipient = conv.get("recipient", {})
        sender_email = recipient.get("handle", "")
    except Exception as e:
        logging.error("reply_to_conversation: failed to get conversation: %s", e)

    try:
        ri = await front_request("GET", f"{BASE_URL}/conversations/{conversation_id}/inboxes")
        if ri.status_code == 200:
            results = ri.json().get("_results", [])
            # Prefer the inbox with support@dify.ai or hello@dify.ai send_as
            for r in results:
                send_as = r.get("send_as", "")
                if send_as in ("support@dify.ai", "hello@dify.ai"):
                    channel_id = f"alt:address:{send_as}"
                    break
            # Fallback to first inbox
            if not channel_id and results:
                address = results[0].get("address") or results[0].get("send_as")
                if address:
                    channel_id = f"alt:address:{address}"
    except Exception as e:
        logging.error("reply_to_conversation: failed to get channel_id: %r", e)

    html_body = markdown_to_safe_html(body)
    payload = {"body": html_body, "type": "email"}
    if sender_email:
        payload["to"] = [sender_email]
    if channel_id:
        payload["channel_id"] = channel_id
    if author_id:
        payload["author_id"] = author_id

    r = await front_request(
        "POST",
        f"{BASE_URL}/conversations/{conversation_id}/messages",
        json=payload,
    )
    if r.status_code != 202:
        logging.error("Front reply failed: %s %s", r.status_code, r.text)
    return r.status_code == 202


async def assign_conversation(conversation_id: str, teammate_id: str) -> bool:
    r = await front_request(
        "PATCH",
        f"{BASE_URL}/conversations/{conversation_id}",
        json={"assignee_id": teammate_id},
    )
    return r.status_code == 204


async def resolve_conversation(conversation_id: str) -> bool:
    r = await front_request(
        "PATCH",
        f"{BASE_URL}/conversations/{conversation_id}",
        json={"status": "archived"},
    )
    return r.status_code == 204


async def reopen_conversation(conversation_id: str) -> bool:
    r = await front_request(
        "PATCH",
        f"{BASE_URL}/conversations/{conversation_id}",
        json={"status": "open"},
    )
    return r.status_code == 204


async def add_comment(conversation_id: str, body: str, author_id: str = None) -> bool:
    payload = {"body": body}
    if author_id:
        payload["author_id"] = author_id
    r = await front_request(
        "POST",
        f"{BASE_URL}/conversations/{conversation_id}/comments",
        json=payload,
    )
    return r.status_code == 201


async def forward_conversation_direct(conversation_id: str, to_email: str, cc_email: str = None, summary: str = "", label: str = "partnership/community") -> bool:
    """Send an internal handoff by composing a normal outgoing email with summary and thread."""
    try:
        channel_id = None

        try:
            ri = await front_request("GET", f"{BASE_URL}/conversations/{conversation_id}/inboxes")
            if ri.status_code == 200:
                results = ri.json().get("_results", [])
                for r in results:
                    send_as = r.get("send_as", "")
                    if send_as in ("support@dify.ai", "hello@dify.ai"):
                        channel_id = f"alt:address:{send_as}"
                        break
                if not channel_id and results:
                    address = results[0].get("address") or results[0].get("send_as")
                    if address:
                        channel_id = f"alt:address:{address}"
        except Exception as e:
            logging.error("forward_conversation_direct: failed to get channel_id: %r", e)

        if not channel_id:
            logging.error("forward_conversation_direct: channel_id is None, forward will likely fail")

        body = await _build_forward_body(conversation_id, summary, label)
        payload = {
            "to": _email_list(to_email),
            "body": _plain_to_html(body),
            "type": "email",
        }
        cc = _email_list(cc_email)
        if cc:
            payload["cc"] = cc
        if channel_id:
            payload["channel_id"] = channel_id

        r = await front_request(
            "POST",
            f"{BASE_URL}/conversations/{conversation_id}/messages",
            json=payload,
        )
        if r.status_code != 202:
            logging.error("Front forward direct failed: %s %s", r.status_code, r.text)
        return r.status_code == 202
    except Exception as e:
        logging.error("forward_conversation_direct failed: %r", e)
        return False
async def get_inbox_by_name(inbox_name: str) -> str | None:
    """Get inbox ID by name or email address. Returns inbox_id or None."""
    import logging
    try:
        r = await front_request("GET", f"{BASE_URL}/inboxes")
        if r.status_code == 200:
            results = r.json().get("_results", [])
            inbox_name_lower = inbox_name.lower()
            for inbox in results:
                name = inbox.get("name", "")
                address = inbox.get("address") or ""
                send_as = inbox.get("send_as") or ""
                # Match by name (partial match) or email
                if name.lower() == inbox_name_lower or inbox_name_lower in name.lower():
                    return inbox.get("id")
                if address.lower() == inbox_name_lower or send_as.lower() == inbox_name_lower:
                    return inbox.get("id")
        logging.warning("get_inbox_by_name: no inbox found for %s", inbox_name)
        return None
    except Exception as e:
        logging.error("get_inbox_by_name failed: %s", e)
        return None


async def move_conversation_to_inbox(conversation_id: str, inbox_identifier: str) -> bool:
    """Move a conversation to a specific inbox by inbox name or email address."""
    import logging

    inbox_id = await get_inbox_by_name(inbox_identifier)
    if not inbox_id:
        logging.error("move_conversation_to_inbox: inbox not found for %s", inbox_identifier)
        return False

    try:
        r = await front_request(
            "PATCH",
            f"{BASE_URL}/conversations/{conversation_id}",
            json={"inbox_id": inbox_id},
        )
        if r.status_code != 204:
            logging.error("move_conversation_to_inbox failed: %s %s", r.status_code, r.text)
        return r.status_code == 204
    except Exception as e:
        logging.error("move_conversation_to_inbox request failed: %s", e)
        return False


async def add_tag(conversation_id: str, tag_id: str) -> bool:
    r = await front_request(
        "POST",
        f"{BASE_URL}/conversations/{conversation_id}/tags",
        json={"tag_ids": [tag_id]},
    )
    return r.status_code == 204


async def get_attachment(attachment_url: str) -> bytes:
    validated_url = validate_attachment_url(attachment_url)
    headers = {"Authorization": f"Bearer {settings.front_api_token}"}
    async with httpx.AsyncClient(timeout=FRONT_TIMEOUT) as client:
        async with client.stream(
            "GET",
            validated_url,
            headers=headers,
        ) as response:
            response.raise_for_status()
            return await read_limited_attachment(
                response,
                settings.max_attachment_bytes,
            )
