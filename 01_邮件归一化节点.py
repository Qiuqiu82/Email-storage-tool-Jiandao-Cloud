import json
import typing
from email.utils import parseaddr
from urllib.parse import unquote


data = {
    "result": "",
    "result.success": False,
    "result.inference": False,
    "attachments": [],
    "variables": {}
}


def _new_data():
    return {
        "result": "",
        "result.success": False,
        "result.inference": False,
        "attachments": [],
        "variables": {}
    }


def _safe_get(source: dict, *keys, default=None):
    for key in keys:
        if isinstance(source, dict) and source.get(key) not in (None, ""):
            return source.get(key)
    return default


def _load_json(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except Exception:
            return {}
    return {}


def _normalize_text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join([str(item) for item in value if item not in (None, "")]).strip()
    return str(value).strip()


def _split_addresses(raw_value):
    if not raw_value:
        return []
    if isinstance(raw_value, list):
        raw_value = ",".join([str(item) for item in raw_value if item not in (None, "")])
    parts = []
    for part in str(raw_value).replace(";", ",").split(","):
        part = part.strip()
        if part:
            parts.append(part)
    return parts


def _extract_email(raw_value):
    if not raw_value:
        return ""
    _, address = parseaddr(str(raw_value))
    return address or str(raw_value).strip()


def _extract_headers(kwargs):
    raw_headers = (
        kwargs.get("tool_config", {})
        .get("context", {})
        .get("x-headers", {})
        .get("x-mail-headers")
    )
    if not raw_headers:
        return {}
    decoded = unquote(raw_headers)
    if isinstance(decoded, str):
        try:
            return json.loads(decoded)
        except Exception:
            return {}
    if isinstance(decoded, dict):
        return decoded
    return {}


def _collect_sources(kwargs):
    sources = []

    question = kwargs.get("question", "")
    if isinstance(question, dict):
        sources.append(question)
    elif isinstance(question, str):
        sources.append(_load_json(question))

    attachments = kwargs.get("attachments", []) or []
    if isinstance(attachments, list) and attachments:
        first = attachments[0]
        if isinstance(first, dict):
            sources.append(_load_json(first.get("data", {})))

    variables = kwargs.get("variables", {}) or {}
    sources.append(_load_json(variables.get("email_info", {})))

    return [source for source in sources if isinstance(source, dict) and source]


def _get_main_email_id(headers, fallback_message_id):
    reference_text = headers.get("References", "") or headers.get("references", "")
    if reference_text:
        first_reference = str(reference_text).split()[0].strip()
        if first_reference:
            return first_reference
    return fallback_message_id


def _infer_job_type(subject, body):
    text = " ".join([value for value in [subject, body] if value])
    if "入库" in text:
        return "入库"
    if "出库" in text:
        return "出库"
    return ""


def _normalize_email_info(kwargs):
    headers = _extract_headers(kwargs)
    merged = {}
    for source in _collect_sources(kwargs):
        merged.update(source)

    from_value = _safe_get(merged, "from_", "from", default="")
    to_value = _safe_get(merged, "to", default="")
    cc_value = _safe_get(merged, "cc", default="")
    subject = _normalize_text(_safe_get(merged, "subject", default=""))
    date_value = _normalize_text(_safe_get(merged, "date", "Date", default=""))
    text_plain = _safe_get(merged, "text_plain", default=[])
    text_html = _safe_get(merged, "text_html", default=[])
    attachments = _safe_get(merged, "attachments", default=[])
    if not isinstance(attachments, list):
        attachments = []

    header_message_id = _normalize_text(headers.get("Message-ID", "") or headers.get("message-id", ""))
    payload_message_id = _normalize_text(_safe_get(merged, "message_id", default=""))
    message_id = header_message_id or payload_message_id
    main_email_id = _get_main_email_id(headers, message_id)

    mail_body = _normalize_text(text_plain) or _normalize_text(text_html)
    sender_email = _extract_email(from_value)
    recipient_emails = [_extract_email(item) for item in _split_addresses(to_value)]
    cc_emails = [_extract_email(item) for item in _split_addresses(cc_value)]

    email_info = {
        "from_": _normalize_text(from_value),
        "from_email": sender_email,
        "to": _normalize_text(to_value),
        "to_emails": [item for item in recipient_emails if item],
        "cc": _normalize_text(cc_value),
        "cc_emails": [item for item in cc_emails if item],
        "date": date_value,
        "subject": subject,
        "message_id": message_id,
        "main_email_id": main_email_id,
        "text_plain": text_plain if isinstance(text_plain, list) else ([mail_body] if mail_body else []),
        "text_html": text_html if isinstance(text_html, list) else ([_normalize_text(text_html)] if text_html else []),
        "mail_body": mail_body,
        "attachments": attachments,
        "select_folder": _normalize_text(_safe_get(merged, "select_folder", default="")),
        "folder_uidvalidity": _normalize_text(_safe_get(merged, "folder_uidvalidity", default="")),
        "eml_url": _normalize_text(_safe_get(merged, "eml_url", default="")),
        "headers_json": _safe_get(merged, "headers_json", default=""),
        "raw_headers": headers,
    }
    email_info["job_type"] = _infer_job_type(subject, mail_body)
    email_info["company_name"] = ""
    return email_info


def main(*args, tool_args: dict, **kwargs) -> typing.Any:
    data = _new_data()
    email_info = _normalize_email_info(kwargs)
    data["variables"]["email_info"] = email_info
    data["variables"]["mail_body"] = email_info.get("mail_body", "")
    data["variables"]["mail_subject"] = email_info.get("subject", "")
    data["variables"]["main_email_id"] = email_info.get("main_email_id", "")
    data["variables"]["message_id"] = email_info.get("message_id", "")
    data["result.success"] = True
    data["result.inference"] = True
    data["result"] = "email normalized"
    return data
