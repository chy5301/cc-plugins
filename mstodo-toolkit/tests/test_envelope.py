"""envelope 模块单测：信封结构、字段掩码、退出码。"""
import json

import pytest
from mstodo_lib import envelope as env


def test_exit_codes_are_banded():
    # 结果类 0-9，模式类 10+
    assert (env.EXIT_OK, env.EXIT_ERROR, env.EXIT_USAGE) == (0, 1, 2)
    assert (env.EXIT_NOT_FOUND, env.EXIT_PERMISSION) == (3, 4)
    assert (env.EXIT_PARTIAL, env.EXIT_AUTH_PENDING) == (5, 6)
    assert env.EXIT_DRY_RUN == 10


def test_apply_fields_filters_each_item_of_a_list():
    data = [{"id": "1", "title": "a", "noise": "x"}, {"id": "2", "title": "b", "noise": "y"}]
    assert env.apply_fields(data, "id,title") == [{"id": "1", "title": "a"},
                                                  {"id": "2", "title": "b"}]


def test_apply_fields_filters_keys_of_a_dict():
    assert env.apply_fields({"id": "1", "title": "a", "noise": "x"}, "id") == {"id": "1"}


def test_apply_fields_silently_drops_unknown_keys():
    assert env.apply_fields([{"id": "1"}], "id,nope") == [{"id": "1"}]


def test_apply_fields_preserves_non_dict_items_in_list_as_is():
    """list 中混有非 dict 元素时，非 dict 项原样保留不被裁剪。"""
    data = [{"id": "1", "title": "a"}, "raw-string", {"id": "2"}]
    result = env.apply_fields(data, "id")
    assert result == [{"id": "1"}, "raw-string", {"id": "2"}]


def test_apply_fields_none_or_empty_means_no_trim():
    data = [{"id": "1", "title": "a"}]
    assert env.apply_fields(data, None) == data
    assert env.apply_fields(data, "") == data


def test_build_envelope_adds_result_count_only_for_lists():
    e = env.build_envelope([{"id": "1"}], command="list-lists")
    assert e["success"] is True
    assert e["metadata"]["result_count"] == 1
    assert e["metadata"]["command"] == "mstodo_cli list-lists"
    assert "result_count" not in env.build_envelope({"id": "1"}, command="get-list")["metadata"]


def test_build_envelope_marks_dry_run():
    e = env.build_envelope({"would_call": "x"}, command="delete-list", dry_run=True)
    assert e["metadata"]["dry_run"] is True


def test_output_prints_envelope_and_exits(capsys):
    with pytest.raises(SystemExit) as exc:
        env.output([{"id": "1"}], command="list-lists", took_ms=12)
    assert exc.value.code == env.EXIT_OK
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["data"] == [{"id": "1"}]
    assert parsed["metadata"]["took_ms"] == 12


def test_fail_omits_data_by_default(capsys):
    with pytest.raises(SystemExit) as exc:
        env.fail("CONFIG_ERROR", "未登录", suggestion="先跑 auth-start",
                 exit_code=env.EXIT_USAGE)
    assert exc.value.code == env.EXIT_USAGE
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["success"] is False
    assert parsed["error"]["code"] == "CONFIG_ERROR"
    assert parsed["error"]["suggestion"] == "先跑 auth-start"
    assert "data" not in parsed


def test_fail_carries_data_for_partial_failure(capsys):
    """spec §6.5：唯一一种 success:false 仍携带 data 的情况。"""
    with pytest.raises(SystemExit) as exc:
        env.fail("PARTIAL_FAILURE", "5 个清单中 4 个成功，1 个失败",
                 exit_code=env.EXIT_PARTIAL,
                 data=[{"id": "1"}],
                 extra={"aggregated_from": 5, "retry_after_seconds": 30})
    assert exc.value.code == env.EXIT_PARTIAL
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["success"] is False
    assert parsed["data"] == [{"id": "1"}]
    assert parsed["metadata"]["retry_after_seconds"] == 30
