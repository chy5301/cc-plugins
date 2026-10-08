import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from dida365_auth import (
    APPROVED_API_HOSTS,
    APPROVED_MCP_HOSTS,
    DEFAULT_TOKEN_FILE,
    TOKEN_FILE_ENV,
    AuthConfigError,
    authorization_header,
    check_domain_config,
    resolve_config,
    resolve_token,
    token_file_path,
    token_source,
    validate_origin,
)

# 保证不存在的凭据文件：父目录随机且从不创建，测试绝不读取真实 ~/.dida365/token
MISSING_TOKEN_FILE = str(Path(tempfile.gettempdir()) / f"dida365-tests-{uuid4().hex}" / "token")


def env(**overrides):
    base = {"DIDA365_API_TOKEN": "dp_test_token", TOKEN_FILE_ENV: MISSING_TOKEN_FILE}
    base.update(overrides)
    return base


def test_resolve_token_ok():
    assert resolve_token(env()) == "dp_test_token"


def test_resolve_token_missing():
    with pytest.raises(AuthConfigError) as excinfo:
        resolve_token({TOKEN_FILE_ENV: MISSING_TOKEN_FILE})
    assert excinfo.value.code == "TOKEN_MISSING"
    assert "DIDA365_API_TOKEN" in excinfo.value.message
    assert "凭据文件" in excinfo.value.message


def test_resolve_token_from_file(tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("dp_file_token\n", encoding="utf-8")
    assert resolve_token({TOKEN_FILE_ENV: str(token_file)}) == "dp_file_token"


def test_env_token_wins_over_file(tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("dp_file_token\n", encoding="utf-8")
    assert resolve_token(env(DIDA365_TOKEN_FILE=str(token_file))) == "dp_test_token"


def test_whitespace_only_file_is_missing(tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("   \n\t\n", encoding="utf-8")
    with pytest.raises(AuthConfigError) as excinfo:
        resolve_token({TOKEN_FILE_ENV: str(token_file)})
    assert excinfo.value.code == "TOKEN_MISSING"
    assert "凭据文件" in excinfo.value.message


def test_undecodable_file_is_treated_as_missing(tmp_path):
    token_file = tmp_path / "token"
    token_file.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(AuthConfigError) as excinfo:
        resolve_token({TOKEN_FILE_ENV: str(token_file)})
    assert excinfo.value.code == "TOKEN_MISSING"
    assert token_source({TOKEN_FILE_ENV: str(token_file)}) is None


def test_token_source_reports_env_file_or_none(tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("dp_file_token", encoding="utf-8")
    assert token_source({TOKEN_FILE_ENV: MISSING_TOKEN_FILE}) is None
    assert token_source({TOKEN_FILE_ENV: str(token_file)}) == "file"
    assert token_source(env(DIDA365_TOKEN_FILE=str(token_file))) == "env"


def test_token_file_path_override_and_default():
    assert token_file_path({}) == DEFAULT_TOKEN_FILE
    assert token_file_path({TOKEN_FILE_ENV: "~/custom/token"}) == Path.home() / "custom" / "token"


def test_domain_default_and_approved_ok():
    check_domain_config(env())
    check_domain_config(env(DIDA365_API_DOMAIN="api.dida365.com"))
    check_domain_config(env(DIDA365_API_DOMAIN="Api.Dida365.com"))


def test_domain_international_rejected():
    with pytest.raises(AuthConfigError) as excinfo:
        check_domain_config(env(DIDA365_API_DOMAIN="api.ticktick.com"))
    assert excinfo.value.code == "REGION_UNSUPPORTED"


def test_domain_unknown_rejected():
    with pytest.raises(AuthConfigError) as excinfo:
        check_domain_config(env(DIDA365_API_DOMAIN="example.internal"))
    assert excinfo.value.code == "REGION_UNSUPPORTED"


@pytest.mark.parametrize(
    "url",
    [
        "http://api.dida365.com/open/v1/project",
        "https://user@api.dida365.com/open/v1/project",
        "https://user:pw@api.dida365.com/open/v1/project",
        "https://api.dida365.com:8443/open/v1/project",
        "https://api.dida365.com:abc/open/v1/project",
        "https://api.dida365.com.evil.example/open/v1/project",
        "https://evil.example/open/v1/project",
        "https://[::1/open/v1/project",
    ],
)
def test_validate_origin_rejects(url):
    with pytest.raises(AuthConfigError) as excinfo:
        validate_origin(url, APPROVED_API_HOSTS)
    assert excinfo.value.code == "INVALID_TARGET"


def test_validate_origin_allows_case_and_default_port():
    validate_origin("https://API.DIDA365.COM:443/open/v1/project", APPROVED_API_HOSTS)


def test_validate_origin_keeps_host_sets_separate():
    validate_origin("https://mcp.dida365.com", APPROVED_MCP_HOSTS)
    validate_origin("https://mcp.dida365.com/", APPROVED_MCP_HOSTS)
    with pytest.raises(AuthConfigError):
        validate_origin("https://api.dida365.com", APPROVED_MCP_HOSTS)


def test_error_messages_and_repr_never_contain_token():
    with pytest.raises(AuthConfigError) as excinfo:
        resolve_config(
            {
                "DIDA365_API_TOKEN": "dp_test_token",
                "DIDA365_API_DOMAIN": "api.ticktick.com",
                TOKEN_FILE_ENV: MISSING_TOKEN_FILE,
            }
        )
    assert "dp_test_token" not in str(excinfo.value)
    assert "dp_test_token" not in repr(excinfo.value)
    assert str(AuthConfigError("X", "m", "s")) == "m"


def test_resolve_config_checks_domain_before_token():
    with pytest.raises(AuthConfigError) as excinfo:
        resolve_config({"DIDA365_API_DOMAIN": "api.ticktick.com", TOKEN_FILE_ENV: MISSING_TOKEN_FILE})
    assert excinfo.value.code == "REGION_UNSUPPORTED"


def test_authorization_header():
    assert authorization_header("dp_x") == {"Authorization": "Bearer dp_x"}
