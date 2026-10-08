import pytest

from dida365_auth import (
    APPROVED_API_HOSTS,
    APPROVED_MCP_HOSTS,
    AuthConfigError,
    authorization_header,
    check_domain_config,
    resolve_config,
    resolve_token,
    validate_origin,
)


def env(**overrides):
    base = {"DIDA365_API_TOKEN": "dp_test_token"}
    base.update(overrides)
    return base


def test_resolve_token_ok():
    assert resolve_token(env()) == "dp_test_token"


def test_resolve_token_missing():
    with pytest.raises(AuthConfigError) as excinfo:
        resolve_token({})
    assert excinfo.value.code == "TOKEN_MISSING"
    assert "DIDA365_API_TOKEN" in excinfo.value.message


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
        validate_origin("https://evil.example/", APPROVED_API_HOSTS)
    assert "dp_test_token" not in str(excinfo.value)


def test_resolve_config_checks_domain_before_token():
    with pytest.raises(AuthConfigError) as excinfo:
        resolve_config({"DIDA365_API_DOMAIN": "api.ticktick.com"})
    assert excinfo.value.code == "REGION_UNSUPPORTED"


def test_authorization_header():
    assert authorization_header("dp_x") == {"Authorization": "Bearer dp_x"}
