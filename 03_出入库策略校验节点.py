import json
import re
import typing

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
LIST_URL = "https://api.jiandaoyun.com/api/v5/app/entry/data/list"
OWNER_STRATEGY_ENTRY_ID = "6a56f26c8dbe6eea0b5033fb"
STOCK_CHECK_URL = "http://117.131.7.5:31080/webroot/service/publish/5b2ac7c4-1b65-4979-98a0-cf18f5bd446b/StockCheck"


FIELD_LABELS = {
    "货主": "shipper_name",
    "作业类型": "source_job_type",
    "作业日期": "job_date",
    "作业时间": "job_time",
    "作业编号": "job_code",
    "订单号": "order_number",
    "物料号": "material_code",
    "物料代码": "material_code",
    "品名": "product_name",
    "批号": "batch_number",
    "单位": "unit",
    "数量": "quantity",
    "状态": "status",
    "规格": "specification",
    "重量": "weight",
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
    if isinstance(value, dict) and "value" in value:
        return _text(value.get("value"))
    if isinstance(value, list):
        return "\n".join([_text(item) for item in value if _text(item)]).strip()
    return str(value).strip()


def _unwrap(value):
    if isinstance(value, dict) and "value" in value:
        return _unwrap(value.get("value"))
    if isinstance(value, list):
        return [_unwrap(item) for item in value]
    if isinstance(value, dict):
        return {key: _unwrap(item) for key, item in value.items()}
    return value


def _safe_get(source, *keys, default=""):
    if not isinstance(source, dict):
        return default
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return _text(value)
    return default


def _split_items(text):
    raw = _text(text)
    if not raw:
        return []
    return [item.strip() for item in re.split(r"[,，;；、\n\r]+", raw) if item.strip()]


def _post_json(url, payload, timeout=60):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if response.status_code != 200:
        raise Exception(f"request failed {response.status_code}: {response.text}")
    return response.json()


def _list_jdy_rows(entry_id, limit=100):
    payload = {
        "app_id": APP_ID,
        "entry_id": entry_id,
        "limit": limit
    }
    result = _post_json(LIST_URL, payload)
    rows = result.get("data", []) or []
    return [_unwrap(row) for row in rows if isinstance(row, dict)]


def _extract_email(value):
    text = _text(value)
    match = re.search(r"[\w.\-+%]+@[\w.\-]+\.[A-Za-z]{2,}", text)
    return match.group(0).lower() if match else text.lower()


def _select_owner_config(config_rows, email_info, orders):
    sender_email = _extract_email(_safe_get(email_info, "from_email", "from_", default=""))
    first_order = orders[0] if orders else {}
    shipper_name = _safe_get(first_order, "shipper_name", default="")

    best_row = {}
    best_score = -1
    for row in config_rows:
        cargo_owner_name = _safe_get(row, "cargo_owner_name", default="")
        linked_email = _extract_email(_safe_get(row, "linked_email", default=""))
        score = 0
        if sender_email and linked_email and sender_email == linked_email:
            score += 3
        if shipper_name and cargo_owner_name:
            if shipper_name == cargo_owner_name:
                score += 4
            elif shipper_name in cargo_owner_name or cargo_owner_name in shipper_name:
                score += 2
        if score > best_score:
            best_row = row
            best_score = score

    return best_row if best_score > 0 else {}


def _strategy_names(config_row, job_type):
    if job_type == "入库":
        rows = config_row.get("inbound_strategy", []) or []
        name_key = "inbound_strategy_name"
    else:
        rows = config_row.get("outbound_strategy", []) or []
        name_key = "outbound_strategy_name"

    names = []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                name = _safe_get(row, name_key, default="")
                if name:
                    names.append(name)
    return names


def _check_required_fields(config_row, orders):
    errors = []
    required_labels = _split_items(_safe_get(config_row, "required_field", default=""))
    for row_index, order in enumerate(orders, start=1):
        for label in required_labels:
            field_name = FIELD_LABELS.get(label)
            if not field_name:
                continue
            if not _safe_get(order, field_name, default=""):
                errors.append(f"第{row_index}行缺少必填字段：{label}")
    return errors


def _extract_stock_rows(response_json):
    candidates = []
    if isinstance(response_json, dict):
        candidates.extend([
            response_json.get("data"),
            response_json.get("rows"),
            response_json.get("list"),
            response_json.get("result"),
        ])
    elif isinstance(response_json, list):
        candidates.append(response_json)

    for item in candidates:
        if isinstance(item, list):
            return [row for row in item if isinstance(row, dict)]
        if isinstance(item, dict):
            for key in ("data", "rows", "list", "records", "items"):
                nested = item.get(key)
                if isinstance(nested, list):
                    return [row for row in nested if isinstance(row, dict)]
    return []


def _query_stock(unit, department_code, sku="", lotatt04=""):
    payload = {
        "unit": unit or "普工路仓库",
        "pageSize": 200,
        "pageNum": 1,
        "customerid": department_code,
        "sku": sku,
        "lotatt04": lotatt04
    }
    response = requests.post(
        STOCK_CHECK_URL,
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=60
    )
    if response.status_code != 200:
        raise Exception(f"库存接口查询失败：{response.status_code} {response.text}")
    try:
        response_json = response.json()
    except Exception as exc:
        raise Exception(f"库存接口返回非JSON：{response.text[:200]}") from exc
    return _extract_stock_rows(response_json)


def _name_contains(left, right):
    left_text = _text(left).lower()
    right_text = _text(right).lower()
    return bool(left_text and right_text and (left_text in right_text or right_text in left_text))


def _spec_equal(left, right):
    return _text(left).replace(" ", "").lower() == _text(right).replace(" ", "").lower()


def _check_material_exact(order, stock_rows):
    material_code = _safe_get(order, "material_code", default="")
    return any(_safe_get(row, "sku", default="") == material_code for row in stock_rows)


def _check_name_contains_spec_exact(order, stock_rows):
    product_name = _safe_get(order, "product_name", default="")
    specification = _safe_get(order, "specification", default="")
    for row in stock_rows:
        depot_name = _safe_get(row, "skuname", "skunamecn", default="")
        depot_spec = _safe_get(row, "skuspec", default="")
        if _name_contains(product_name, depot_name) and _spec_equal(specification, depot_spec):
            return True
    return False


def _check_strategy(config_row, job_type, orders):
    errors = []
    strategy_names = _strategy_names(config_row, job_type)
    if not strategy_names:
        errors.append(f"未配置{job_type}策略")
        return errors, []

    unit = _safe_get(config_row, "associated_warehouse", default="普工路仓库")
    department_code = _safe_get(config_row, "department_code", default="")
    if not department_code:
        errors.append("策略配置缺少部门代码，无法查询仓库库存数据")
        return errors, strategy_names

    cache = {}
    for row_index, order in enumerate(orders, start=1):
        row_passed = False
        row_reasons = []
        material_code = _safe_get(order, "material_code", default="")

        for strategy_name in strategy_names:
            try:
                if "物料号完全匹配" in strategy_name:
                    cache_key = ("sku", material_code)
                    if cache_key not in cache:
                        cache[cache_key] = _query_stock(unit, department_code, sku=material_code)
                    if _check_material_exact(order, cache[cache_key]):
                        row_passed = True
                        break
                    row_reasons.append("物料号未在仓库数据中完全匹配")
                elif "品名" in strategy_name and "规格" in strategy_name:
                    cache_key = ("owner", department_code)
                    if cache_key not in cache:
                        cache[cache_key] = _query_stock(unit, department_code)
                    if _check_name_contains_spec_exact(order, cache[cache_key]):
                        row_passed = True
                        break
                    row_reasons.append("品名包含关系或规格完全匹配不成立")
                else:
                    row_reasons.append(f"暂不支持的策略：{strategy_name}")
            except Exception as exc:
                row_reasons.append(str(exc))

        if not row_passed:
            order_no = _safe_get(order, "order_number", default="-")
            material = _safe_get(order, "material_code", default="-")
            errors.append(f"第{row_index}行校验失败，订单号{order_no}，物料号{material}：{'；'.join(row_reasons)}")

    return errors, strategy_names


def main(*args, tool_args: dict, **kwargs) -> typing.Any:
    data = _new_data()
    variables = kwargs.get("variables", {}) or {}
    email_info = variables.get("email_info", {}) or {}
    orders = variables.get("source_order_info", []) or []
    job_type = _safe_get({"job_type": variables.get("job_type")}, "job_type", default="") or _safe_get(email_info, "job_type", default="")

    errors = []
    config_row = {}
    strategy_names = []

    try:
        if not orders:
            errors.append("未解析到附件中的订单明细")
        if job_type not in ("入库", "出库"):
            errors.append("未识别到作业类型，无法判断入库/出库策略")

        config_rows = _list_jdy_rows(OWNER_STRATEGY_ENTRY_ID)
        config_row = _select_owner_config(config_rows, email_info, orders)
        if not config_row:
            first_shipper = _safe_get(orders[0], "shipper_name", default="") if orders else ""
            sender = _safe_get(email_info, "from_", "from_email", default="")
            errors.append(f"未在货主-出入库策略表配置中匹配到货主配置，货主：{first_shipper or '-'}，发件人：{sender or '-'}")

        if not errors and config_row:
            errors.extend(_check_required_fields(config_row, orders))
            strategy_errors, strategy_names = _check_strategy(config_row, job_type, orders)
            errors.extend(strategy_errors)

        validation_pass = not errors
        message = "策略校验通过，可以写入出入库单" if validation_pass else "策略校验未通过，已阻止写入出入库单：" + "；".join(errors)

        data["variables"]["validation_pass"] = validation_pass
        data["variables"]["validation_message"] = message
        data["variables"]["validation_errors"] = errors
        data["variables"]["matched_owner_strategy"] = {
            "cargo_owner_name": _safe_get(config_row, "cargo_owner_name", default=""),
            "department_code": _safe_get(config_row, "department_code", default=""),
            "associated_warehouse": _safe_get(config_row, "associated_warehouse", default=""),
            "required_field": _safe_get(config_row, "required_field", default=""),
            "strategy_names": strategy_names,
        }
        data["result.success"] = True
        data["result.inference"] = True
        data["result"] = json.dumps(
            {
                "validation_pass": validation_pass,
                "validation_message": message,
                "strategy_names": strategy_names,
            },
            ensure_ascii=False
        )
        return data
    except Exception as exc:
        message = f"策略校验节点异常，已阻止写入出入库单：{exc}"
        data["variables"]["validation_pass"] = False
        data["variables"]["validation_message"] = message
        data["variables"]["validation_errors"] = [str(exc)]
        data["result.success"] = True
        data["result.inference"] = True
        data["result"] = json.dumps(
            {
                "validation_pass": False,
                "validation_message": message,
            },
            ensure_ascii=False
        )
        return data
