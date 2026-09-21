"""Graph HTTP 客户端：请求、退出码映射、OData 处理、分页。"""

from __future__ import annotations

import json
from typing import Any

import httpx

from . import envelope as env

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# 逐对象剥离：对 Agent 无用，纯占上下文
ITEM_ODATA_STRIP = ("@odata.etag", "@odata.context", "@odata.type")

# 集合级控制字段：必须保留。nextLink 是分页的唯一信号，
# 按 "@odata." 前缀一刀切会把它删掉，导致分页静默失效（spec §6.6）。
COLLECTION_ODATA_KEEP = frozenset({"@odata.nextLink", "@odata.deltaLink", "@odata.count"})

_STATUS_TO_EXIT = {
    401: env.EXIT_PERMISSION,
    403: env.EXIT_PERMISSION,
    404: env.EXIT_NOT_FOUND,
}


class GraphError(Exception):
    """Graph 返回了非 2xx。"""

    def __init__(self, status: int, code: str, message: str,
                 retry_after: int | None = None) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.retry_after = retry_after


def status_to_exit(status: int) -> int:
    return _STATUS_TO_EXIT.get(status, env.EXIT_ERROR)


def strip_item_odata(obj: Any) -> Any:
    """剥离逐对象的 OData 噪音，保留集合级控制字段。

    这是无损降噪，不是 --fields 那种裁剪，故无需用户指定。
    raw 子命令不调用本函数（逃生舱须原样返回）。
    """
    if isinstance(obj, list):
        return [strip_item_odata(item) for item in obj]
    if not isinstance(obj, dict):
        return obj
    result = {}
    for key, value in obj.items():
        if key in COLLECTION_ODATA_KEEP:
            result[key] = value
        elif key in ITEM_ODATA_STRIP:
            continue
        else:
            result[key] = strip_item_odata(value)
    return result


def make_client(*, http: httpx.Client | None = None) -> httpx.Client:
    return http or httpx.Client(base_url=GRAPH_BASE, timeout=60)


def request(method: str, path: str, *, http: httpx.Client, token: str,
            body: Any = None, params: dict | None = None) -> httpx.Response:
    """向 Graph 发一次请求。path 以 / 开头，相对 GRAPH_BASE。"""
    url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
    return http.request(method, url,
                        headers={"Authorization": f"Bearer {token}"},
                        json=body, params=params)


def handle_response(resp: httpx.Response) -> Any:
    """2xx 返回剥噪后的 JSON（204 返回 None），否则抛 GraphError。"""
    if (resp.status_code == 204 or not resp.content) and resp.status_code < 400:
        return None
    if resp.status_code < 400:
        return strip_item_odata(resp.json())

    retry_after = None
    raw_retry = resp.headers.get("Retry-After")
    if raw_retry and raw_retry.isdigit():
        retry_after = int(raw_retry)

    try:
        payload = resp.json()
        err = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(err, dict):
            err = {}
        code = err.get("code") or f"HTTP_{resp.status_code}"
        message = err.get("message") or json.dumps(payload, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError):
        code = f"HTTP_{resp.status_code}"
        message = resp.text[:500]

    raise GraphError(resp.status_code, code, message, retry_after)
