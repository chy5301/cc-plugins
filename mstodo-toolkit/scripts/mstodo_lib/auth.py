"""OAuth2 设备码流、token 缓存与自动刷新。

缓存落在 ~/ 下的独立目录，绝不进仓库；每台设备各自登录一次。
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import time
from typing import Any

import httpx

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


class DeviceCodeError(Exception):
    """设备码流的终态失败：用户拒绝，或 device_code 已过期。"""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


def auth_base() -> str:
    """Microsoft 认证服务的基础 URL。"""
    return f"https://login.microsoftonline.com/{tenant()}/oauth2/v2.0"


@contextlib.contextmanager
def _client_session(http: httpx.Client | None = None):
    """获取客户端会话。若调用方未传入，则创建一个临时的并在退出时关闭。"""
    owned = http is None
    client = http or httpx.Client(timeout=30)
    try:
        yield client
    finally:
        if owned:
            client.close()


def device_code_start(*, http: httpx.Client | None = None) -> dict:
    """发起设备码流，立即返回 user_code 等信息，不阻塞。"""
    with _client_session(http) as client:
        resp = client.post(f"{auth_base()}/devicecode",
                           data={"client_id": client_id(), "scope": SCOPE})
        payload = resp.json()
        if resp.status_code != 200:
            raise DeviceCodeError("other", json.dumps(payload, ensure_ascii=False))
        return payload


def device_code_poll(device_code: str, *, interval: int, timeout_s: float,
                     http: httpx.Client | None = None,
                     now=time.time, sleep=time.sleep) -> dict | None:
    """轮询授权结果。

    返回 token 响应表示成功；返回 None 表示到达 timeout_s 时用户仍未完成授权
    （调用方应以 AUTH_PENDING 提示用户用同一个 device_code 重试）；
    用户拒绝或 device_code 过期则抛 DeviceCodeError。

    必须遵循服务端下发的 interval；收到 slow_down 时 interval += 5（RFC 8628）。
    绝不允许 sleep 超过 deadline；slow_down 导致 wait 膨胀时仍在 deadline 处返回。
    """
    with _client_session(http) as client:
        deadline = now() + timeout_s
        wait = interval
        while now() < deadline:
            # 计算剩余时间，sleep 不超过它
            remaining = deadline - now()
            sleep(min(wait, remaining))

            # 醒来后重新检查 deadline
            if now() >= deadline:
                return None

            resp = client.post(f"{auth_base()}/token", data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": client_id(),
                "device_code": device_code,
            })
            payload = resp.json()
            if resp.status_code == 200:
                return payload
            err = payload.get("error", "")
            if err == "authorization_pending":
                continue
            if err == "slow_down":
                wait += 5
                continue
            if err == "authorization_declined":
                raise DeviceCodeError("declined", payload.get(
                    "error_description", "用户拒绝了授权请求"))
            if err == "expired_token":
                raise DeviceCodeError("expired", payload.get(
                    "error_description", "device_code 已过期，请重新发起登录"))
            raise DeviceCodeError("other", json.dumps(payload, ensure_ascii=False))
        return None


class NotLoggedInError(Exception):
    """本机从未登录过。调用方映射为退出码 2 + CONFIG_ERROR。"""


class AuthExpiredError(Exception):
    """登录过但 refresh 失败（撤销 / 超 90 天 / 改密码）。

    调用方映射为退出码 4 + AUTH_EXPIRED。注意：token 端点返回的是
    HTTP 400 + invalid_grant，不是 401——不得写成 HTTP_401，否则会与
    "真的调 Graph 拿到 401" 在信封上不可区分。
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def refresh(refresh_token: str, *, http: httpx.Client | None = None) -> dict:
    """用 refresh_token 换新的 access_token。失败抛 AuthExpiredError。"""
    with _client_session(http) as client:
        resp = client.post(f"{auth_base()}/token", data={
            "grant_type": "refresh_token",
            "client_id": client_id(),
            "scope": SCOPE,
            "refresh_token": refresh_token,
        })
        payload = resp.json()
        if resp.status_code != 200:
            raise AuthExpiredError(payload.get(
                "error_description", json.dumps(payload, ensure_ascii=False)))
        return payload


def get_access_token(*, http: httpx.Client | None = None, now=time.time) -> str:
    """取可用的 access_token；剩余有效期不足阈值时先刷新并写回缓存。

    对调用方完全透明。
    """
    cached = read_cache()
    if cached is None:
        raise NotLoggedInError("本机尚未登录 Microsoft To Do")

    if float(cached.get("expires_at", 0)) - now() > REFRESH_SKEW_SECONDS:
        return cached["access_token"]

    old_refresh = cached.get("refresh_token") or ""
    if not old_refresh:
        raise AuthExpiredError("缓存中没有 refresh_token，需重新登录")

    fresh = refresh(old_refresh, http=http)
    # 响应未回带 refresh_token 时沿用旧的
    fresh.setdefault("refresh_token", old_refresh)
    fresh.setdefault("scope", cached.get("scope", ""))
    write_cache(fresh, now=now())
    return fresh["access_token"]
