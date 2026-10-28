"""适用于内置 ACP 提供程序的实时、无凭据的一致性探针。

对于每个 ``ACP_PROVIDERS``，通过 ``npx`` 启动 ``info.default_command`` 无误（verbatim
），并使用虚假的凭据和孤立
的数据目录，然后验证活服务器返回的内容，而不是注册表假设的内容。 它捕捉到的每一个历史
漂移（#3772，#3654，
#4629，#4812）之所以保持沉默，正是因为没有从
服务器 — 请参阅 OpenHands/software-智能体-SDK#4830 P0-1/P0-2。

无需 API 键、订阅或网络凭据：每种内置提供者的握手（初始化 / 验证 / new_session /
set_session_mode / 模型选择）都成功了，但使用的
是一个语法上存在的但无效的键，这使得这个套件在无认证的情况下在 fork PR 中运行是安全的
。 需要 ``npx`` (Node.js) 和网络访问 npm 注册表； 不
可用时跳过。

通过操作从默认运行中取消选中 ``acp_live`` marker (
``addopts = -m 'not stress and not acp_live'`` 在
pyproject.toml:) SDK默认测试作业是  *必需的* 合并检查，以及一个 npm-注册表 blip 或
upstream ACP 握手失败 —— 一种与
                                                                                                                         [
12注册表不可达，“上述跳过已经覆盖了——必须不能阻止无关的” PR. 运行显式地
``pytest -m acp_live``; CI 在单独的、非必需的环境中运行
``acp-live-tests`` [job, gated on changes to] ACP 注册表/目录文件（见 ）
``.github/workflows/tests.yml``).
"""  # noqa: E501

from __future__ import annotations

import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from acp.client.connection import ClientSideConnection
from acp.exceptions import RequestError as ACPRequestError

from openhands.sdk.agent.acp_agent import (
    ACPAgent,
    _apply_acp_model,
    _select_auth_method,
)
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.settings.acp_install_catalog import ACP_INSTALL_CATALOG
from openhands.sdk.settings.acp_providers import ACP_PROVIDERS
from openhands.sdk.utils.async_executor import AsyncExecutor
from openhands.sdk.workspace.local import LocalWorkspace


def _npm_registry_reachable(timeout: float = 3.0) -> bool:
    try:
        socket.create_connection(("registry.npmjs.org", 443), timeout=timeout).close()
        return True
    except OSError:
        return False


requires_npx = pytest.mark.skipif(
    shutil.which("npx") is None or not _npm_registry_reachable(),
    reason="npx (Node.js) not available, or npm registry unreachable",
)

pytestmark = pytest.mark.acp_live

# 语法上看起来有效但不起作用凭据。 足以让每个提供商的身份验证方法选择选择一个环境变量支
# 持的方法并清除握手； 真正的推理会拒绝它们，但不会发送任何轮次。
#
_BOGUS_KEY = "sk-acp-conformance-probe-0000000000000000000000000000"

# 模型接受度探针的每条调用截止时间 set_config_option / set_session_model 往返 — 这些是元
# 数据写入，而不是推理调用，因此即使冷启动，也应该在不到一秒内返回。
#
_MODEL_CALL_TIMEOUT = 15.0


def _node_version() -> tuple[int, ...] | None:
    """正在运行的 ``node`` 的版本作为可比较的元组，或 None。"""
    node = shutil.which("node")
    if node is None:
        return None
    try:
        raw = subprocess.run(
            [node, "--version"], capture_output=True, text=True, timeout=30
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        return tuple(int(part) for part in raw.lstrip("v").split(".")[:3])
    except ValueError:
        return None


def _skip_if_node_below_floor(provider_key: str) -> None:
    """当主机节点低于该提供商的节点时，跳过而不是失败
    包声明。

    这不是软处理：CLI的自身依赖在几行之后以一个看似无关的协议错误表面（pi引擎在
    `webidl.util.markAsUncloneable`处崩溃，然后适配器报告
    “在流被销毁后无法调用write”`session/new`），所以在这里的简单失败会被读作符合回归
    ，而不是未满足的前提条件。 该图像的自身地板在tests/cro
    ss/test_agent_server_build_metadata.py.中单独声明，与Dockerfile的版本号进行比较
    """
    floor = ACP_INSTALL_CATALOG[provider_key].min_node_version
    if floor is None:
        return
    running = _node_version()
    required = tuple(int(part) for part in floor.split("."))
    if running is not None and running < required:
        pytest.skip(
            f"provider {provider_key!r} declares node >={floor}; this host runs "
            f"v{'.'.join(map(str, running))}"
        )


def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """为探测器提供自己的 HOME 和虚假密钥，这样它就不会接触主机
    凭据（订阅登录，真实的API密钥）或真实的代理。"""
    isolated_home = tmp_path / "home"
    isolated_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(isolated_home))
    for var in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "GEMINI_API_KEY",
        # kimi-code 自己的 KIMI_API_KEY 是来自 $KIMI_CODE_HOME/config.toml 内部的只读，
        # 而不是来自环境，因此它无法清除身份验证门。 KIMI_MODEL_NAME 是 CLI 的仅 env 提
        # 供程序合成的触发器，KIMI_MODEL_API_KEY 是它配对的密钥 - 它们一起让 session/new
        #  通过虚假的凭据成功，这正是这个套件所需要的。 不使用该键设置名称会使 CLI 退出
        # ，因此两者都必须设置。
        #
        "KIMI_MODEL_API_KEY",
        # opencode 在此控制其 *catalogue*，而不仅仅是 auth-method
        # 选择：未经身份验证，``session/new`` 仅宣传免费
        # 层并且实时 set_config_option 调用拒绝 available_models 的 REST。 语法上存在的
        # 密钥足以提供持有密钥的用户所看到的内容（已验证：7 个模型选项 -> 90）。
        #
        "OPENCODE_API_KEY",
    ):
        monkeypatch.setenv(var, _BOGUS_KEY)
    monkeypatch.setenv("KIMI_MODEL_NAME", "kimi-k2.7-code")
    for var in (
        "CLAUDE_CODE_OAUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "OPENAI_BASE_URL",
        "GEMINI_BASE_URL",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "CODEX_HOME",
        "CLAUDE_CONFIG_DIR",
        "KIMI_API_KEY",
        "KIMI_BASE_URL",
        "KIMI_CODE_HOME",
        "KIMI_MODEL_BASE_URL",
        "OPENCODE_CONFIG_DIR",
        "OPENCODE_CONFIG",
        "OPENCODE_CONFIG_CONTENT",
        # 按值携带整个开放代码身份验证存储，因此环境会将主机凭据偷运到无凭据的探测器中。
        #
        "OPENCODE_AUTH_CONTENT",
    ):
        monkeypatch.delenv(var, raising=False)


def _spy(monkeypatch: pytest.MonkeyPatch, obj: Any, name: str) -> dict[str, Any]:
    """包装 ``obj`` 的异步属性来记录其 args/return，而
    仍在呼吁真正的实施。"""
    original = getattr(obj, name)
    captured: dict[str, Any] = {}

    async def _wrapped(*args, **kwargs):
        result = await original(*args, **kwargs)
        captured["args"] = args
        captured["kwargs"] = kwargs
        captured["result"] = result
        return result

    monkeypatch.setattr(obj, name, _wrapped)
    return captured


def _launch(agent: ACPAgent, tmp_path: Path) -> ConversationState:
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    state = ConversationState.create(
        id=uuid.uuid4(),
        agent=agent,
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
    )
    agent._executor = AsyncExecutor()
    agent._start_acp_server(state)
    return state


@requires_npx
@pytest.mark.parametrize("provider_key", list(ACP_PROVIDERS))
def test_acp_conformance_probe(
    provider_key: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = ACP_PROVIDERS[provider_key]
    _skip_if_node_below_floor(provider_key)
    _isolate_env(monkeypatch, tmp_path)

    init_captured = _spy(monkeypatch, ClientSideConnection, "initialize")
    auth_method_calls: list[tuple[list[Any], str | None]] = []
    original_select = _select_auth_method

    def _spy_select_auth_method(auth_methods, env):
        picked = original_select(auth_methods, env)
        auth_method_calls.append((list(auth_methods), picked))
        return picked

    monkeypatch.setattr(
        "openhands.sdk.agent.acp_agent._select_auth_method", _spy_select_auth_method
    )

    agent = ACPAgent(
        acp_command=list(provider.default_command),
        acp_server=provider.key,
        acp_isolate_data_dir=True,
        acp_model=provider.default_model,
    )
    start = time.monotonic()
    try:
        _launch(agent, tmp_path)
        cold_start = time.monotonic() - start

        init_response = init_captured["result"]
        print(
            f"[acp-conformance] provider={provider.key} "
            f"cold_start={cold_start:.2f}s "
            f"protocol_version={init_response.protocol_version}"
        )
        assert 0 < init_response.protocol_version < 65536

        # agent_name 匹配 agent_name_patterns。
        assert agent.agent_name, "server did not report an agent name"
        lowered_name = agent.agent_name.lower()
        assert any(pat in lowered_name for pat in provider.agent_name_patterns), (
            f"agent_name={agent.agent_name!r} does not match any pattern in "
            f"{provider.agent_name_patterns!r} (upstream renamed the agent?)"
        )

        # agent_version 等于引脚。
        pinned_version = ACP_INSTALL_CATALOG[provider.key].packages[0].version
        assert agent.agent_version == pinned_version, (
            f"agent_version={agent.agent_version!r} != pinned {pinned_version!r} — "
            "npx resolved a different version than default_command pins"
        )

        # authMethods 包含 _select_auth_method 选择的内容。 一些提供商（如claude-code，
        # 见#4830的基线）根本不进行身份验证握手，因此_select_auth_method从不被调用——只有
        # 在服务器实际提供了方法时才进行断言。
        #
        offered_ids = {m.id for m in init_response.auth_methods or []}
        if offered_ids:
            assert auth_method_calls, (
                f"server offered authMethods {sorted(offered_ids)!r} but "
                "_select_auth_method was never invoked"
            )
            _, picked_method_id = auth_method_calls[0]
            if picked_method_id is not None:
                assert picked_method_id in offered_ids, (
                    f"_select_auth_method picked {picked_method_id!r}, not "
                    f"present in the server's own authMethods "
                    f"{sorted(offered_ids)!r}"
                )

        # set_session_mode(default_session_mode) 隐式成功：在 _start_acp_server 内部引发
        # 拒绝，并且 _launch 会在此行之前传播。
        #

        # 该会话通告了 *some* 模型选择机制，符合 supports_set_session_model 存在的前提。
        #
        if provider.supports_set_session_model:
            assert agent._available_models is not None, (
                f"provider={provider.key} claims supports_set_session_model "
                "but the session response carried neither configOptions nor "
                "the models capability"
            )

        # 模型按要求读回。
        if provider.default_model:
            assert agent.current_model_id == provider.default_model, (
                f"requested default_model={provider.default_model!r} but the "
                f"live session reports current_model_id={agent.current_model_id!r} "
                "(the id may no longer be accepted — see the model-acceptance "
                "probe below)"
            )

        # 会话中set_model在supports_runtime_model_switch时工作。
        if provider.supports_runtime_model_switch:
            candidates = [
                m.id
                for m in provider.available_models
                if m.id != agent.current_model_id
            ]
            if candidates:
                target = candidates[0]
                agent.set_acp_model(target)
                assert agent.current_model_id == target, (
                    f"set_acp_model({target!r}) reported success but "
                    f"current_model_id is {agent.current_model_id!r}"
                )

        # 模型接受度探针 (#4830 P0-2): 每个经过 curated 的 available_models id 和
        # default_model 必须是 *accepted* 通过实时协议调用，而不是仅仅出现在我们的精选列
        # 表中。
        #
        session_id = agent._session_id
        conn = agent._conn
        assert session_id is not None
        assert conn is not None
        candidate_ids = list(
            dict.fromkeys(
                [m.id for m in provider.available_models]
                + ([provider.default_model] if provider.default_model else [])
            )
        )
        rejected: dict[str, str] = {}
        for model_id in candidate_ids:
            try:
                agent._executor.run_async(
                    _apply_acp_model(
                        conn,
                        session_id,
                        model_id,
                        agent_name=agent.agent_name,
                        via_config_option=agent._model_via_config_option,
                    ),
                    timeout=_MODEL_CALL_TIMEOUT,
                )
            except (ACPRequestError, ValueError) as exc:
                rejected[model_id] = str(exc)
        assert not rejected, (
            f"provider={provider.key} rejected curated model id(s) via the "
            f"live protocol call (dead catalog entries — fix _CODEX_MODELS / "
            f"_GEMINI_MODELS / _CLAUDE_MODELS or default_model in "
            f"acp_providers.py): {rejected}"
        )
    finally:
        agent.close()
