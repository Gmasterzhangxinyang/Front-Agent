import httpx
from config import settings

BASE_URL = "https://api2.frontapp.com"
HEADERS = {
    "Authorization": f"Bearer {settings.front_api_token}",
    "Content-Type": "application/json",
}


async def get_conversation_messages(conversation_id: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/conversations/{conversation_id}/messages", headers=HEADERS)
        r.raise_for_status()
        return r.json().get("_results", [])


async def get_conversation(conversation_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/conversations/{conversation_id}", headers=HEADERS)
        r.raise_for_status()
        return r.json()


async def create_draft(conversation_id: str, body: str, author_id: str = None) -> bool:
    import logging
    sender_email = ""
    channel_id = None

    try:
        conv = await get_conversation(conversation_id)
        recipient = conv.get("recipient", {})
        sender_email = recipient.get("handle", "")
    except Exception as e:
        logging.error("create_draft: failed to get conversation: %s", e)

    # Fetch channel_id from inboxes
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            ri = await c.get(f"{BASE_URL}/conversations/{conversation_id}/inboxes", headers=HEADERS)
            if ri.status_code == 200:
                results = ri.json().get("_results", [])
                if results:
                    address = results[0].get("address") or results[0].get("send_as")
                    if address:
                        channel_id = f"alt:address:{address}"
    except Exception as e:
        logging.error("create_draft: failed to get channel_id: %s", e)

    if not channel_id:
        logging.error("create_draft: channel_id is None, draft will likely fail")

    html_body = "<p>" + body.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
    payload = {"body": html_body, "mode": "shared"}
    if channel_id:
        payload["channel_id"] = channel_id
    if sender_email:
        payload["to"] = [sender_email]
    if author_id:
        payload["author_id"] = author_id

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{BASE_URL}/conversations/{conversation_id}/drafts",
                headers=HEADERS,
                json=payload,
            )
            if r.status_code not in (200, 201, 202, 204):
                logging.error("Front draft failed: %s %s", r.status_code, r.text)
            return r.status_code in (200, 201, 202, 204)
    except Exception as e:
        logging.error("create_draft: request failed: %s", e)
        return False


async def reply_to_conversation(conversation_id: str, body: str, author_id: str = None) -> bool:
    import logging
    try:
        conv = await get_conversation(conversation_id)
        recipient = conv.get("recipient", {})
        sender_email = recipient.get("handle", "")
    except Exception:
        sender_email = ""

    html_body = body.replace("\n", "<br>")
    payload = {"body": html_body, "type": "email"}
    if sender_email:
        payload["to"] = [sender_email]
    if author_id:
        payload["author_id"] = author_id
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/conversations/{conversation_id}/messages",
            headers=HEADERS,
            json=payload,
        )
        if r.status_code != 202:
            logging.error("Front reply failed: %s %s", r.status_code, r.text)
        return r.status_code == 202


async def assign_conversation(conversation_id: str, teammate_id: str) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{BASE_URL}/conversations/{conversation_id}",
            headers=HEADERS,
            json={"assignee_id": teammate_id},
        )
        return r.status_code == 204


async def resolve_conversation(conversation_id: str) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{BASE_URL}/conversations/{conversation_id}",
            headers=HEADERS,
            json={"status": "archived"},
        )
        return r.status_code == 204


async def add_comment(conversation_id: str, body: str, author_id: str = None) -> bool:
    payload = {"body": body}
    if author_id:
        payload["author_id"] = author_id
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/conversations/{conversation_id}/comments",
            headers=HEADERS,
            json=payload,
        )
        return r.status_code == 201


async def forward_conversation(conversation_id: str, to_email: str, cc_email: str = None, summary: str = "") -> bool:
    """Create a forward draft (for partnership type - requires Bobby review)."""
    import logging
    try:
        channel_id = None
        sender_email = ""

        try:
            conv = await get_conversation(conversation_id)
            recipient = conv.get("recipient", {})
            sender_email = recipient.get("handle", "")
        except Exception as e:
            logging.error("forward_conversation: failed to get conversation: %s", e)

        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                ri = await c.get(f"{BASE_URL}/conversations/{conversation_id}/inboxes", headers=HEADERS)
                if ri.status_code == 200:
                    results = ri.json().get("_results", [])
                    if results:
                        address = results[0].get("address") or results[0].get("send_as")
                        if address:
                            channel_id = f"alt:address:{address}"
        except Exception as e:
            logging.error("forward_conversation: failed to get channel_id: %s", e)

        if not channel_id:
            logging.error("forward_conversation: channel_id is None, forward will likely fail")

        if summary:
            body = f"Forwarding partnership/reseller inquiry:\n\n{summary}\n\nFrom: {sender_email}\nConversation ID: {conversation_id}"
        else:
            body = f"Forwarded conversation from {sender_email}\n\nConversation ID: {conversation_id}"

        html_body = "<p>" + body.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"

        payload = {
            "to": [to_email],
            "body": html_body,
            "mode": "shared",
        }
        if cc_email:
            payload["cc"] = [cc_email]
        if channel_id:
            payload["channel_id"] = channel_id

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{BASE_URL}/conversations/{conversation_id}/drafts",
                    headers=HEADERS,
                    json=payload,
                )
                if r.status_code not in (200, 201, 202, 204):
                    logging.error("Front forward draft failed: %s %s", r.status_code, r.text)
                return r.status_code in (200, 201, 202, 204)
        except Exception as e:
            logging.error("forward_conversation: request failed: %s", e)
            return False
    except Exception as e:
        logging.error("forward_conversation failed: %s", e)
        return False


async def forward_conversation_direct(conversation_id: str, to_email: str, cc_email: str = None, summary: str = "") -> bool:
    """Forward conversation directly without draft (for community type - sends immediately)."""
    import logging
    try:
        channel_id = None
        sender_email = ""

        try:
            conv = await get_conversation(conversation_id)
            recipient = conv.get("recipient", {})
            sender_email = recipient.get("handle", "")
        except Exception as e:
            logging.error("forward_conversation_direct: failed to get conversation: %s", e)

        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                ri = await c.get(f"{BASE_URL}/conversations/{conversation_id}/inboxes", headers=HEADERS)
                if ri.status_code == 200:
                    results = ri.json().get("_results", [])
                    if results:
                        address = results[0].get("address") or results[0].get("send_as")
                        if address:
                            channel_id = f"alt:address:{address}"
        except Exception as e:
            logging.error("forward_conversation_direct: failed to get channel_id: %s", e)

        if not channel_id:
            logging.error("forward_conversation_direct: channel_id is None, forward will likely fail")

        if summary:
            body = f"Forwarding community inquiry:\n\n{summary}\n\nFrom: {sender_email}\nConversation ID: {conversation_id}"
        else:
            body = f"Forwarded conversation from {sender_email}\n\nConversation ID: {conversation_id}"

        html_body = "<p>" + body.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"

        payload = {
            "to": [to_email],
            "body": html_body,
            "type": "email",
        }
        if cc_email:
            payload["cc"] = [cc_email]
        if channel_id:
            payload["channel_id"] = channel_id

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{BASE_URL}/conversations/{conversation_id}/messages",
                    headers=HEADERS,
                    json=payload,
                )
                if r.status_code != 202:
                    logging.error("Front forward direct failed: %s %s", r.status_code, r.text)
                return r.status_code == 202
        except Exception as e:
            logging.error("forward_conversation_direct: request failed: %s", e)
            return False
    except Exception as e:
        logging.error("forward_conversation_direct failed: %s", e)
        return False


async def get_inbox_by_name(inbox_name: str) -> str | None:
    """Get inbox ID by name or email address. Returns inbox_id or None."""
    import logging
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{BASE_URL}/inboxes", headers=HEADERS)
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
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.patch(
                f"{BASE_URL}/conversations/{conversation_id}",
                headers=HEADERS,
                json={"inbox_id": inbox_id},
            )
            if r.status_code != 204:
                logging.error("move_conversation_to_inbox failed: %s %s", r.status_code, r.text)
            return r.status_code == 204
    except Exception as e:
        logging.error("move_conversation_to_inbox request failed: %s", e)
        return False


async def add_tag(conversation_id: str, tag_id: str) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/conversations/{conversation_id}/tags",
            headers=HEADERS,
            json={"tag_ids": [tag_id]},
        )
        return r.status_code == 204


async def get_attachment(attachment_url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        r = await client.get(attachment_url, headers={"Authorization": f"Bearer {settings.front_api_token}"})
        r.raise_for_status()
        return r.content
