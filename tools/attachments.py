import base64
import io
from tools.front import get_attachment

IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/jpg"}
DOC_TYPES = {"application/pdf", "application/msword",
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


async def fetch_attachments_as_base64(attachments: list[dict]) -> list[dict]:
    result = []
    for att in attachments:
        url = att.get("url")
        content_type = att.get("content_type", "")
        if not url:
            continue
        if content_type.lower() not in IMAGE_TYPES:
            continue
        try:
            data = await get_attachment(url)
            b64 = base64.b64encode(data).decode("utf-8")
            result.append({"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{b64}"}})
        except Exception:
            pass
    return result


async def fetch_attachments_as_text(attachments: list[dict]) -> list[dict]:
    """Extract text content from PDF and Word attachments."""
    result = []
    for att in attachments:
        url = att.get("url")
        content_type = att.get("content_type", "")
        filename = att.get("filename", "attachment")
        if not url:
            continue
        if content_type.lower() not in DOC_TYPES:
            continue
        try:
            data = await get_attachment(url)
            text = await _extract_text(data, content_type, filename)
            if text:
                result.append({"filename": filename, "content_type": content_type, "text": text})
        except Exception:
            pass
    return result


async def _extract_text(data: bytes, content_type: str, filename: str) -> str:
    """Extract text from PDF or Word document using Python libraries."""
    try:
        if "pdf" in content_type.lower():
            import io
            from pdfminer.high_level import extract_text
            pdf_file = io.BytesIO(data)
            text = extract_text(pdf_file)
            return text.strip() if text else ""
        elif "word" in content_type.lower() or "document" in content_type.lower():
            import io
            from docx import Document
            doc_file = io.BytesIO(data)
            doc = Document(doc_file)
            return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to extract text from {filename}: {e}")
    return ""
