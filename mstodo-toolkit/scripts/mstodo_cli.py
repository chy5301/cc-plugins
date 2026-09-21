# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx"]
# ///
"""Microsoft To Do CLI（基于 Microsoft Graph v1.0 的 To Do API）。

认证走 OAuth2 设备码流，token 缓存在本机 ~/ 下的独立目录。

环境变量:
    MSTODO_CLIENT_ID:    Azure 应用 client ID（默认用微软第一方公共 client）
    MSTODO_TENANT:       common / consumers / organizations（默认 common）
    MSTODO_TOKEN_CACHE:  token 缓存目录（默认 XDG state 目录）
    MSTODO_TIMEZONE:     日期字段默认时区（默认 Asia/Shanghai）
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable

from mstodo_lib import auth
from mstodo_lib import envelope as env

AUTH_COMPLETE_DEFAULT_TIMEOUT = 90


class JsonArgumentParser(argparse.ArgumentParser):
    """用法错误也输出 JSON 信封，而不是裸文本。

    Agent 统一按信封解析输出，裸文本会让它的解析直接崩溃。
    """

    def error(self, message: str):  # type: ignore[override]
        env.fail("INVALID_PARAMETER", message,
                 suggestion="用 --help 查看该子命令的用法",
                 exit_code=env.EXIT_USAGE)


def add_global_options(parser: argparse.ArgumentParser) -> None:
    """挂 --fields / --dry-run / --max-pages 全局选项。"""
    parser.add_argument("--fields", default=None,
                        help="顶层字段掩码，逗号分隔。返回大对象时优先使用")
    parser.add_argument("--dry-run", action="store_true",
                        help="只输出将要发起的 API 调用，不真正执行（退出码 10）")
    parser.add_argument("--max-pages", type=int, default=0,
                        help="集合端点最多跟随几页，0 表示不限。触发上限会标 truncated")


def resolve_token() -> str:
    """取 access_token，把认证异常映射为对应的信封与退出码。

    未登录 → 退出码 2 + CONFIG_ERROR（走完整引导）
    refresh 失败 → 退出码 4 + AUTH_EXPIRED（只需重登）
    """
    try:
        return auth.get_access_token()
    except auth.NotLoggedInError:
        env.fail("CONFIG_ERROR", "本机尚未登录 Microsoft To Do",
                 suggestion="运行 auth-start 开始登录，再用 auth-complete 完成",
                 exit_code=env.EXIT_USAGE)
    except auth.AuthExpiredError as exc:
        env.fail("AUTH_EXPIRED", f"登录凭据已失效：{exc.detail}",
                 suggestion="重新运行 auth-start 登录（凭据过期不是配置问题）",
                 exit_code=env.EXIT_PERMISSION)


# --------------------------------------------------------------------------
# 认证子命令
# --------------------------------------------------------------------------

def cmd_auth_start(args: argparse.Namespace) -> None:
    """发起设备码登录，立即返回用户码。"""
    try:
        payload = auth.device_code_start()
    except auth.DeviceCodeError as exc:
        env.fail("AUTH_START_FAILED", f"发起设备码流失败：{exc.detail}",
                 suggestion="检查网络与代理，或确认 MSTODO_TENANT 取值合法")
    env.output({
        "user_code": payload["user_code"],
        "verification_uri": payload.get("verification_uri", "https://microsoft.com/link"),
        "device_code": payload["device_code"],
        "expires_in": payload.get("expires_in", 900),
        "interval": payload.get("interval", 5),
    }, command="auth-start", fields=args.fields)


def cmd_auth_complete(args: argparse.Namespace) -> None:
    """轮询等待授权完成并落盘 token。"""
    started = time.time()
    try:
        token = auth.device_code_poll(
            args.device_code,
            interval=args.interval,
            timeout_s=args.timeout,
        )
    except auth.DeviceCodeError as exc:
        if exc.kind == "declined":
            env.fail("AUTH_DECLINED", f"用户拒绝了授权：{exc.detail}",
                     suggestion="重新运行 auth-start 并在浏览器中同意授权")
        if exc.kind == "expired":
            env.fail("AUTH_CODE_EXPIRED", f"设备码已过期：{exc.detail}",
                     suggestion="重新运行 auth-start 获取新的设备码")
        env.fail("AUTH_FAILED", exc.detail, suggestion="重新运行 auth-start")

    if token is None:
        env.fail("AUTH_PENDING",
                 f"等待 {args.timeout} 秒后用户仍未完成授权",
                 suggestion=f"用同一个 device_code 再跑一次："
                            f"auth-complete --device-code {args.device_code}",
                 exit_code=env.EXIT_AUTH_PENDING)

    auth.write_cache(token)
    cached = auth.read_cache() or {}
    env.output({
        "logged_in": True,
        "tenant": auth.tenant(),
        "scope": cached.get("scope", ""),
        "expires_in_seconds": int(cached.get("expires_at", 0) - time.time()),
    }, command="auth-complete", took_ms=int((time.time() - started) * 1000),
        fields=args.fields)


def cmd_auth_status(args: argparse.Namespace) -> None:
    """查看本机登录状态。"""
    cached = auth.read_cache()
    if cached is None:
        env.fail("CONFIG_ERROR", "本机尚未登录 Microsoft To Do",
                 suggestion="运行 auth-start 开始登录，再用 auth-complete 完成",
                 exit_code=env.EXIT_USAGE)
    env.output({
        "logged_in": True,
        "tenant": auth.tenant(),
        "scope": cached.get("scope", ""),
        "expires_in_seconds": int(cached.get("expires_at", 0) - time.time()),
        "cache_path": str(auth.cache_path()),
    }, command="auth-status", fields=args.fields)


def cmd_auth_logout(args: argparse.Namespace) -> None:
    """删除本机 token 缓存。"""
    env.output({"removed": auth.clear_cache(), "cache_path": str(auth.cache_path())},
               command="auth-logout", fields=args.fields)


# 认证四条命令，后续可被 Task 9/11 通过 .update() 追加
COMMAND_MAP: dict[str, Callable[[argparse.Namespace], None]] = {
    "auth-start": cmd_auth_start,
    "auth-complete": cmd_auth_complete,
    "auth-status": cmd_auth_status,
    "auth-logout": cmd_auth_logout,
}


def build_parser() -> JsonArgumentParser:
    """组装 argparse 树。"""
    parser = JsonArgumentParser(prog="mstodo_cli",
                                description="Microsoft To Do CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("auth-start", help="发起设备码登录，立即返回用户码")
    add_global_options(p)

    p = sub.add_parser("auth-complete", help="轮询等待授权完成并落盘 token")
    p.add_argument("--device-code", required=True, help="auth-start 返回的 device_code")
    p.add_argument("--timeout", type=int, default=AUTH_COMPLETE_DEFAULT_TIMEOUT,
                   help="最多等待多少秒（默认 90，刻意小于调用方的 120 秒超时）")
    p.add_argument("--interval", type=int, default=5, help="轮询间隔秒数")
    add_global_options(p)

    p = sub.add_parser("auth-status", help="查看本机登录状态")
    add_global_options(p)

    p = sub.add_parser("auth-logout", help="删除本机 token 缓存")
    add_global_options(p)

    return parser


def main(argv: list[str] | None = None) -> None:
    """主入口。"""
    args = build_parser().parse_args(argv)
    COMMAND_MAP[args.command](args)


if __name__ == "__main__":
    main()
