"""可观察性实用程序的测试。"""

import os
from unittest.mock import patch

import openhands.sdk.observability.utils as utils
from openhands.sdk.observability.utils import get_env


def test_get_env_from_environment():
    """get_env 返回进程环境中的值。"""
    with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
        assert get_env("TEST_VAR") == "test_value"


def test_get_env_not_found():
    """当变量未设置时，get_env 返回 None。"""
    with patch.dict(os.environ, {}, clear=True):
        assert get_env("NONEXISTENT_VAR") is None


def test_get_env_does_not_use_python_dotenv():
    """回归问题 #1325 的守卫。

    崩溃来自 Python-dotenv 的 ``find_dotenv()``，它遍历调用堆栈并执行
    ``assert frame.f_back is not None``。 这在框架没有磁盘源文件的部署中失败（打包/冻
    结构建、删除的 CWD、线程运行执行代码）。
    加载 ``.env`` 现在是主机应用程序的责任，因此 ``get_env`` 必须单独读取
    from ``os.environ`` and must not import or call python-dotenv.

    将 ``get_env`` 恢复为 ``dotenv_values()`` 调用会使此操作失败。
    """
    assert not hasattr(utils, "dotenv_values")
