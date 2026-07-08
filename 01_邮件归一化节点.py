import json
import typing
from email.header import decode_header
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


def _split_addresses(raw_value):
    if not raw_value:
        return []
    if isinstance(raw_value, list):
        raw_value = ",".join([str(item) for item in raw_value if item not in (None, "")])
    text = str(raw_value)
    items = []
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if part:
            items.append(part)
    return items


def _extract_email_address(raw_value):
    if not raw_value:
        return ""
    _, addr = parseaddr(str(raw_value))
    return addr or str(raw_value).strip()


def _normalize_text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join([str(v) for v in value if v not in (None, "")]).strip()
    return str(value).strip()


def _extract_headers(kwargs):
    headers_raw = (
        kwargs.get("tool_config", {})
        .get("context", {})
        .get("x-headers", {})
        .get("x-mail-headers")
    )
    if not headers_raw:
        return {}
    decoded = unquote(headers_raw)
    if isinstance(decoded, str):
        try:
            return json.loads(decoded)
        except Exception:
            return {}
    if isinstance(decoded, dict):
        return decoded
    return {}


def _collect_email_sources(kwargs):
    sources = []

    question = kwargs.get("question", "")
    if isinstance(question, str):
        sources.append(_load_json(question))
    elif isinstance(question, dict):
        sources.append(question)

    attachments = kwargs.get("attachments", []) or []
    if attachments and isinstance(attachments, list):
        first = attachments[0]
        if isinstance(first, dict):
            sources.append(_load_json(first.get("data", {})))

    sources.append(_load_json(kwargs.get("variables", {}).get("email_info", {})))
    return [src for src in sources if isinstance(src, dict) and src]


def _infer_job_type(subject, body, orders):
    candidates = []
    if orders:
        candidates.append(_safe_get(orders[0], "source_job_type", default=""))
    candidates.append(subject or "")
    candidates.append(body or "")
    text = " ".join([str(v) for v in candidates if v])
    if "入库" in text:
        return "入库"
    if "出库" in text:
        return "出库"
    return ""


def _infer_company_name(subject, orders, customer_company):
    if customer_company:
        return customer_company
    if orders:
        first_shipper = _safe_get(orders[0], "shipper_name", default="")
        if first_shipper:
            return first_shipper
    if subject:
        tail = str(subject).split("-")[-1].strip()
        tail = tail.replace(".xlsx", "").replace(".eml", "").strip()
        return tail
    return ""


def _normalize_email_info(kwargs):
    headers = _extract_headers(kwargs)
    sources = _collect_email_sources(kwargs)

    merged = {}
    for src in sources:
        merged.update(src)

    from_value = _safe_get(merged, "from_", "from", default="")
    to_value = _safe_get(merged, "to", default="")
    cc_value = _safe_get(merged, "cc", default="")
    subject = _safe_get(merged, "subject", default="")
    message_id = _safe_get(merged, "message_id", "Message-ID", default="")
    date_value = _safe_get(merged, "date", "Date", default="")
    text_plain = _safe_get(merged, "text_plain", default=[])
    text_html = _safe_get(merged, "text_html", default=[])
    attachments = _safe_get(merged, "attachments", default=[])

    if not isinstance(attachments, list):
        attachments = []

    reference_text = headers.get("References", "") or headers.get("references", "")
    main_message_id = ""
    if reference_text:
        main_message_id = str(reference_text).split(" ")[0].strip()
    if not main_message_id:
        main_message_id = message_id

    mail_body = _normalize_text(text_plain) or _normalize_text(text_html)
    sender_email = _extract_email_address(from_value)
    recipient_emails = [_extract_email_address(item) for item in _split_addresses(to_value)]
    recipient_emails = [item for item in recipient_emails if item]
    cc_emails = [_extract_email_address(item) for item in _split_addresses(cc_value)]
    cc_emails = [item for item in cc_emails if item]

    email_info = {
        "from_": _normalize_text(from_value),
        "from_email": sender_email,
        "to": _normalize_text(to_value),
        "to_emails": recipient_emails,
        "cc": _normalize_text(cc_value),
        "cc_emails": cc_emails,
        "date": _normalize_text(date_value),
        "subject": _normalize_text(subject),
        "message_id": _normalize_text(message_id),
        "main_message_id": _normalize_text(main_message_id),
        "text_plain": text_plain if isinstance(text_plain, list) else [mail_body] if mail_body else [],
        "text_html": text_html if isinstance(text_html, list) else ([text_html] if text_html else []),
        "mail_body": mail_body,
        "attachments": attachments,
        "select_folder": _safe_get(merged, "select_folder", default=""),
        "folder_uidvalidity": _safe_get(merged, "folder_uidvalidity", default=""),
        "eml_url": _safe_get(merged, "eml_url", default=""),
        "headers_json": _safe_get(merged, "headers_json", default=""),
        "raw_headers": headers,
    }
    email_info["job_type"] = _infer_job_type(email_info["subject"], email_info["mail_body"], [])
    email_info["company_name"] = _infer_company_name(email_info["subject"], [], "")
    return email_info


def main(*args, tool_args: dict, **kwargs) -> typing.Any:
    """Run Tool"""

    data = _new_data()
    email_info = _normalize_email_info(kwargs)
    data["variables"]["email_info"] = email_info
    data["variables"]["mail_body"] = email_info.get("mail_body", "")
    data["variables"]["mail_subject"] = email_info.get("subject", "")
    data["variables"]["main_message_id"] = email_info.get("main_message_id", "")
    data["result.success"] = True
    data["result.inference"] = True
    data["result"] = "email normalized"
    return data
