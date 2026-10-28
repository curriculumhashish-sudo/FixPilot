import os

import pytest

from openhands.agent_server.config import (
    V0_SESSION_API_KEY_ENV,
    V1_SESSION_API_KEY_ENV,
)
from openhands.agent_server.persistence import reset_stores


@pytest.fixture(autouse=True)
def isolate_session_api_key_env():
    """将会话密钥变量恢复为每次测试找到它们的方式。

    服务器在启动或初始化时 (``export_session_api_key``) 将其有效密钥导出到
    ``OH_SESSION_API_KEYS_0``。 直接驱动
    那些路径的测试，或者调用辅助函数，否则会将密钥留在进程环境中，之后从默认配置构建
    的每个后续应用程序都会要求它。 ``monkeypatch.delenv`` 对于不
    存在的变量没有记录任何内容，因此这是一个显式快照。
    """
    names = (V0_SESSION_API_KEY_ENV, V1_SESSION_API_KEY_ENV)
    saved = {name: os.environ.get(name) for name in names}
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@pytest.fixture(autouse=True)
def isolate_persistence_dir(tmp_path, monkeypatch):
    """让开发人员的真实 ``~/.openhands`` 远离每次测试。

    ``_start_conversation`` 在每次启动时读取设置存储，而不仅仅是 ``agent_profile_id``
     一次，并且
    ``get_settings_store`` 回退到
    当 ``OH_PERSISTENCE_DIR`` 未设置时为 ``~/.openhands``。 构建的测试
    ``ConversationService`` 直接从不初始化单例，因此如果没有这个，它们将拾取主机上恰
    好存在的任何 settings.json 并
    pass or fail depending on the machine.
    """
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(tmp_path / ".openhands"))
    # 单例获取器解析 ``OH_PERSISTENCE_DIR`` 每条呼叫，但三 SDK 在导入时，模块常量会被冻
    # 结为默认值，因此在导入模块后，它会忽略上述环境变量（这里总是会导入的）。 也固定它
    # 们，或者没有明确构建的商店
    # ``base_dir``仍然落在开发商的真实``~/.openhands``中。
    from openhands.sdk.llm import llm_profile_store
    from openhands.sdk.profiles import agent_profile_store
    from openhands.sdk.skills import installed as installed_skills

    persistence_dir = tmp_path / ".openhands"
    monkeypatch.setattr(
        llm_profile_store, "_DEFAULT_PROFILE_DIR", persistence_dir / "profiles"
    )
    monkeypatch.setattr(
        agent_profile_store, "_DEFAULT_PROFILE_DIR", persistence_dir / "agent-profiles"
    )
    monkeypatch.setattr(
        installed_skills,
        "DEFAULT_INSTALLED_SKILLS_DIR",
        persistence_dir / "skills" / "installed",
    )
    reset_stores()
    try:
        yield
    finally:
        reset_stores()
