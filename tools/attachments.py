import base64
from tools.front import get_attachment

IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/jpg"}


async def fetch_attachments_as_base64(attachments: list[dict]) -> list[dict]:
    result = []
    for att in attachments:
        url = att.get("url")
        content_type = att.get("content_type", "")
        if not url:
            continue
        # Skip non-image attachments (PDF, Word, CSV, etc.)
        if content_type.lower() not in IMAGE_TYPES:
            continue
        try:
            data = await get_attachment(url)
            b64 = base64.b64encode(data).decode("utf-8")
            result.append({"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{b64}"}})
        except Exception:
            pass
    return result
