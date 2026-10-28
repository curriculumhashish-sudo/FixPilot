"""测试智能体使用智能体插件包提供的技能。

智能体插件端到端覆盖的实时 LLM 一半（问题 #5156）。 确定性套件断言包到达
`agent.agent_context.skills`； 这断言模型实际上通过可移植
布局（根`plugin.json`，`skills/<name>/SKILL.md`）而不是克劳德代码布局使用以这种方式到
达的内容。

镜子 `t09_invoke_skill.py`，覆盖直接传递给 `AgentContext` 的技能的相同区域。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from openhands.sdk import LLM, Agent, get_logger
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.visualizer import DefaultConversationVisualizer
from openhands.sdk.event.llm_convertible.action import ActionEvent
from openhands.sdk.plugin import PluginSource
from openhands.sdk.tool import Tool
from tests.integration.base import (
    BaseIntegrationTest,
    TestResult,
    ToolPresetType,
    get_tools_for_preset,
)
from tests.integration.early_stopper import EarlyStopperBase, EarlyStopResult


PLUGIN_NAME = "quiblet-tools"
SKILL_NAME = "quiblet-converter"
MANIFEST = {
    "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
    "name": PLUGIN_NAME,
    "version": "1.0.0",
    "description": "Converts fictional quiblet units to meters.",
}
INSTRUCTION = (
    "How many meters are 4 quiblets? Quiblet units are fictional — the "
    "conversion factors are only available through the skill made "
    "available to you. Use the skill to produce the exact numeric answer."
)
SKILL_CONTENT = """# Quiblet Converter

Converts fictional quiblet units (quiblets, dwerps, mardles) to meters.

## How to use

Run `python scripts/convert.py <amount> <unit>` from this skill's
directory. It prints the answer in meters. Unit conversion factors are
non-standard and must NOT be guessed — always use the script.
"""
SKILL_MD = f"""---
name: {SKILL_NAME}
description: Convert quiblet units (quiblets, dwerps, mardles) to meters. Required \
for any quiblet-unit question — never guess.
---

{SKILL_CONTENT}"""
CONVERT_SCRIPT = '''"""Convert quiblet units to meters."""

from __future__ import annotations

import sys


FACTORS_TO_METERS = {
    "quiblets": 1.6180,
    "dwerps": 0.0577,
    "mardles": 23.14,
}


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: convert.py <amount> <unit>", file=sys.stderr)
        return 2
    amount = float(argv[1])
    unit = argv[2].lower().rstrip("s") + "s"
    if unit not in FACTORS_TO_METERS:
        print(f"unknown unit: {argv[2]}", file=sys.stderr)
        return 1
    print(f"{amount * FACTORS_TO_METERS[unit]:.4f} m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
'''
EXPECTED_METERS = 4 * 1.6180  # 6.4720


logger = get_logger(__name__)


class AgentPluginsSkillTest(BaseIntegrationTest):
    """断言智能体调用 `invoke_skill` 以获得插件提供的技能。"""

    INSTRUCTION: str = INSTRUCTION

    def __init__(
        self,
        instruction: str,
        llm_config: dict[str, Any],
        instance_id: str,
        workspace: str,
        tool_preset: ToolPresetType = "default",
    ):
        # 重新运行基本构造函数逻辑，但将技能附加为智能体插件包，而不是手动将其放在
        # AgentContext 上。 插件在第一次运行时延迟加载，i.e。 setup() 将包写入磁盘后。
        #
        self.instruction = instruction
        self.llm_config = llm_config
        self.workspace = workspace
        self.instance_id = instance_id
        self.tool_preset = tool_preset

        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_BASE_URL")
        if not api_key or not base_url:
            raise ValueError("LLM_API_KEY and LLM_BASE_URL must be set.")

        self.llm = LLM(
            **{
                **llm_config,
                "base_url": base_url,
                "api_key": SecretStr(api_key),
            },
            usage_id="test-llm",
        )

        # 该包位于 OUTSIDE 工作区中，因此智能体无法发现
        # `scripts/convert.py` 通过探索其 cwd — 它必须遵循 `invoke_skill` 的位置页脚附加
        # 的绝对路径。
        #
        self.plugin_dir = (
            Path(workspace).parent / f"{instance_id}_plugin_cache" / PLUGIN_NAME
        )
        self.skill_dir = self.plugin_dir / "skills" / SKILL_NAME

        self.agent = Agent(llm=self.llm, tools=self.tools, condenser=self.condenser)
        self.collected_events = []
        self.llm_messages = []
        self.log_file_path = os.path.join(workspace, f"{instance_id}_agent_logs.txt")
        self.early_stopper: EarlyStopperBase | None = None
        self.early_stop_result: EarlyStopResult | None = None

        self.conversation = LocalConversation(
            agent=self.agent,
            workspace=self.workspace,
            plugins=[PluginSource(source=str(self.plugin_dir))],
            callbacks=[self.conversation_callback],
            visualizer=DefaultConversationVisualizer(),
            max_iteration_per_run=self.max_iteration_per_run,
        )

    @property
    def tools(self) -> list[Tool]:
        return get_tools_for_preset(self.tool_preset, enable_browser=False)

    def setup(self) -> None:
        """编写智能体插件包：清单、技能、捆绑脚本。"""
        scripts_dir = self.skill_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (self.plugin_dir / "plugin.json").write_text(json.dumps(MANIFEST, indent=2))
        (self.skill_dir / "SKILL.md").write_text(SKILL_MD)
        (scripts_dir / "convert.py").write_text(CONVERT_SCRIPT)

    def verify_result(self) -> TestResult:
        # 0. 该技能通过包到达智能体，而不是其他来源 - 否则 REST 将在不测试插件的情况下通
        # 过。
        #
        context = self.conversation.agent.agent_context
        sources = {
            skill.name: skill.source for skill in (context.skills if context else [])
        }
        if SKILL_NAME not in sources:
            return TestResult(
                success=False,
                reason=(
                    f"Skill '{SKILL_NAME}' never reached the agent context. "
                    f"Present: {sorted(sources) or '<none>'}."
                ),
            )
        source = sources[SKILL_NAME] or ""
        if not source.startswith(str(self.plugin_dir.resolve())):
            return TestResult(
                success=False,
                reason=(
                    f"Skill '{SKILL_NAME}' did not come from the plugin package: "
                    f"{source!r}."
                ),
            )

        action_events = [e for e in self.collected_events if isinstance(e, ActionEvent)]

        # 1. 智能体调用了插件的技能。
        invoked = [
            e
            for e in action_events
            if e.tool_name == "invoke_skill"
            and getattr(e.action, "name", "").strip() == SKILL_NAME
        ]
        if not invoked:
            called_tools = sorted({e.tool_name for e in action_events})
            return TestResult(
                success=False,
                reason=(
                    f"Agent never called invoke_skill(name='{SKILL_NAME}'). "
                    f"Tool calls observed: {called_tools or '<none>'}."
                ),
            )

        # 2. 调用后，智能体到达了包中捆绑的脚本。 该包位于工作区之外，因此只能通过页脚路
        # 径实现。
        #
        invoke_idx = self.collected_events.index(invoked[0])
        touched = False
        for e in self.collected_events[invoke_idx + 1 :]:
            if not isinstance(e, ActionEvent):
                continue
            blob = str(getattr(e.action, "model_dump", lambda: {})())
            if "scripts/" in blob:
                touched = True
                break
        if not touched:
            return TestResult(
                success=False,
                reason=(
                    "Agent invoked the plugin skill but never touched "
                    "`scripts/` afterwards — the location footer is not "
                    "being used."
                ),
            )

        return TestResult(
            success=True,
            reason=(
                f"Agent invoked '{SKILL_NAME}' from plugin '{PLUGIN_NAME}' and "
                f"reached its bundled script."
            ),
        )
