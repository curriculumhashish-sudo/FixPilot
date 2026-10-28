"""测试工具类功能。"""

import gc
import threading
from abc import ABC

import pytest
from pydantic import Field, ValidationError

from openhands.sdk.tool import Action
from openhands.sdk.tool.spec import Tool
from openhands.sdk.tool.tool import (
    _action_types_with_risk,
    _action_types_with_summary,
    _create_action_type_with_summary,
    create_action_type_with_risk,
)
from openhands.sdk.utils.models import _get_checked_concrete_subclasses


# 必须存在于模块范围内（Pydantic 拒绝 <locals> 类）。
class _Bug2199Action(Action, ABC):
    cmd: str = Field(description="test")


class _Bug2642ActionA(Action, ABC):
    command: str = Field(description="shell command")


class _Bug2642ActionB(Action, ABC):
    path: str = Field(description="file path")


class _Bug2642ActionC(Action, ABC):
    tab_id: int = Field(description="tab id")


def test_tool_json_round_trip():
    tool = Tool(name="TestTool", params={"working_dir": "/test", "timeout": 45})

    assert Tool.model_validate_json(tool.model_dump_json()) == tool


def test_tool_immutability():
    """测试工具在参数修改后的行为是否正确。"""
    original_params = {"test_param": "/workspace"}
    tool = Tool(name="TerminalTool", params=original_params)

    # 修改原始参数不应影响工具
    original_params["test_param"] = "/changed"
    assert tool.params["test_param"] == "/workspace"


def test_tool_rejects_empty_name():
    with pytest.raises(ValidationError):
        Tool(name="")


def test_issue_2199_1(request):
    """重现问题 #2199：重复的动态 Action 包装类。

    当子智能体和线程同时对同一个输入调用 ``create_action_type_with_risk`` 或
    ``_create_action_type_with_summary`` 时，模块级缓存上的 TOCTOU 赛跑会导致两个具有
    相同 ``__name__`` 的不同
    类对象，从而导致 ``_get_checked_concrete_subclasses(Action)`` 引发
    ``ValueError("Duplicate class definition ...")``。

    Ref: https://github.com/issues/assigned?issue=OpenHands%7Csoftware-agent-sdk%7C2199
    """
    """包装相同类型的许多线程必须都获得相同的类对象。"""
    saved_risk = dict(_action_types_with_risk)

    def _cleanup():
        _action_types_with_risk.clear()
        _action_types_with_risk.update(saved_risk)
        gc.collect()

    request.addfinalizer(_cleanup)

    results: list[type] = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        results.append(create_action_type_with_risk(_Bug2199Action))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(set(id(r) for r in results)) == 1, "All threads must get the same class"
    _get_checked_concrete_subclasses(Action)


def test_issue_2199_2(request):
    """
    _create_action_type_with_summary 的相同比赛测试。
    """
    saved_risk = dict(_action_types_with_risk)
    saved_summary = dict(_action_types_with_summary)

    def _cleanup():
        _action_types_with_risk.clear()
        _action_types_with_risk.update(saved_risk)
        _action_types_with_summary.clear()
        _action_types_with_summary.update(saved_summary)
        gc.collect()

    request.addfinalizer(_cleanup)

    with_risk = create_action_type_with_risk(_Bug2199Action)
    results: list[type] = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        results.append(_create_action_type_with_summary(with_risk))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(set(id(r) for r in results)) == 1, "All threads must get the same class"
    _get_checked_concrete_subclasses(Action)


def test_issue_2642(request):
    """生成时出现重复的 Action 类定义错误子智能体。

    当子智能体对话在同一进程中重新初始化工具时，
    如果旧的 WithRisk 类仍然存在，``create_action_type_with_risk`` 可能会生成具有相同
     ``__name__`` 的 *第二个
     * 类对象
    ``Action.__subclasses__()`` 但模块级缓存已失去对它们的跟踪。
    ``_get_checked_concrete_subclasses(Action)`` 然后加注
    ``ValueError("Duplicate class definition ...")``.

    Ref: https://github.com/OpenHands/software-agent-sdk/issues/2642
    """
    bug_actions: list[type[Action]] = [
        _Bug2642ActionA,
        _Bug2642ActionB,
        _Bug2642ActionC,
    ]

    saved_risk = dict(_action_types_with_risk)
    saved_summary = dict(_action_types_with_summary)

    def _cleanup():
        _action_types_with_risk.clear()
        _action_types_with_risk.update(saved_risk)
        _action_types_with_summary.clear()
        _action_types_with_summary.update(saved_summary)
        gc.collect()

    request.addfinalizer(_cleanup)

    # 步骤 1 — 模拟创建 WithRisk 包装器的父对话。 在生产中，当智能体为每个工具调用
    # _get_tool_schema(add_security_risk_prediction=True) 时，就会发生这种情况。
    #
    first_gen: list[type] = []
    for action_type in bug_actions:
        with_risk = create_action_type_with_risk(action_type)
        _create_action_type_with_summary(with_risk)
        first_gen.append(with_risk)

    # 理智：还没有重复。
    _get_checked_concrete_subclasses(Action)

    # 第 2 步 — 模拟缓存丢失旧类的跟踪。 在生产中，当委托工具生成一个子智能体，其
    # action_type 是一个不同的对象 (e.g. 来自重新导入或动态工具重新创建），导致缓存键不
    # 匹配。
    #
    _action_types_with_risk.clear()
    _action_types_with_summary.clear()

    # 步骤 3 — 模拟子智能体对话，重新初始化其工具。 缓存未命中→再次调用type()→具有相同__
    # 名称__的第二类。
    #
    for action_type in bug_actions:
        create_action_type_with_risk(action_type)

    # 步骤 4 — 这是错误报告中爆炸的调用（在子智能体中的 Event/ToolDefinition 反序列化期
    # 间由 Action.resolve_kind() 触发）。
    #
    _get_checked_concrete_subclasses(Action)
