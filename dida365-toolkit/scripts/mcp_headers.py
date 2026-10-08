#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Claude Code headersHelper：为官方滴答 MCP 连接输出认证头。

仅标准库，不做网络请求，不持久化 Token。失败时不输出任何认证头。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dida365_auth as auth  # noqa: E402

SERVER_URL_ENV = "CLAUDE_CODE_MCP_SERVER_URL"


def _status(server_url: str, ok: bool, error: auth.AuthConfigError | None = None) -> dict:
    status = {
        "ok": ok,
        "server_url": server_url,
        "domain": os.environ.get(auth.DOMAIN_ENV) or auth.API_BASE_URL,
        "token_present": bool((os.environ.get(auth.TOKEN_ENV) or "").strip()),
    }
    if error is not None:
        status["error"] = {"code": error.code, "message": error.message}
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="输出滴答 MCP 认证头（含凭据，勿手动回显）")
    parser.add_argument("--check", action="store_true", help="只输出不含凭据的配置状态")
    args = parser.parse_args(argv)

    server_url = (os.environ.get(SERVER_URL_ENV) or auth.MCP_SERVER_URL).strip()
    try:
        auth.validate_origin(server_url, auth.APPROVED_MCP_HOSTS)
        token = auth.resolve_config()
    except auth.AuthConfigError as exc:
        if args.check:
            print(json.dumps(_status(server_url, ok=False, error=exc), ensure_ascii=False))
        else:
            print(f"配置错误 [{exc.code}]：{exc.message}", file=sys.stderr)
            if exc.suggestion:
                print(f"建议：{exc.suggestion}", file=sys.stderr)
        return 1

    if args.check:
        print(json.dumps(_status(server_url, ok=True), ensure_ascii=False))
        return 0

    json.dump(auth.authorization_header(token), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
