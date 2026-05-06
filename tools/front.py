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
    try:
        conv = await get_conversation(conversation_id)
        recipient = conv.get("recipient", {})
        sender_email = recipient.get("handle", "")
        # channel_id must be a channel resource alias, not an inbox id
        # Fetch inboxes to get the address, then build alt:address: alias
        channel_id = None
        async with httpx.AsyncClient() as c:
            ri = await c.get(f"{BASE_URL}/conversations/{conversation_id}/inboxes", headers=HEADERS)
            if ri.status_code == 200:
                results = ri.json().get("_results", [])
                if results:
                    address = results[0].get("address") or results[0].get("send_as")
                    if address:
                        channel_id = f"alt:address:{address}"
    except Exception as e:
        logging.error("create_draft setup failed: %s", e)
        sender_email = ""
        channel_id = None

    html_body = "<p>" + body.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
    payload = {"body": html_body, "mode": "shared"}
    if channel_id:
        payload["channel_id"] = channel_id
    if sender_email:
        payload["to"] = [sender_email]
    if author_id:
        payload["author_id"] = author_id
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/conversations/{conversation_id}/drafts",
            headers=HEADERS,
            json=payload,
        )
        if r.status_code not in (200, 201, 202, 204):
            logging.error("Front draft failed: %s %s", r.status_code, r.text)
        return r.status_code in (200, 201, 202, 204)


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


async def forward_conversation(conversation_id: str, to_email: str, cc_email: str = None) -> bool:
    payload = {
        "to": [to_email],
        "body": f"Forwarded conversation: {conversation_id}",
        "type": "email",
    }
    if cc_email:
        payload["cc"] = [cc_email]
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/conversations/{conversation_id}/messages",
            headers=HEADERS,
            json=payload,
        )
        return r.status_code == 202


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
