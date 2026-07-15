import json
import mimetypes
import typing
import uuid
from datetime import datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import requests


data = {
    "result": "",
    "result.success": False,
    "result.inference": False,
    "attachments": [],
    "variables": {}
}


APP_ID = "6a4cc7e9d2ad50b1555e4e42"
API_KEY = "wrCjUmragft9mMJw3XbkWiP4gDiBaOcf1D16dAc8972DeCe3eF40fD05b32029c0"
CREATE_URL = "https://api.jiandaoyun.com/api/v5/app/entry/data/create"
UPDATE_URL = "https://api.jiandaoyun.com/api/v5/app/entry/data/update"
LIST_URL = "https://api.jiandaoyun.com/api/v5/app/entry/data/list"
UPLOAD_TOKEN_URL = "https://api.jiandaoyun.com/api/v5/app/entry/file/get_upload_token"
EMAIL_LOG_ENTRY_ID = "6a5063eaac359ad34098cb12"
EMAIL_CENTER_ENTRY_ID = "6a548fa8477084704dc780ef"
OUTBOUND_ENTRY_ID = "6a5063312322f5b1acb33b32"
INBOUND_ENTRY_ID = "6a5063a0c1568ac27f292489"
SERIAL_FIELD_ID = "_widget_1783653197823"
OUTBOUND_CENTER_MAIN_EMAIL_FIELD = "_widget_1784008748955"
INBOUND_CENTER_MAIN_EMAIL_FIELD = "_widget_1784014377455"


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
        return "\n".join([str(item) for item in value if item not in (None, "")]).strip()
    return str(value).strip()


def _wrap(value):
    return {"value": value}


def _post_json(url, payload):
    request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=request_body, method="POST")
    request.add_header("Authorization", f"Bearer {API_KEY}")
    request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = ""
        try:
            error_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            error_body = ""
        raise Exception(f"jiandaoyun http {exc.code}: {error_body or exc.reason}") from exc


def _post_json_requests(url, payload):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    if response.status_code != 200:
        raise Exception(f"jiandaoyun http {response.status_code}: {response.text}")
    return response.json()


def _extract_created_id(response):
    if not isinstance(response, dict):
        return ""
    data_obj = response.get("data") or {}
    if isinstance(data_obj, dict):
        return _text_value(data_obj.get("_id", ""))
    return ""


def _extract_data_id(response, fallback=""):
    data_id = _extract_created_id(response)
    if data_id:
        return data_id
    return _text_value(fallback)


def _get_upload_tokens(entry_id, transaction_id):
    payload = {
        "app_id": APP_ID,
        "entry_id": entry_id,
        "transaction_id": transaction_id
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    response = requests.post(UPLOAD_TOKEN_URL, headers=headers, json=payload, timeout=60)
    if response.status_code != 200:
        raise Exception(f"get upload token failed: {response.status_code} {response.text}")
    result = response.json()
    return result.get("token_and_url_list", [])


def _download_file_bytes(file_url):
    response = requests.get(file_url, timeout=60)
    if response.status_code != 200:
        raise Exception(f"download attachment failed: {response.status_code}")
    return response.content


def _upload_single_file(upload_url, token, filename, file_bytes):
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }
    files = {
        "file": (filename, file_bytes, mime_type)
    }
    data_payload = {
        "token": token
    }
    response = requests.post(upload_url, headers=headers, data=data_payload, files=files, timeout=120)
    if response.status_code != 200:
        raise Exception(f"upload attachment failed: {response.status_code} {response.text}")
    result = response.json()
    file_key = result.get("key", "")
    if not file_key:
        raise Exception(f"upload attachment missing key: {json.dumps(result, ensure_ascii=False)}")
    return file_key


def _upload_email_attachments(email_info, entry_id):
    attachments = email_info.get("attachments", []) or []
    if not attachments:
        return "", []

    transaction_id = str(uuid.uuid4())
    token_pool = []
    file_keys = []

    for index, item in enumerate(attachments):
        if not isinstance(item, dict):
            continue
        if len(token_pool) <= index:
            token_pool.extend(_get_upload_tokens(entry_id, transaction_id))
        token_info = token_pool[index]
        file_bytes = _download_file_bytes(_text_value(item.get("oss_url", "")))
        file_key = _upload_single_file(
            upload_url=token_info["url"],
            token=token_info["token"],
            filename=_text_value(item.get("filename", f"attachment_{index + 1}")),
            file_bytes=file_bytes
        )
        file_keys.append(file_key)

    return transaction_id, file_keys


def _build_mail_form_data(email_info, appendix_keys=None, extra_fields=None):
    attachments = email_info.get("attachments", []) or []
    attachment_rows = []
    appendix_keys = appendix_keys or []
    extra_fields = extra_fields or {}
    for item in attachments:
        if not isinstance(item, dict):
            continue
        attachment_rows.append({
            "filename": _wrap(_text_value(item.get("filename", ""))),
            "oss_url": _wrap(_text_value(item.get("oss_url", ""))),
            "binary": _wrap(_text_value(item.get("binary", ""))),
            "mail_content_type": _wrap(_text_value(item.get("mail_content_type", ""))),
            "content_id": _wrap(_text_value(item.get("content_id", ""))),
            "content_disposition": _wrap(_text_value(item.get("content_disposition", ""))),
            "charset": _wrap(_text_value(item.get("charset", ""))),
            "content_transfer_encoding": _wrap(_text_value(item.get("content_transfer_encoding", ""))),
        })

    payload = {
        "sender_id": _wrap(_safe_get(email_info, "from_", "from_email", default="")),
        "recipient_id": _wrap(_safe_get(email_info, "to", default="")),
        "cc": _wrap(_safe_get(email_info, "cc", default="")),
        "date": _wrap(_safe_get(email_info, "date", default="")),
        "main_email_id": _wrap(_safe_get(email_info, "main_email_id", default="")),
        "message_id": _wrap(_safe_get(email_info, "message_id", default="")),
        "select_folder": _wrap(_safe_get(email_info, "select_folder", default="")),
        "folder_uidvalidity": _wrap(_safe_get(email_info, "folder_uidvalidity", default="")),
        "eml_url": _wrap(_safe_get(email_info, "eml_url", default="")),
        "subject": _wrap(_safe_get(email_info, "subject", default="")),
        "text_plain": _wrap(_text_value(email_info.get("text_plain", []))),
        "attachments": _wrap(attachment_rows),
        "appendix": _wrap(appendix_keys),
    }
    payload.update(extra_fields)
    return payload


def _build_create_payload(entry_id, data_payload, transaction_id=""):
    payload = {
        "app_id": APP_ID,
        "entry_id": entry_id,
        "is_start_workflow": False,
        "is_start_trigger": False,
        "data": data_payload
    }
    if transaction_id:
        payload["transaction_id"] = transaction_id
    return payload


def _build_update_payload(entry_id, data_id, data_payload, transaction_id=""):
    payload = {
        "app_id": APP_ID,
        "entry_id": entry_id,
        "data_id": data_id,
        "is_start_workflow": False,
        "is_start_trigger": False,
        "data": data_payload
    }
    if transaction_id:
        payload["transaction_id"] = transaction_id
    return payload


def _generate_serial_number(email_info):
    main_email_id = _safe_get(email_info, "main_email_id", default="")
    digits = "".join(ch for ch in str(main_email_id) if ch.isdigit())
    if digits:
        return digits[-5:].zfill(5)
    return datetime.now().strftime("%H%M%S")[-5:]


def _build_order_payload(
    email_info,
    customer_info,
    driver_vehicle_info,
    source_order_info,
    entry_id,
    main_email_field,
    email_center_id="",
    center_main_email_fill_field=""
):
    customer_row = (customer_info or [{}])[0]
    vehicle_row = (driver_vehicle_info or [{}])[0]
    serial_number = _generate_serial_number(email_info)

    data_payload = {
        SERIAL_FIELD_ID: _wrap(serial_number),
        "company_name": _wrap(_safe_get(email_info, "company_name", default="")),
        "job_type": _wrap(_safe_get(email_info, "job_type", default="")),
        "message_id": _wrap(_safe_get(email_info, "message_id", default="")),
        main_email_field: _wrap(_safe_get(email_info, "main_email_id", default="")),
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
            "driver_phone": _wrap(_safe_get(vehicle_row, "driver_phone", default="")),
            "id_number": _wrap(_safe_get(vehicle_row, "id_number", default="")),
            "escort_name": _wrap(_safe_get(vehicle_row, "escort_name", default="")),
            "escort_phone": _wrap(_safe_get(vehicle_row, "escort_phone", default="")),
            "escort_id_number": _wrap(_safe_get(vehicle_row, "escort_id_number", default="")),
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
            "quantity": _wrap(_safe_get(item, "quantity", default="")),
            "status": _wrap(_safe_get(item, "status", default="")),
            "specification": _wrap(_safe_get(item, "specification", default="")),
            "weight": _wrap(_safe_get(item, "weight", default="")),
        } for item in (source_order_info or [])]),
    }

    if email_center_id:
        data_payload["email_center_ref"] = _wrap(email_center_id)
    if center_main_email_fill_field:
        data_payload[center_main_email_fill_field] = _wrap(_safe_get(email_info, "main_email_id", default=""))

    return {
        "app_id": APP_ID,
        "entry_id": entry_id,
        "is_start_workflow": False,
        "is_start_trigger": False,
        "data": data_payload
    }


def _write_email_log(email_info, email_center_id=""):
    transaction_id, appendix_keys = _upload_email_attachments(email_info, EMAIL_LOG_ENTRY_ID)
    extra_fields = {}
    if email_center_id:
        extra_fields["email_center_ref"] = _wrap(email_center_id)
    payload = _build_create_payload(
        EMAIL_LOG_ENTRY_ID,
        _build_mail_form_data(
            email_info,
            appendix_keys=appendix_keys,
            extra_fields=extra_fields
        ),
        transaction_id=transaction_id
    )
    response = _post_json(CREATE_URL, payload)
    return payload, response, transaction_id, appendix_keys


def _find_email_center_record(main_email_id):
    payload = {
        "app_id": APP_ID,
        "entry_id": EMAIL_CENTER_ENTRY_ID,
        "filter": {
            "rel": "and",
            "cond": [
                {
                    "field": "main_email_id",
                    "type": "text",
                    "method": "eq",
                    "value": [main_email_id]
                }
            ]
        },
        "limit": 10
    }
    result = _post_json_requests(LIST_URL, payload)
    rows = result.get("data", []) or []
    if not rows:
        return {}
    return rows[-1]


def _write_email_center(email_info):
    main_email_id = _safe_get(email_info, "main_email_id", default="")
    if not main_email_id:
        return None, None, "", [], "", ""

    transaction_id, appendix_keys = _upload_email_attachments(email_info, EMAIL_CENTER_ENTRY_ID)
    data_payload = _build_mail_form_data(email_info, appendix_keys=appendix_keys)
    existing = _find_email_center_record(main_email_id)
    existing_id = _text_value(existing.get("_id", "")) if isinstance(existing, dict) else ""

    if existing_id:
        payload = _build_update_payload(
            entry_id=EMAIL_CENTER_ENTRY_ID,
            data_id=existing_id,
            data_payload=data_payload,
            transaction_id=transaction_id
        )
        response = _post_json_requests(UPDATE_URL, payload)
        mode = "update"
    else:
        payload = _build_create_payload(
            entry_id=EMAIL_CENTER_ENTRY_ID,
            data_payload=data_payload,
            transaction_id=transaction_id
        )
        response = _post_json(CREATE_URL, payload)
        mode = "create"

    return payload, response, transaction_id, appendix_keys, existing_id, mode


def _write_order_form(email_info, customer_info, driver_vehicle_info, source_order_info, email_center_id=""):
    job_type = _safe_get(email_info, "job_type", default="")
    if job_type not in ("入库", "出库"):
        return None, None, None

    if job_type == "出库":
        entry_id = OUTBOUND_ENTRY_ID
        main_email_field = "main_email_id"
        center_main_email_fill_field = OUTBOUND_CENTER_MAIN_EMAIL_FIELD
    else:
        entry_id = INBOUND_ENTRY_ID
        main_email_field = "rmain_email_id"
        center_main_email_fill_field = INBOUND_CENTER_MAIN_EMAIL_FIELD

    payload = _build_order_payload(
        email_info=email_info,
        customer_info=customer_info,
        driver_vehicle_info=driver_vehicle_info,
        source_order_info=source_order_info,
        entry_id=entry_id,
        main_email_field=main_email_field,
        email_center_id=email_center_id,
        center_main_email_fill_field=center_main_email_fill_field,
    )
    response = _post_json(CREATE_URL, payload)
    return job_type, payload, response


def main(*args, tool_args: dict, **kwargs) -> typing.Any:
    data = _new_data()
    variables = kwargs.get("variables", {}) or {}
    email_info = dict(variables.get("email_info", {}) or {})
    customer_info = variables.get("customer_info", []) or []
    driver_vehicle_info = variables.get("driver_vehicle_info", []) or []
    source_order_info = variables.get("source_order_info", []) or []
    validation_pass = variables.get("validation_pass", None)
    validation_message = variables.get("validation_message", "")
    validation_errors = variables.get("validation_errors", [])
    stock_check_debug = variables.get("stock_check_debug", [])
    matched_owner_strategy = variables.get("matched_owner_strategy", {})

    parsed_company_name = variables.get("company_name", "")
    parsed_job_type = variables.get("job_type", "")
    if parsed_company_name:
        email_info["company_name"] = parsed_company_name
    if parsed_job_type:
        email_info["job_type"] = parsed_job_type

    try:
        center_payload, center_response, center_transaction_id, center_appendix_keys, existing_center_id, center_mode = _write_email_center(email_info)
        if center_payload:
            data["variables"]["email_center_payload"] = center_payload
            data["variables"]["email_center_response"] = center_response
            data["variables"]["email_center_transaction_id"] = center_transaction_id
            data["variables"]["email_center_appendix_keys"] = center_appendix_keys
            data["variables"]["email_center_mode"] = center_mode
            email_center_id = _extract_data_id(center_response, fallback=existing_center_id)
            if not email_center_id:
                raise Exception(f"email center write did not return _id: {json.dumps(center_response, ensure_ascii=False)}")
            data["variables"]["email_center_id"] = email_center_id
        else:
            email_center_id = ""
            center_mode = ""

        log_payload, log_response, transaction_id, appendix_keys = _write_email_log(
            email_info,
            email_center_id=email_center_id
        )
        data["variables"]["email_log_payload"] = log_payload
        data["variables"]["email_log_response"] = log_response
        data["variables"]["email_log_transaction_id"] = transaction_id
        data["variables"]["email_log_appendix_keys"] = appendix_keys
        email_log_id = _extract_created_id(log_response)
        if not email_log_id:
            raise Exception(f"email log write did not return _id: {json.dumps(log_response, ensure_ascii=False)}")
        data["variables"]["email_log_id"] = email_log_id

        if validation_pass is False:
            order_kind, order_payload, order_response = None, None, None
            data["variables"]["order_write_skipped"] = True
            data["variables"]["order_write_skip_reason"] = validation_message
        else:
            order_kind, order_payload, order_response = _write_order_form(
                email_info=email_info,
                customer_info=customer_info,
                driver_vehicle_info=driver_vehicle_info,
                source_order_info=source_order_info,
                email_center_id=email_center_id,
            )
        order_form_id = ""
        if order_payload:
            data["variables"]["order_payload"] = order_payload
            data["variables"]["order_response"] = order_response
            data["variables"]["order_form_type"] = order_kind
            order_form_id = _extract_created_id(order_response)
            if not order_form_id:
                raise Exception(f"order form write did not return _id: {json.dumps(order_response, ensure_ascii=False)}")
            data["variables"]["order_form_id"] = order_form_id

        data["result.success"] = True
        data["result.inference"] = True
        data["result"] = json.dumps(
            {
                "email_log_written": True,
                "email_log_id": email_log_id,
                "appendix_count": len(appendix_keys),
                "email_center_written": bool(email_center_id),
                "email_center_id": email_center_id,
                "email_center_mode": center_mode,
                "validation_pass": validation_pass,
                "validation_message": validation_message,
                "validation_errors": validation_errors,
                "matched_owner_strategy": matched_owner_strategy,
                "stock_check_debug": stock_check_debug,
                "order_form_type": order_kind or "",
                "order_written": bool(order_form_id),
                "order_form_id": order_form_id,
            },
            ensure_ascii=False
        )
        return data
    except Exception as exc:
        data["result.success"] = False
        data["result.inference"] = False
        data["result"] = str(exc)
        return data
