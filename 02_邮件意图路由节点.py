import json
import typing


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


def _text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join([str(item) for item in value if item not in (None, "")]).strip()
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _fallback_intent(email_info):
    subject = _text(email_info.get("subject", ""))
    body = _text(email_info.get("mail_body", "")) or _text(email_info.get("text_plain", ""))
    attachments = email_info.get("attachments", []) or []
    attachment_names = " ".join([
        _text(item.get("filename", "")) for item in attachments if isinstance(item, dict)
    ])
    text = " ".join([subject, body, attachment_names])

    keywords = [
        "入库", "出库", "提货", "送货", "任务单", "订单号",
        "物料号", "品名", "批号", "货主", "作业类型"
    ]
    if any(keyword in text for keyword in keywords):
        return "出入库"
    return "其他"


def _normalize_intent(raw_intent, email_info):
    text = _text(raw_intent)
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
            text = _text(
                parsed.get("mail_intent")
                or parsed.get("intent")
                or parsed.get("result")
                or parsed
            )
        except Exception:
            pass
    if "出入库" in text:
        return "出入库"
    if "入库" in text or "出库" in text:
        return "出入库"
    if "其他" in text:
        return "其他"
    return _fallback_intent(email_info)


def main(*args, tool_args: dict, **kwargs) -> typing.Any:
    data = _new_data()
    variables = kwargs.get("variables", {}) or {}
    email_info = variables.get("email_info", {}) or {}

    # 大模型节点默认会把 Text 输出放在 result；若你设置了自定义变量，也可以从 variables 里取。
    raw_intent = (
        variables.get("mail_intent_llm")
        or variables.get("intent_result")
        or kwargs.get("result", "")
    )
    mail_intent = _normalize_intent(raw_intent, email_info)
    is_inoutbound_mail = mail_intent == "出入库"

    fixed_reply_message = (
        "您好，您的邮件已收到。当前邮件内容不属于出入库任务单处理范围，"
        "系统暂不生成入库单或出库单。如需处理出入库业务，请发送包含出入库任务单附件的邮件。"
    )

    data["variables"]["mail_intent_raw"] = _text(raw_intent)
    data["variables"]["mail_intent"] = mail_intent
    data["variables"]["is_inoutbound_mail"] = is_inoutbound_mail
    data["variables"]["fixed_reply_message"] = fixed_reply_message
    data["result.success"] = True
    data["result.inference"] = True
    data["result"] = json.dumps(
        {
            "mail_intent": mail_intent,
            "is_inoutbound_mail": is_inoutbound_mail,
        },
        ensure_ascii=False
    )
    return data
