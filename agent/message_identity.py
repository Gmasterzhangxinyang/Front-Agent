"""Front message identity helpers.

Front can mark messages inside an internally forwarded conversation as
``is_inbound=true``.  Treat the actual author/from addresses as the source of
truth so internal Dify traffic cannot re-enter the customer reply flow.
"""

from collections.abc import Mapping


INTERNAL_EMAIL_SUFFIX = "@dify.ai"


def _contact_email(value) -> str:
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, Mapping):
        return str(value.get("handle") or value.get("email") or "").strip().lower()
    return ""


def message_author_email(message: Mapping) -> str:
    return _contact_email(message.get("author"))


def message_from_email(message: Mapping) -> str:
    for field in ("from", "sender"):
        email = _contact_email(message.get(field))
        if email:
            return email

    recipients = message.get("recipients") or []
    if isinstance(recipients, list):
        for recipient in recipients:
            if not isinstance(recipient, Mapping):
                continue
            if str(recipient.get("role") or "").lower() != "from":
                continue
            email = _contact_email(recipient)
            if email:
                return email
    return ""


def is_internal_email(email: str | None) -> bool:
    return bool(email and email.strip().lower().endswith(INTERNAL_EMAIL_SUFFIX))


def has_internal_origin(message: Mapping) -> bool:
    return is_internal_email(message_author_email(message)) or is_internal_email(
        message_from_email(message)
    )


def external_sender_email(message: Mapping) -> str:
    sender = message_from_email(message)
    if sender and not is_internal_email(sender):
        return sender

    author = message_author_email(message)
    if author and not is_internal_email(author):
        return author
    return ""


def is_external_inbound_message(message: Mapping) -> bool:
    if not message:
        return False
    if message.get("is_draft") is True:
        return False
    if message.get("type") == "comment":
        return False
    if message.get("is_inbound") is False:
        return False
    if has_internal_origin(message):
        return False
    return bool(message.get("text") or message.get("body") or message.get("attachments"))


def conversation_message_role(message: Mapping) -> str:
    if (
        message.get("type") == "email"
        and message.get("is_draft") is not True
        and message.get("is_inbound") is not False
        and not has_internal_origin(message)
    ):
        return "User"
    return "Support"
