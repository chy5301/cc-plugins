"""跨清单的只读扇出聚合。

CLI 只替 Agent 做只读扇出（幂等、可 $batch 打包、失败可整体重试）；
跨资源的写事务不在此处，也不在 CLI 任何地方——见 spec §3.2。
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx

from . import client

# Graph 单批最多 20 个子请求
BATCH_LIMIT = 20

_AUTH_STATUSES = frozenset({401, 403})


def chunk(seq: list, size: int) -> Iterator[list]:
    for start in range(0, len(seq), size):
        yield seq[start:start + size]


def inject_list_identity(items: list, *, list_id: str, display_name: str) -> list:
    """给每个任务注入所属清单的 id 与名称。

    Graph 的 todoTask 本身没有这两个字段，不冲突。单清单与 --list all
    两种模式都注入：只在聚合时注入会让 `--fields id,title,listId` 在
    单清单模式下静默失效（spec §6.4）。
    """
    return [dict(item, listId=list_id, listDisplayName=display_name)
            if isinstance(item, dict) else item for item in items]


def filter_by_status(items: list, status_csv: str | None) -> list:
    """按 taskStatus 过滤。

    调用方必须在分页完整跟完之后才调用本函数：先取首页再过滤，会在一个
    有大量已完成任务的清单上过滤出 0 条未完成任务而毫无错误提示
    （spec §5.4）。
    """
    if not status_csv:
        return items
    wanted = {s.strip() for s in status_csv.split(",") if s.strip()}
    return [i for i in items if isinstance(i, dict) and i.get("status") in wanted]


def batch_get(paths: dict[str, str], *, http: httpx.Client, token: str) -> dict[str, dict]:
    """把多个 GET 打进 $batch，按关联 id 返回各自结果。

    响应顺序可能与请求不同，必须靠 id 关联（Graph 官方明确这一点）。
    批内被限流的子请求不会自动重试，故逐个记录 Retry-After 交给调用方。
    """
    results: dict[str, dict] = {}
    keys = list(paths)

    for group in chunk(keys, BATCH_LIMIT):
        payload = {"requests": [{"id": key, "method": "GET", "url": paths[key]}
                                for key in group]}
        resp = client.request("POST", "/$batch", http=http, token=token, body=payload)
        envelope = client.handle_response(resp)

        for item in (envelope or {}).get("responses", []):
            raw_retry = (item.get("headers") or {}).get("Retry-After")
            results[item["id"]] = {
                "status": item.get("status", 0),
                "body": item.get("body") or {},
                "retry_after": int(raw_retry) if raw_retry and str(raw_retry).isdigit()
                else None,
            }

    return results


def aggregate_tasks(lists: list, *, http: httpx.Client, token: str,
                    max_pages: int = 0) -> tuple[list, dict]:
    """跨清单聚合任务。

    分两段：先用 $batch 一次往返拿到每个清单的首页，再对首页带 nextLink 的
    清单串行跟随续页（$batch 只能压缩首页请求，续页 URL 是运行时才知道的）。

    返回 (items, meta)，meta 含 aggregated_from / partial_failures /
    retry_after_seconds / all_auth_failed / pages_fetched。
    """
    by_id = {entry["id"]: entry.get("displayName", "") for entry in lists}
    paths = {lid: f"/me/todo/lists/{lid}/tasks" for lid in by_id}
    responses = batch_get(paths, http=http, token=token)

    items: list = []
    failures: list[dict] = []
    pages = 0

    for list_id, display_name in by_id.items():
        result = responses.get(list_id)
        if result is None:
            failures.append({"listId": list_id, "displayName": display_name,
                             "status": 0, "retry_after": None})
            continue

        if result["status"] >= 400:
            failures.append({"listId": list_id, "displayName": display_name,
                             "status": result["status"],
                             "retry_after": result["retry_after"]})
            continue

        body = client.strip_item_odata(result["body"])
        pages += 1
        page_items = list(body.get("value", []))

        # 二维分页：此清单还有后续页时串行跟完
        next_url = body.get("@odata.nextLink")
        list_pages = 1
        while next_url:
            if max_pages and list_pages >= max_pages:
                failures.append({"listId": list_id, "displayName": display_name,
                                 "status": 0, "retry_after": None,
                                 "reason": "truncated"})
                break
            more = client.handle_response(
                client.request("GET", next_url, http=http, token=token))
            pages += 1
            list_pages += 1
            page_items.extend(more.get("value", []))
            next_url = more.get("@odata.nextLink")

        items.extend(inject_list_identity(page_items, list_id=list_id,
                                          display_name=display_name))

    retry_values = [f["retry_after"] for f in failures if f.get("retry_after")]
    # 判定「整批均认证失败」不能用 `not items` 代理——某清单可能成功但恰好
    # 没有任务（200 + 空 value），此时 items 为空但并非认证问题。必须直接比较
    # 失败清单数与清单总数：只有全部清单都失败、且全是 401/403，才是认证问题。
    all_auth_failed = bool(failures) and len(failures) == len(by_id) and all(
        f["status"] in _AUTH_STATUSES for f in failures)

    return items, {
        "aggregated_from": len(by_id),
        "pages_fetched": pages,
        "partial_failures": failures,
        "retry_after_seconds": max(retry_values) if retry_values else None,
        "all_auth_failed": all_auth_failed,
    }
