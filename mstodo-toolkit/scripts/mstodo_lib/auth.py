"""OAuth2 设备码流、token 缓存与自动刷新。

缓存落在 ~/ 下的独立目录，绝不进仓库；每台设备各自登录一次。
"""

from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Any

# 微软第一方公共 client（Graph Command Line Tools），免 Azure 注册
DEFAULT_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
DEFAULT_TENANT = "common"
SCOPE = "Tasks.ReadWrite offline_access"

# 剩余有效期低于该秒数即提前刷新
REFRESH_SKEW_SECONDS = 300


def client_id() -> str:
    return os.environ.get("MSTODO_CLIENT_ID") or DEFAULT_CLIENT_ID


def tenant() -> str:
    return os.environ.get("MSTODO_TENANT") or DEFAULT_TENANT


def cache_path() -> pathlib.Path:
    override = os.environ.get("MSTODO_TOKEN_CACHE")
    if override:
        return pathlib.Path(override).expanduser() / "token.json"
    state = os.environ.get("XDG_STATE_HOME")
    base = pathlib.Path(state).expanduser() if state else pathlib.Path.home() / ".local" / "state"
    return base / "mstodo-toolkit" / "token.json"


def write_cache(token_response: dict, *, now: float | None = None) -> None:
    """原子写入缓存。目录 0700、文件 0600。

    并发安全性：官方明确 refresh token 每次使用都自我替换，且旧 token 不被
    吊销，故两个会话同时刷新不会互相踢下线；最坏是旧 token 覆盖新 token，
    属良性，下次调用自动再刷。
    """
    stamp = time.time() if now is None else now
    payload: dict[str, Any] = {
        "access_token": token_response["access_token"],
        "refresh_token": token_response.get("refresh_token", ""),
        "expires_at": stamp + float(token_response.get("expires_in", 3600)),
        "scope": token_response.get("scope", ""),
        "client_id": client_id(),
        "tenant": tenant(),
    }
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def read_cache() -> dict | None:
    """读取缓存。缺失、损坏，或 client_id/tenant 已变更时返回 None。"""
    path = cache_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("client_id") != client_id() or payload.get("tenant") != tenant():
        return None
    return payload


def clear_cache() -> bool:
    """删除缓存。返回是否确实删掉了东西。"""
    try:
        cache_path().unlink()
        return True
    except FileNotFoundError:
        return False
