"""测试 SDK 启动横幅。"""

import pytest

from openhands.sdk.banner import _print_banner


@pytest.fixture
def reset_banner_state(monkeypatch):
    """在每次测试之前和之后重置横幅状态和环境变量。"""
    import openhands.sdk.banner as banner_module

    # 如果设置了 (e.g., from CI)，则删除抑制环境变量
    monkeypatch.delenv("OPENHANDS_SUPPRESS_BANNER", raising=False)

    original_state = banner_module._BANNER_PRINTED
    banner_module._BANNER_PRINTED = False
    yield
    banner_module._BANNER_PRINTED = original_state


def test_banner_prints_to_stderr(reset_banner_state, capsys):
    """测试横幅是否打印到 stderr。"""
    _print_banner("1.0.0")

    captured = capsys.readouterr()
    assert "OpenHands SDK v1.0.0" in captured.err
    assert "github.com/OpenHands/software-agent-sdk/issues" in captured.err
    assert "openhands.dev/joinslack" in captured.err
    assert "openhands.dev/product/sdk" in captured.err
    assert "OPENHANDS_SUPPRESS_BANNER=1" in captured.err
    assert captured.out == ""


def test_banner_prints_only_once(reset_banner_state, capsys):
    """测试横幅是否只打印一次，即使多次调用也是如此。"""
    _print_banner("1.0.0")
    _print_banner("1.0.0")
    _print_banner("1.0.0")

    captured = capsys.readouterr()
    assert captured.err.count("OpenHands SDK") == 1


def test_banner_suppressed_by_env_var(monkeypatch, reset_banner_state, capsys):
    """测试 OPENHANDS_SUPPRESS_BANNER=1 抑制横幅。"""
    monkeypatch.setenv("OPENHANDS_SUPPRESS_BANNER", "1")

    _print_banner("1.0.0")

    captured = capsys.readouterr()
    assert captured.err == ""


def test_banner_suppressed_by_env_var_true(monkeypatch, reset_banner_state, capsys):
    """测试 OPENHANDS_SUPPRESS_BANNER=True 是否抑制横幅。"""
    monkeypatch.setenv("OPENHANDS_SUPPRESS_BANNER", "true")

    _print_banner("1.0.0")

    captured = capsys.readouterr()
    assert captured.err == ""
