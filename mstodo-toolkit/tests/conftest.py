"""让测试能 import scripts/ 下的 mstodo_lib 包。"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    d = tmp_path / "state"
    monkeypatch.setenv("MSTODO_TOKEN_CACHE", str(d))
    monkeypatch.delenv("MSTODO_CLIENT_ID", raising=False)
    monkeypatch.delenv("MSTODO_TENANT", raising=False)
    return d
