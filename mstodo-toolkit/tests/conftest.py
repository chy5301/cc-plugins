"""让测试能 import scripts/ 下的 mstodo_lib 包。"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
