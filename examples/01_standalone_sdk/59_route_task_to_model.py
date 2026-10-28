"""使用内置的 route_task_to_model 工具将每个任务路由到最佳的 LLM。

智能体从默认配置文件开始。 当它调用 ``route_task_to_model`` 工具时 (a.k.a.
``ClassifyAndSwitchLLMTool``),
一个轻量级分类器 LLM 检查最近的对话，选择最适合的任务的保存 LLM 头像，然后在智能体继
续之前，切换对话到那个头像。

此示例显示了该工具支持的两种元轮廓形状：

1. **结构化类** — 一组固定的``{description, model}``行； 分类器返回类别索引。
2. **直接提示词** — 使用 ``{{ instance_text }}`` 和 ``{{ model_table }}`` 渲染的
``prompt_template``； 分类器直接返回模型名称。

两种模式都要求目标模型以保存的 LLM 配置文件的形式存在（工具按名称切换到它们）或通过
``meta_profile_llms`` 内联提供。

用途：
    LLM_API_KEY=... LLM_BASE_URL=https://llm-proxy.app.all-hands.dev \
        uv run python examples/01_standalone_sdk/59_route_task_to_model.py
"""

import os

from pydantic import SecretStr

from openhands.sdk import LLM, Conversation, OpenHandsAgentSettings
from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.sdk.llm.meta_profile_store import MetaProfile, MetaProfileClass
from openhands.tools.preset.default import register_default_tools


DEFAULT_BASE_URL = "https://llm-proxy.app.all-hands.dev"

# 已保存的配置文件名称。 route_task_to_model工具通过名称将对话切换到其中一个，因此，
# LLMProfileStore中的每个都必须存在。
#
DEFAULT_PROFILE = "example-router-default"
CHEAP_PROFILE = "example-router-cheap"
STRONG_PROFILE = "example-router-strong"
CLASSIFIER_PROFILE = "example-router-classifier"

CHEAP_MODEL = "openai/gpt-5.5"
STRONG_MODEL = "openai/prod/claude-sonnet-4-5-20250929"

api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."
base_url = os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL)


# ── 1. 保存路由器将在 ──────────── 之间选择的 LLM 个配置文件
profile_store = LLMProfileStore()
for name, model, usage_id in [
    (DEFAULT_PROFILE, CHEAP_MODEL, "router-default"),
    (CHEAP_PROFILE, CHEAP_MODEL, "router-cheap"),
    (STRONG_PROFILE, STRONG_MODEL, "router-strong"),
    (CLASSIFIER_PROFILE, CHEAP_MODEL, "router-classifier"),
]:
    profile_store.save(
        name,
        LLM(
            model=model,
            api_key=SecretStr(api_key),
            base_url=base_url,
            usage_id=usage_id,
        ),
        include_secrets=True,
    )

try:
    # ── 2. 定义一个meta-profile：结构化类────────────────────── 分类器返回一个从1开始的
    # 类索引； ``model`` 是要切换到的已保存配置文件名称。 ``classifier_model`` 本身是用
    # 于运行分类调用的已保存配置文件名称。
    #
    structured_meta = MetaProfile(
        classifier_model=CLASSIFIER_PROFILE,
        classes=[
            MetaProfileClass(
                description="Simple lookups, small edits, formatting",
                model=CHEAP_PROFILE,
            ),
            MetaProfileClass(
                description="Multi-file reasoning, debugging, architecture",
                model=STRONG_PROFILE,
            ),
        ],
    )

    # ── 3. 通过OpenHandsAgentSettings构建智能体 ──────────────────────
    # ``create_agent()`` 按名称默认为标准执行工具（终端、file_editor、task_tracker）；
    # 他们的实现位于
    # ``openhands-tools`` 且必须在智能体初始化之前注册。
    register_default_tools(enable_browser=False)

    # 只需启用该工具 + 设置活动元配置文件名称即可将 route_task_to_model 连接到智能体。
    # 智能体在默认配置文件上启动，并且仅在调用该工具时进行切换。
    #
    settings = OpenHandsAgentSettings(
        llm=profile_store.load(DEFAULT_PROFILE),
        enable_classify_and_switch_llm_tool=True,
        active_meta_profile="structured",
        meta_profile=structured_meta,
    )
    agent = settings.create_agent()

    conversation = Conversation(agent=agent, workspace=os.getcwd())
    print(f"Starting model: {conversation.agent.llm.model}")

    conversation.send_message(
        "Call the route_task_to_model tool now. After it returns, answer in one "
        "short sentence naming the model the tool switched to."
    )
    conversation.run()

    print(f"Active model after routing: {conversation.agent.llm.model}")

    for usage_id, metrics in conversation.state.stats.usage_to_metrics.items():
        print(f"  [{usage_id}] cost=${metrics.accumulated_cost:.6f}")
    combined = conversation.state.stats.get_combined_metrics()
    print(f"Total cost: ${combined.accumulated_cost:.6f}")
    print(f"EXAMPLE_COST: {combined.accumulated_cost}")

    # ── 4. (信息) 直接-提示词元素形状 ──────────────────────── 而不是固定类，您给分类器
    # 一个自由形式的提示词模板和一个模型表。 分类器直接将模型名称返回为 JSON
    # ``{"model": "<name>", "reason": "..."}``。 这是 Pareto 提示词元轮廓使用的形状。
    #
    direct_meta = MetaProfile(
        classifier_model=CLASSIFIER_PROFILE,
        prompt_template=(
            "Pick the best model for the task below.\n\n"
            "{{ model_table }}\n\n"
            "Task:\n{{ instance_text }}\n\n"
            'Return ONLY JSON: {"model": "<exact profile name>", "reason": "<short>"}'
        ),
        model_table=(
            f"- {CHEAP_PROFILE}: fast and cheap, good for simple tasks\n"
            f"- {STRONG_PROFILE}: slower and stronger, good for hard tasks"
        ),
    )
    print()
    print("Direct-prompt meta-profile (not executed here):")
    print(direct_meta.model_dump_json(indent=2))

finally:
    for name in [
        DEFAULT_PROFILE,
        CHEAP_PROFILE,
        STRONG_PROFILE,
        CLASSIFIER_PROFILE,
    ]:
        profile_store.delete(name)
