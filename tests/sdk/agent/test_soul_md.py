"""单元测试适用于 _load_soul_md 装载机边缘情况。

对完整渲染系统提示词进行快照测试，默认和自定义灵魂内容与其他提示词黄金文件一起位于
``tests/sdk/context/prompts/test_prompt_snapshot.py`` 中。
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

from openhands.sdk.agent.base import _load_soul_md


def test_load_soul_md_returns_default_when_missing(tmp_path: Path) -> None:
    with patch("openhands.sdk.agent.base._SOUL_PATH", str(tmp_path / "SOUL.md")):
        assert "OpenHands agent" in _load_soul_md()


def test_load_soul_md_returns_default_when_empty(tmp_path: Path) -> None:
    soul = tmp_path / "SOUL.md"
    soul.write_text("")
    with patch("openhands.sdk.agent.base._SOUL_PATH", str(soul)):
        assert "OpenHands agent" in _load_soul_md()


def test_load_soul_md_returns_default_when_whitespace_only(
    tmp_path: Path,
) -> None:
    soul = tmp_path / "SOUL.md"
    soul.write_text("   \n\n  \n")
    with patch("openhands.sdk.agent.base._SOUL_PATH", str(soul)):
        assert "OpenHands agent" in _load_soul_md()


def test_load_soul_md_returns_content(tmp_path: Path) -> None:
    soul = tmp_path / "SOUL.md"
    soul.write_text("You are a helpful cat agent.")
    with patch("openhands.sdk.agent.base._SOUL_PATH", str(soul)):
        assert _load_soul_md() == "You are a helpful cat agent."


def test_load_soul_md_strips_whitespace(tmp_path: Path) -> None:
    soul = tmp_path / "SOUL.md"
    soul.write_text("\n  You are direct.  \n\n")
    with patch("openhands.sdk.agent.base._SOUL_PATH", str(soul)):
        assert _load_soul_md() == "You are direct."


def test_load_soul_md_preserves_internal_structure(tmp_path: Path) -> None:
    content = textwrap.dedent("""\
        # Identity
        You are smolpaws.

        # Style
        Be direct. Be concise.
    """)
    soul = tmp_path / "SOUL.md"
    soul.write_text(content)
    with patch("openhands.sdk.agent.base._SOUL_PATH", str(soul)):
        result = _load_soul_md()
        assert "# Identity" in result
        assert "# Style" in result
        assert "smolpaws" in result
