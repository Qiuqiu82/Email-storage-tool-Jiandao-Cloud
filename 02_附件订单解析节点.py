import json
import typing
import re
from io import BytesIO

import pandas as pd
import requests


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


def _normalize_text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join([str(v) for v in value if v not in (None, "")]).strip()
    return str(value).strip()


def _download_xlsx(oss_url):
    response = requests.get(oss_url, timeout=60)
    if response.status_code != 200:
        raise Exception(f"download file failed: {response.status_code}")
    return BytesIO(response.content)


def _cell_text(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if hasattr(v, "isoformat"):
        try:
            return v.strftime("%Y-%m-%d")
        except Exception:
            return str(v)
    return str(v).strip()


def _find_row_by_keywords(rows, keywords):
    for idx, row in enumerate(rows):
        row_text = " ".join([_cell_text(v) for v in row if _cell_text(v)])
        if all(keyword in row_text for keyword in keywords):
            return idx
    return None


def _extract_value_after_label(rows, label_keywords, row_offset=0, col_offset=1):
    for r_idx, row in enumerate(rows):
        for c_idx, cell in enumerate(row):
            cell_text = _cell_text(cell)
            if all(keyword in cell_text for keyword in label_keywords):
                rr = r_idx + row_offset
                cc = c_idx + col_offset
                if 0 <= rr < len(rows) and 0 <= cc < len(rows[rr]):
                    return _cell_text(rows[rr][cc])
    return ""


def _parse_email_body_fields(mail_body):
    text = _normalize_text(mail_body)
    result = {}
    patterns = {
        "vehicle_number": r"(?:车牌|车辆号码)\s*[:：]?\s*([A-Z\u4e00-\u9fa50-9\-]+)",
        "driver_name": r"司机姓名\s*[:：]?\s*([^\s\r\n]+)",
        "driver_phone": r"联系电话\s*[:：]?\s*([0-9\-]{7,20})",
        "id_number": r"身份证号\s*[:：]?\s*([0-9Xx]{15,18})",
        "escort_name": r"押运员姓名\s*[:：]?\s*([^\s\r\n]+)",
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, text)
        if m:
            result[key] = m.group(1).strip()
    return result


def _find_table_start(rows):
    keywords = ["货主", "作业类型", "作业日期", "订单号", "物料号", "品名"]
    for idx, row in enumerate(rows):
        row_text = " ".join([_cell_text(v) for v in row if _cell_text(v)])
        hit = sum(1 for keyword in keywords if keyword in row_text)
        if hit >= 4:
            return idx
    return None


def _parse_orders(rows, start_row):
    header_row = rows[start_row]
    headers = [_cell_text(v) for v in header_row]

    def col_idx(*names):
        for name in names:
            for i, h in enumerate(headers):
                if name in h:
                    return i
        return None

    mapping = {
        "shipper_name": col_idx("货主"),
        "source_job_type": col_idx("作业类型"),
        "job_date": col_idx("作业日期"),
        "job_time": col_idx("作业时间"),
        "job_code": col_idx("作业编号"),
        "order_number": col_idx("订单号"),
        "material_code": col_idx("物料号"),
        "product_name": col_idx("品名"),
        "batch_number": col_idx("批号"),
        "unit": col_idx("单位"),
        "specification": col_idx("规格"),
        "status": col_idx("状态"),
        "quantity": col_idx("数量"),
        "weight": col_idx("重量"),
    }

    orders = []
    for row in rows[start_row + 1:]:
        if not any(_cell_text(v) for v in row):
            if orders:
                break
            continue
        first_value = _cell_text(row[0]) if row else ""
        if first_value and first_value in ("制单：", "作用1：", "备注", "客户信息"):
            break

        order = {}
        for key, idx in mapping.items():
            if idx is not None and idx < len(row):
                order[key] = _cell_text(row[idx])
            else:
                order[key] = ""
        if any(order.values()):
            if not order.get("job_date") and start_row + 1 < len(rows):
                order["job_date"] = order.get("job_date", "")
            orders.append(order)
    return orders


def _build_customer_info(email_info, rows):
    info = {
        "customer_company_name": _extract_value_after_label(rows, ["公司名称"]),
        "customer_contact_name": _extract_value_after_label(rows, ["联系人"]),
        "customer_phone": _extract_value_after_label(rows, ["联系电话"]),
        "customer_email": _extract_value_after_label(rows, ["E-mail"]),
        "customer_address": _extract_value_after_label(rows, ["公司地址"]),
    }
    if not info["customer_company_name"]:
        info["customer_company_name"] = _safe_get(email_info, "company_name", default="")
    return info


def _build_driver_vehicle_info(email_info, rows, body_fields):
    info = {
        "vehicle_number": _extract_value_after_label(rows, ["车牌号码"]) or body_fields.get("vehicle_number", ""),
        "trailer_number": _extract_value_after_label(rows, ["挂车号码"]),
        "driver_name": _extract_value_after_label(rows, ["司机姓名"]) or body_fields.get("driver_name", ""),
        "id_number": _extract_value_after_label(rows, ["身份证号"]) or body_fields.get("id_number", ""),
        "driver_phone": _extract_value_after_label(rows, ["联系电话"]) or body_fields.get("driver_phone", ""),
        "escort_name": _extract_value_after_label(rows, ["押运员姓名"]) or body_fields.get("escort_name", ""),
    }
    return info


def _normalize_row_values(row):
    return [None if v is None else v for v in row]


def _extract_sheet_rows(xlsx_bytes):
    wb = pd.ExcelFile(xlsx_bytes, engine="openpyxl")
    df = pd.read_excel(wb, sheet_name=0, header=None, dtype=object, engine="openpyxl")
    rows = df.where(pd.notnull(df), None).values.tolist()
    return rows


def main(*args, tool_args: dict, **kwargs) -> typing.Any:
    """Run Tool"""

    data = _new_data()
    email_info = kwargs.get("variables", {}).get("email_info", {}) or {}
    attachments = email_info.get("attachments", []) or []
    if not attachments:
        data["result.success"] = True
        data["result.inference"] = True
        data["result"] = "no attachments"
        data["variables"]["source_order_info"] = []
        data["variables"]["customer_info"] = []
        data["variables"]["driver_vehicle_info"] = []
        return data

    first_attachment = None
    for item in attachments:
        if isinstance(item, dict) and str(item.get("filename", "")).lower().endswith(".xlsx"):
            first_attachment = item
            break

    if not first_attachment:
        raise ValueError("no xlsx attachment found")

    oss_url = first_attachment.get("oss_url", "")
    if not oss_url:
        raise ValueError("missing oss_url in attachment")

    xlsx_bytes = _download_xlsx(oss_url)
    rows = _extract_sheet_rows(xlsx_bytes)
    table_start = _find_table_start(rows)
    if table_start is None:
        raise ValueError("cannot find order table header")

    body_fields = _parse_email_body_fields(email_info.get("mail_body", ""))
    orders = _parse_orders(rows, table_start)
    customer_info = _build_customer_info(email_info, rows)
    driver_vehicle_info = _build_driver_vehicle_info(email_info, rows, body_fields)

    company_name = customer_info.get("customer_company_name") or _safe_get(email_info, "company_name", default="")
    job_type = _safe_get(email_info, "job_type", default="")
    if not job_type and orders:
        job_type = _safe_get(orders[0], "source_job_type", default="")
    if not job_type:
        body_text = _normalize_text(email_info.get("subject", "")) + " " + _normalize_text(email_info.get("mail_body", ""))
        job_type = "入库" if "入库" in body_text else ("出库" if "出库" in body_text else "")

    source_order_info = []
    for order in orders:
        source_order_info.append({
            "shipper_name": order.get("shipper_name", ""),
            "source_job_type": order.get("source_job_type", ""),
            "job_date": order.get("job_date", ""),
            "job_time": order.get("job_time", ""),
            "job_code": order.get("job_code", ""),
            "order_number": order.get("order_number", ""),
            "material_code": order.get("material_code", ""),
            "product_name": order.get("product_name", ""),
            "batch_number": order.get("batch_number", ""),
            "unit": order.get("unit", ""),
            "specification": order.get("specification", ""),
            "status": order.get("status", ""),
            "quantity": order.get("quantity", ""),
            "weight": order.get("weight", ""),
        })

    data["variables"]["source_order_info"] = source_order_info
    data["variables"]["customer_info"] = [customer_info]
    data["variables"]["driver_vehicle_info"] = [driver_vehicle_info]
    data["variables"]["company_name"] = company_name
    data["variables"]["job_type"] = job_type
    data["variables"]["attachment_filename"] = first_attachment.get("filename", "")
    data["variables"]["attachment_oss_url"] = oss_url
    data["result.success"] = True
    data["result.inference"] = True
    data["result"] = "xlsx parsed"
    return data
