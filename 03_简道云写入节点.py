import json
import typing
from urllib.error import HTTPError
from urllib.request import Request, urlopen


data = {
    "result": "",
    "result.success": False,
    "result.inference": False,
    "attachments": [],
    "variables": {}
}


APP_ID = "6a4cc7e9d2ad50b1555e4e42"
ENTRY_ID = "6a4cc7eca2ce44a8d0123d41"
API_KEY = "wrCjUmragft9mMJw3XbkWiP4gDiBaOcf1D16dAc8972DeCe3eF40fD05b32029c0"
CREATE_URL = "https://api.jiandaoyun.com/api/v5/app/entry/data/create"


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


def _text_value(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join([str(v) for v in value if v not in (None, "")]).strip()
    return str(value).strip()


def _wrap(value):
    return {"value": value}


def _build_payload(email_info, customer_info, driver_vehicle_info, source_order_info):
    customer_info = customer_info or [{}]
    driver_vehicle_info = driver_vehicle_info or [{}]
    source_order_info = source_order_info or []
    mail_body = _text_value(email_info.get("mail_body", "")) or _text_value(email_info.get("text_plain", []))
    if not mail_body:
        mail_body = _text_value(email_info.get("subject", ""))

    customer_row = customer_info[0] if customer_info else {}
    vehicle_row = driver_vehicle_info[0] if driver_vehicle_info else {}

    data_payload = {
        "company_name": _wrap(_safe_get(email_info, "company_name", default="")),
        "job_type": _wrap(_safe_get(email_info, "job_type", default="")),
        "sender_id": _wrap(_safe_get(email_info, "from_", "from_email", default="")),
        "recipient_id": _wrap(_safe_get(email_info, "to", default="")),
        "mail_subject": _wrap(_safe_get(email_info, "subject", default="")),
        "mail_body": _wrap(mail_body),
        "customer_info": _wrap([{
            "customer_company_name": _wrap(_safe_get(customer_row, "customer_company_name", default="")),
            "customer_contact_name": _wrap(_safe_get(customer_row, "customer_contact_name", default="")),
            "customer_phone": _wrap(_safe_get(customer_row, "customer_phone", default="")),
            "customer_email": _wrap(_safe_get(customer_row, "customer_email", default="")),
            "customer_address": _wrap(_safe_get(customer_row, "customer_address", default="")),
        }]),
        "driver_vehicle_info": _wrap([{
            "vehicle_number": _wrap(_safe_get(vehicle_row, "vehicle_number", default="")),
            "trailer_number": _wrap(_safe_get(vehicle_row, "trailer_number", default="")),
            "driver_name": _wrap(_safe_get(vehicle_row, "driver_name", default="")),
            "id_number": _wrap(_safe_get(vehicle_row, "id_number", default="")),
            "driver_phone": _wrap(_safe_get(vehicle_row, "driver_phone", default="")),
            "escort_name": _wrap(_safe_get(vehicle_row, "escort_name", default="")),
        }]),
        "source_order_info": _wrap([{
            "shipper_name": _wrap(_safe_get(item, "shipper_name", default="")),
            "source_job_type": _wrap(_safe_get(item, "source_job_type", default="")),
            "job_date": _wrap(_safe_get(item, "job_date", default="")),
            "job_time": _wrap(_safe_get(item, "job_time", default="")),
            "job_code": _wrap(_safe_get(item, "job_code", default="")),
            "order_number": _wrap(_safe_get(item, "order_number", default="")),
            "material_code": _wrap(_safe_get(item, "material_code", default="")),
            "product_name": _wrap(_safe_get(item, "product_name", default="")),
            "batch_number": _wrap(_safe_get(item, "batch_number", default="")),
            "unit": _wrap(_safe_get(item, "unit", default="")),
            "specification": _wrap(_safe_get(item, "specification", default="")),
            "status": _wrap(_safe_get(item, "status", default="")),
            "quantity": _wrap(_safe_get(item, "quantity", default="")),
            "weight": _wrap(_safe_get(item, "weight", default="")),
        } for item in source_order_info]),
    }

    payload = {
        "app_id": APP_ID,
        "entry_id": ENTRY_ID,
        "is_start_workflow": False,
        "is_start_trigger": False,
        "data": data_payload
    }
    return payload


def _post_json(url, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {API_KEY}")
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except HTTPError as exc:
        body_text = ""
        try:
            body_text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body_text = ""
        raise Exception(f"jiandaoyun http {exc.code}: {body_text or exc.reason}") from exc


def main(*args, tool_args: dict, **kwargs) -> typing.Any:
    """Run Tool"""

    data = _new_data()
    email_info = kwargs.get("variables", {}).get("email_info", {}) or {}
    customer_info = kwargs.get("variables", {}).get("customer_info", []) or []
    driver_vehicle_info = kwargs.get("variables", {}).get("driver_vehicle_info", []) or []
    source_order_info = kwargs.get("variables", {}).get("source_order_info", []) or []

    if not source_order_info:
        data["result.success"] = False
        data["result.inference"] = False
        data["result"] = "no parsed orders"
        return data

    payload = _build_payload(email_info, customer_info, driver_vehicle_info, source_order_info)
    try:
        response = _post_json(CREATE_URL, payload)
    except Exception as exc:
        data["result.success"] = False
        data["result.inference"] = False
        data["result"] = str(exc)
        data["variables"]["jdy_payload"] = payload
        return data

    data["result.success"] = True
    data["result.inference"] = True
    data["result"] = json.dumps(response, ensure_ascii=False)
    data["variables"]["jdy_create_response"] = response
    data["variables"]["jdy_entry_id"] = ENTRY_ID
    data["variables"]["jdy_app_id"] = APP_ID
    if isinstance(response, dict):
        data_obj = response.get("data") or {}
        if isinstance(data_obj, dict) and data_obj.get("_id"):
            data["variables"]["jdy_data_id"] = data_obj.get("_id")
    return data
