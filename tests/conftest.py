"""通用测试测试夹具和实用程序。"""

import os
import re
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from openhands.sdk import Agent
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.io import InMemoryFileStore
from openhands.sdk.llm import LLM
from openhands.sdk.tool import ToolExecutor
from openhands.sdk.workspace import LocalWorkspace


REPO_ROOT = Path(__file__).resolve().parent.parent
TOKENIZER_FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "tokenizers"
QWEN3_TOKENIZER_CONFIG = (
    TOKENIZER_FIXTURES_DIR / "qwen3-4b-instruct-2507-tokenizer_config.json"
)

# 将 Agent Server 指向实时部署或对其进行身份验证的设置。 OpenHands 沙箱内的运行会从沙箱
# 继承它们。
#
_LIVE_DEPLOYMENT_ENV = re.compile(
    r"SESSION_API_KEY|OH_SESSION_API_KEYS_\d+|OH_WEBHOOKS(_\w+)?"
    r"|OH_CONVERSATIONS_PATH|OH_BASH_EVENTS_DIR|OH_INTERNAL_SERVER_URL"
    r"|OH_LLM_API_KEY_REFRESH_\w+"
)


def pytest_configure(config: pytest.Config) -> None:
    # 收集之前：某些模块在导入时读取智能体-服务器配置。
    for name in [n for n in os.environ if _LIVE_DEPLOYMENT_ENV.fullmatch(n)]:
        del os.environ[name]


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("examples")
    group.addoption(
        "--run-examples",
        action="store_true",
        default=False,
        help="Execute example scripts. Disabled by default for faster test runs.",
    )
    group.addoption(
        "--examples-results-dir",
        action="store",
        default=None,
        help=(
            "Directory to store per-example JSON results "
            "(defaults to .example-test-results)."
        ),
    )


@pytest.fixture(scope="session")
def examples_enabled(pytestconfig: pytest.Config) -> bool:
    return bool(pytestconfig.getoption("--run-examples"))


@pytest.fixture(scope="session")
def examples_results_dir(pytestconfig: pytest.Config) -> Path:
    configured = pytestconfig.getoption("--examples-results-dir")
    result_dir = (
        Path(configured)
        if configured is not None
        else REPO_ROOT / ".example-test-results"
    )
    result_dir.mkdir(parents=True, exist_ok=True)
    if not hasattr(pytestconfig, "workerinput"):
        for existing in result_dir.glob("*.json"):
            existing.unlink()
    return result_dir


@pytest.fixture(scope="session")
def tokenizer_fixtures_dir() -> Path:
    """获取分词器测试夹具目录路径。"""
    return TOKENIZER_FIXTURES_DIR


@pytest.fixture(scope="session")
def qwen3_tokenizer_config_path(tokenizer_fixtures_dir: Path) -> Path:
    """缓存的 Qwen3 tokenizer 配置的路径测试夹具。"""
    return tokenizer_fixtures_dir / "qwen3-4b-instruct-2507-tokenizer_config.json"


@pytest.fixture
def mock_llm():
    """创建标准模拟对象 LLM 实例进行测试。"""
    return LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )


@pytest.fixture
def mock_conversation_state(mock_llm, tmp_path):
    """创建用于测试的标准模拟对象 ConversationState。"""
    agent = Agent(llm=mock_llm)
    workspace = LocalWorkspace(working_dir=str(tmp_path))

    state = ConversationState(
        id=uuid.uuid4(),
        workspace=workspace,
        persistence_dir=str(tmp_path / ".state"),
        agent=agent,
    )

    # 为状态持久化设置文件存储
    state._fs = InMemoryFileStore()
    state._autosave_enabled = False

    return state


@pytest.fixture
def mock_tool():
    """创建一个模拟对象工具进行测试。"""

    class MockExecutor(ToolExecutor):
        def __call__(self, action, conversation=None):
            return MagicMock(output="mock output", metadata=MagicMock(exit_code=0))

    # 创建一个简单的模拟对象工具，无需复杂的依赖项
    mock_tool = MagicMock()
    mock_tool.name = "mock_tool"
    mock_tool.executor = MockExecutor()
    return mock_tool


def create_mock_litellm_response(
    content: str = "Test response",
    response_id: str = "test-id",
    model: str = "gpt-4o",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
    finish_reason: str = "stop",
):
    """用于创建结构正确的 LiteLLM 模拟对象响应的辅助函数。

    Args:
        content: 回复内容
        response_id: 唯一响应 ID
        model: 型号名称
        prompt_tokens: 提示词 token 数量
        completion_tokens: 完成数量 token
        finish_reason: 完成原因
    """
    from litellm.types.utils import (
        Choices,
        Message as LiteLLMMessage,
        ModelResponse,
        Usage,
    )

    # 创建正确的 LiteLLM 消息
    message = LiteLLMMessage(content=content, role="assistant")

    # 创造正确的选择
    choice = Choices(finish_reason=finish_reason, index=0, message=message)

    # 创建正确的用法
    usage = Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )

    # 创建适当的ModelResponse
    response = ModelResponse(
        id=response_id,
        choices=[choice],
        created=1234567890,
        model=model,
        object="chat.completion",
        usage=usage,
    )

    return response


@pytest.fixture(autouse=True)
def suppress_logging(monkeypatch):
    """在测试期间禁止记录以减少噪音。"""
    mock_logger = MagicMock()
    monkeypatch.setattr("openhands.sdk.llm.llm.logger", mock_logger)


@pytest.fixture(autouse=True)
def restore_observability_latch():
    """防止一个测试的跟踪设置改变每个后续测试的行为方式。

    ``should_enable_observability`` 将 ``True`` 缓存在模块全局中，并且不会重新检查，
    并且
    ``Laminar.shutdown()`` 不会清除它。 ``@observe`` 这个测试会把 lmnr 提升起来，因此
    ，它会让每个后续的构建都使用真实包装器，
    第一次调用时就这样做——这会悄悄地破坏那些触发懒加载构建的测试，只有当它们共享一个
    xdist 工作进程时才会这样做。
    """
    from openhands.sdk.observability import laminar

    previous = laminar._observability_enabled
    try:
        yield
    finally:
        laminar._observability_enabled = previous
