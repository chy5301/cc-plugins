"""schemas 模块单测：日期展开、body 展开、union 类型、校验。"""
import pytest
from mstodo_lib import schemas


@pytest.fixture(autouse=True)
def clean_tz(monkeypatch):
    monkeypatch.delenv("MSTODO_TIMEZONE", raising=False)


def test_default_timezone_is_iana_shanghai():
    assert schemas.default_timezone() == "Asia/Shanghai"


def test_default_timezone_honours_env(monkeypatch):
    monkeypatch.setenv("MSTODO_TIMEZONE", "China Standard Time")
    assert schemas.default_timezone() == "China Standard Time"


def test_expand_datetime_pads_date_only_to_midnight():
    assert schemas.expand_datetime("2026-04-05") == {
        "dateTime": "2026-04-05T00:00:00", "timeZone": "Asia/Shanghai"}


def test_expand_datetime_adds_default_zone_to_naive_datetime():
    assert schemas.expand_datetime("2026-04-05T14:30:00") == {
        "dateTime": "2026-04-05T14:30:00", "timeZone": "Asia/Shanghai"}


def test_expand_datetime_passes_through_full_object():
    full = {"dateTime": "2026-04-05T14:30:00", "timeZone": "China Standard Time"}
    assert schemas.expand_datetime(full) == full


def test_expand_datetime_accepts_windows_zone_via_env(monkeypatch):
    monkeypatch.setenv("MSTODO_TIMEZONE", "China Standard Time")
    assert schemas.expand_datetime("2026-04-05")["timeZone"] == "China Standard Time"


def test_expand_body_field_wraps_plain_string_as_text():
    assert schemas.expand_body_field("覆盖本周三个里程碑") == {
        "content": "覆盖本周三个里程碑", "contentType": "text"}


def test_expand_body_field_passes_through_object():
    full = {"content": "<p>hi</p>", "contentType": "html"}
    assert schemas.expand_body_field(full) == full


def test_normalize_body_expands_every_datetime_field():
    out = schemas.normalize_body("create-task", {
        "title": "写周报",
        "dueDateTime": "2026-04-05",
        "reminderDateTime": "2026-04-04T09:00:00",
        "body": "覆盖本周三个里程碑",
    })
    assert out["dueDateTime"]["dateTime"] == "2026-04-05T00:00:00"
    assert out["reminderDateTime"]["dateTime"] == "2026-04-04T09:00:00"
    assert out["body"] == {"content": "覆盖本周三个里程碑", "contentType": "text"}
    assert out["title"] == "写周报"


def test_normalize_body_does_not_mutate_caller_dict():
    original = {"dueDateTime": "2026-04-05"}
    schemas.normalize_body("create-task", original)
    assert original["dueDateTime"] == "2026-04-05"


def test_create_task_schema_declares_body_as_union_type():
    """spec §6.3 / I5：body 同时接受 str 与 object，单值 type 表达不了。"""
    field = schemas.get_schema("create-task")["fields"]["body"]
    assert field["type"] == ["str", "object"]


def test_create_task_schema_warns_about_the_name_clash():
    desc = schemas.get_schema("create-task")["fields"]["body"]["desc"]
    assert "--body" in desc


def test_create_task_schema_enumerates_status_and_importance():
    fields = schemas.get_schema("update-task")["fields"]
    assert fields["status"]["enum"] == [
        "notStarted", "inProgress", "completed", "waitingOnOthers", "deferred"]
    assert fields["importance"]["enum"] == ["low", "normal", "high"]


def test_create_task_requires_title():
    assert schemas.validate_body("create-task", {}) == [
        "create-task 缺少必需字段: title"]


def test_validate_body_rejects_value_outside_enum():
    errors = schemas.validate_body("update-task", {"status": "done"})
    assert errors == [("update-task 的 status 取值非法: 'done'，允许值: "
                       "notStarted, inProgress, completed, waitingOnOthers, deferred")]


def test_validate_body_rejects_wrong_scalar_type():
    errors = schemas.validate_body("create-task", {"title": 123})
    assert errors == ["create-task 的 title 类型应为 str，实际为 int"]


def test_validate_body_accepts_either_arm_of_a_union():
    assert schemas.validate_body("create-task", {"title": "a", "body": "文本"}) == []
    assert schemas.validate_body("create-task", {
        "title": "a", "body": {"content": "x", "contentType": "text"}}) == []


def test_validate_body_rejects_update_task_with_no_fields():
    assert schemas.validate_body("update-task", {}) == [
        "update-task 至少需要一个待更新字段"]


def test_get_schema_raises_on_unknown_operation():
    with pytest.raises(KeyError):
        schemas.get_schema("move-tasks")


def test_all_schemas_covers_every_body_operation():
    assert set(schemas.all_schemas()) == {
        "create-list", "update-list",
        "create-task", "update-task",
        "create-checklist-item", "update-checklist-item",
    }


# Finding 1 修复：normalize_body 应仅展开 schema 声明的字段
def test_normalize_body_does_not_expand_undeclared_body_field():
    """create-list 不声明 body 字段，所以不应展开。"""
    result = schemas.normalize_body("create-list", {"body": "oops"})
    assert result["body"] == "oops"  # 保持字符串不变


def test_normalize_body_expands_declared_body_field():
    """create-task 声明 body 字段，应该正常展开。"""
    result = schemas.normalize_body("create-task", {"title": "x", "body": "文本"})
    assert result["body"] == {"content": "文本", "contentType": "text"}


# Finding 2 修复：expand_datetime 应验证日期形状
def test_expand_datetime_rejects_invalid_shape_not_a_date():
    """10 个字符但不是日期格式的字符串应被拒绝。"""
    with pytest.raises(schemas.InvalidDatetimeFormat):
        schemas.expand_datetime("not-a-date")


def test_expand_datetime_rejects_invalid_shape_short_date():
    """YYYY-M-D（缺少 0 padding）应被拒绝。"""
    with pytest.raises(schemas.InvalidDatetimeFormat):
        schemas.expand_datetime("2026-4-5")


def test_expand_datetime_rejects_invalid_shape_trailing_space():
    """日期字符串含尾随空格应被拒绝。"""
    with pytest.raises(schemas.InvalidDatetimeFormat):
        schemas.expand_datetime("2026-04-05 ")


def test_expand_datetime_accepts_valid_date():
    """合法的 YYYY-MM-DD 格式应正常工作。"""
    result = schemas.expand_datetime("2026-04-05")
    assert result["dateTime"] == "2026-04-05T00:00:00"


def test_expand_datetime_accepts_valid_datetime():
    """合法的 YYYY-MM-DDTHH:MM:SS 格式应正常工作。"""
    result = schemas.expand_datetime("2026-04-05T14:30:00")
    assert result["dateTime"] == "2026-04-05T14:30:00"


def test_expand_datetime_accepts_valid_datetime_with_fractional_seconds():
    """带小数秒的合法时间戳应正常工作。"""
    result = schemas.expand_datetime("2026-04-05T14:30:00.123")
    assert result["dateTime"] == "2026-04-05T14:30:00.123"


# Finding 2 补充修复：尾随与前导空白应被拒绝
def test_expand_datetime_rejects_trailing_newline_in_date():
    """日期末尾含换行符应被拒绝（正则 $ 陷阱）。"""
    with pytest.raises(schemas.InvalidDatetimeFormat):
        schemas.expand_datetime("2026-04-05\n")


def test_expand_datetime_rejects_trailing_newline_in_datetime():
    """日期时间末尾含换行符应被拒绝。"""
    with pytest.raises(schemas.InvalidDatetimeFormat):
        schemas.expand_datetime("2026-04-05T14:30:00\n")


def test_expand_datetime_rejects_trailing_tab():
    """日期末尾含制表符应被拒绝。"""
    with pytest.raises(schemas.InvalidDatetimeFormat):
        schemas.expand_datetime("2026-04-05\t")


def test_expand_datetime_rejects_leading_newline():
    """日期开头含换行符应被拒绝。"""
    with pytest.raises(schemas.InvalidDatetimeFormat):
        schemas.expand_datetime("\n2026-04-05")
