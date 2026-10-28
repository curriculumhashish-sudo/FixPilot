"""行为的共享实用程序集成测试。"""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent
from typing import Any

from openhands.sdk import get_logger
from openhands.sdk.tool import Tool
from tests.integration.base import (
    BaseIntegrationTest,
    SkipTest,
    ToolPresetType,
    get_tools_for_preset,
)
from tests.integration.early_stopper import EarlyStopperBase


logger = get_logger(__name__)

PINNED_SOFTWARE_AGENT_SDK_COMMIT = "693c32618dca43e6506a785da4e37575e387a638"


def clone_pinned_software_agent_repo(workspace: str) -> Path:
    """在固定提交处克隆 software-智能体-SDK 存储库。"""
    repo_dir = Path(workspace) / "software-agent-sdk"

    try:
        subprocess.run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "https://github.com/OpenHands/software-agent-sdk.git",
                str(repo_dir),
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )

        subprocess.run(
            [
                "git",
                "fetch",
                "origin",
                PINNED_SOFTWARE_AGENT_SDK_COMMIT,
                "--depth",
                "1",
            ],
            cwd=repo_dir,
            check=True,
            capture_output=True,
            timeout=60,
        )

        subprocess.run(
            ["git", "checkout", PINNED_SOFTWARE_AGENT_SDK_COMMIT],
            cwd=repo_dir,
            check=True,
            capture_output=True,
            timeout=30,
        )

        logger.info("Cloned software-agent-sdk to: %s", repo_dir)

    except subprocess.TimeoutExpired as exc:
        message = "Git clone timed out; skipping behavior test"
        logger.warning(message)
        raise SkipTest(message) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", "ignore") if exc.stderr else ""
        details = stderr.strip() or str(exc)
        message = (
            f"Git command failed while preparing behavior test workspace: {details}"
        )
        logger.warning(message)
        raise SkipTest(message) from exc
    except Exception as exc:  # noqa: BLE001
        message = f"Unable to prepare behavior test workspace: {exc}"
        logger.warning(message)
        raise SkipTest(message) from exc

    return repo_dir


def default_behavior_tools(tool_preset: ToolPresetType = "default") -> list[Tool]:
    """根据工具预设返回行为测试的默认工具。"""
    return get_tools_for_preset(tool_preset, enable_browser=False)


ENVIRONMENT_TIPS_BODY = """\
- If you see another checkout lives under
  /home/runner/_work/software-agent-sdk/software-agent-sdk,
  ignore it and stay within this workspace.
- Use `uv` (as per development guide) to avoid collision with the other checkout
  when running Python commands.
"""


def append_environment_tips(body: str) -> str:
    """将共享环境提示附加到指令正文。"""
    trimmed_body = body.rstrip()
    tips = dedent(ENVIRONMENT_TIPS_BODY).rstrip()
    return f"{trimmed_body}\n\nImportant environment notes:\n{tips}\n"


class SoftwareAgentSDKBehaviorTest(BaseIntegrationTest):
    """为行为测试提供通用设置和工具的基类。"""

    repo_dir: Path | None

    def __init__(
        self,
        instruction: str,
        llm_config: dict[str, Any],
        instance_id: str,
        workspace: str,
        tool_preset: ToolPresetType = "default",
    ):
        super().__init__(instruction, llm_config, instance_id, workspace, tool_preset)
        self.repo_dir = None

    @property
    def tools(self) -> list[Tool]:
        return default_behavior_tools(self.tool_preset)

    def get_early_stopper(self) -> EarlyStopperBase | None:
        """在子类中重写以提供此测试的早期阻止程序。

        Returns:
            EarlyStopperBase 实例，或 None 禁用提前停止。
        """
        return None

    def setup(self) -> None:
        self.repo_dir = clone_pinned_software_agent_repo(self.workspace)
        # 如果子类提供，则配置早期停止器
        self.early_stopper = self.get_early_stopper()
        self.after_workspace_setup()

    def after_workspace_setup(self) -> None:
        """如果需要，挂钩子类以执行额外的设置。"""
        return
