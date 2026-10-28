"""每个呼叫站点的覆盖范围为 ``OH_PERSISTENCE_DIR``。

所有读写用户级 ``~/.openhands`` 状态的模块都必须通过：func:
`openhands.sdk.utils.path.get_user_persistence_dir` 进行路由，这样，指向持久卷的临时
沙盒
``OH_PERSISTENCE_DIR`` 保持数据。 该模块断言该合同位于
*every* 调用站点，而不是单独信任共享助手，该助手负责保护
反对未来的编辑重新引入裸露的``Path.home() / ".openhands"``。

存在两种类型的调用站点：

* **导入时间常数** (e.g. ``_DEFAULT_PROFILE_DIR``）在首次导入模块时解析一次环境变量。
 它们在新的子进程中进行了验证，因此导入确实在测试
环境下发生，就像真实流程启动的方式一样。 这也可以防止模块状态在测试之间泄漏。
* **调用时函数**在每次调用时解析，并在API允许的地方通过真正的读/写在进程中执行。
"""

from __future__ import annotations

import json
import os
import site
import subprocess
import sys
import sysconfig
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest


def _import_roots() -> list[str]:
    """使 ``openhands`` + 其依赖项在子项中可导入的目录。

    覆盖子级中的 ``HOME`` 会将 Python 的每用户站点包移动到
    ``$HOME/.local/...``，两者都绕过可编辑安装
    ``.pth``注入查找器并隐藏第三方依赖项。 在父级（实数 ``HOME``）中解析，这些根都固
    定到 ``PYTHONPATH``。
    """
    repo_root = Path(__file__).resolve().parents[2]
    roots = [
        str(repo_root / pkg)
        for pkg in ("openhands-sdk", "openhands-tools", "openhands-agent-server")
    ]
    roots += list(sys.path)
    roots.append(site.getusersitepackages())
    roots.extend(site.getsitepackages() if hasattr(site, "getsitepackages") else [])
    roots.append(sysconfig.get_path("purelib"))
    seen: set[str] = set()
    ordered: list[str] = []
    for r in roots:
        if r and r not in seen and Path(r).exists():
            seen.add(r)
            ordered.append(r)
    return ordered


_IMPORT_ROOTS = _import_roots()


def _subprocess_env(**overrides: str) -> dict[str, str]:
    """Env 是一个子解释器，通过假``HOME``保持可导入性。"""
    env = dict(os.environ)
    env.update(overrides)
    env["OPENHANDS_SUPPRESS_BANNER"] = "1"
    existing = env.get("PYTHONPATH", "")
    parts = _IMPORT_ROOTS + ([existing] if existing else [])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


# --------------------------------------------------------------------------- #
# 导入时间常数 — 通过子进程导入验证。
# --------------------------------------------------------------------------- #

# 名称 -> （模块、属性、相对于持久化-root 的子路径）
# ``attribute`` 可以是通过“attr[i]”进入列表常量的索引。
_IMPORT_TIME_CALL_SITES: dict[str, tuple[str, str, str]] = {
    "llm_profile_store": (
        "openhands.sdk.llm.llm_profile_store",
        "_DEFAULT_PROFILE_DIR",
        "profiles",
    ),
    "agent_profile_store": (
        "openhands.sdk.profiles.agent_profile_store",
        "_DEFAULT_PROFILE_DIR",
        "agent-profiles",
    ),
    "skills_fetch_cache": (
        "openhands.sdk.skills.fetch",
        "DEFAULT_CACHE_DIR",
        "cache/skills",
    ),
    "skills_installed": (
        "openhands.sdk.skills.installed",
        "DEFAULT_INSTALLED_SKILLS_DIR",
        "skills/installed",
    ),
    "skills_user_dirs_skills": (
        "openhands.sdk.skills.skill",
        "USER_SKILLS_DIRS[1]",
        "skills",
    ),
    "skills_user_dirs_microagents": (
        "openhands.sdk.skills.skill",
        "USER_SKILLS_DIRS[2]",
        "microagents",
    ),
    "plugin_fetch_cache": (
        "openhands.sdk.plugin.fetch",
        "DEFAULT_CACHE_DIR",
        "cache/plugins",
    ),
    "plugin_source_cache": (
        "openhands.sdk.plugin.source",
        "DEFAULT_CACHE_DIR",
        "cache/git",
    ),
    "plugin_user_dirs": (
        "openhands.sdk.plugin.discovery",
        "USER_PLUGINS_DIRS[1]",
        "plugins",
    ),
    "plugin_installed": (
        "openhands.sdk.plugin.installed",
        "DEFAULT_INSTALLED_PLUGINS_DIR",
        "plugins/installed",
    ),
    "extensions_cache": (
        "openhands.sdk.extensions.installation.manager",
        "DEFAULT_CACHE_DIR",
        "cache/extensions",
    ),
    "agent_soul_path": (
        "openhands.sdk.agent.base",
        "_SOUL_PATH",
        "SOUL.md",
    ),
}

# 调用故意在持久化-dir 条目之前保留 ``~/.agents`` 条目的站点。 已验证仍然指向
# ``~/.agents``，无论
# ``OH_PERSISTENCE_DIR``.
_AGENTS_DIR_CALL_SITES: dict[str, tuple[str, str, str]] = {
    "skills_user_dirs_agents": (
        "openhands.sdk.skills.skill",
        "USER_SKILLS_DIRS[0]",
        ".agents/skills",
    ),
    "plugin_user_dirs_agents": (
        "openhands.sdk.plugin.discovery",
        "USER_PLUGINS_DIRS[0]",
        ".agents/plugins",
    ),
}


def _probe_constants_in_subprocess(env: dict[str, str]) -> dict[str, str]:
    """将每个调用站点的模块导入子进程中并返回其路径。

    在 ``env`` 下运行，因此导入时间分辨率为 ``OH_PERSISTENCE_DIR`` /
    ``HOME`` 的发生与实际进程启动时完全相同。
    """
    all_sites = {**_IMPORT_TIME_CALL_SITES, **_AGENTS_DIR_CALL_SITES}
    spec = {name: (mod, attr) for name, (mod, attr, _sub) in all_sites.items()}
    script = (
        "import json, importlib\n"
        f"spec = {spec!r}\n"
        "out = {}\n"
        "import os\n"
        "def resolve(module, attr):\n"
        "    if attr.endswith(']'):\n"
        "        base, index = attr[:-1].split('[')\n"
        "        return getattr(module, base)[int(index)]\n"
        "    return getattr(module, attr)\n"
        "for name, (mod, attr) in spec.items():\n"
        "    m = importlib.import_module(mod)\n"
        "    out[name] = os.fspath(resolve(m, attr))\n"
        "print(json.dumps(out))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    # 横幅/日志行转到 stderr； stdout 仅携带我们的 JSON 行。
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def constants_with_persistence_env() -> Iterator[dict[str, str]]:
    with tempfile.TemporaryDirectory() as tmpdir:
        home = str(Path(tmpdir) / "unused-home")
        env = _subprocess_env(OH_PERSISTENCE_DIR=tmpdir, HOME=home)
        paths = _probe_constants_in_subprocess(env)
        paths["__root__"] = tmpdir
        paths["HOME"] = home
        yield paths


@pytest.fixture(scope="module")
def constants_with_home_fallback() -> Iterator[dict[str, str]]:
    with tempfile.TemporaryDirectory() as tmpdir:
        env = _subprocess_env(HOME=tmpdir)
        env.pop("OH_PERSISTENCE_DIR", None)
        paths = _probe_constants_in_subprocess(env)
        paths["__root__"] = tmpdir
        yield paths


@pytest.mark.parametrize("name", sorted(_IMPORT_TIME_CALL_SITES))
def test_import_time_constant_honors_persistence_env(
    name: str, constants_with_persistence_env: dict[str, str]
) -> None:
    root = Path(constants_with_persistence_env["__root__"])
    _mod, _attr, subpath = _IMPORT_TIME_CALL_SITES[name]
    assert Path(constants_with_persistence_env[name]) == root / subpath


@pytest.mark.parametrize("name", sorted(_IMPORT_TIME_CALL_SITES))
def test_import_time_constant_falls_back_to_home(
    name: str, constants_with_home_fallback: dict[str, str]
) -> None:
    home = Path(constants_with_home_fallback["__root__"])
    _mod, _attr, subpath = _IMPORT_TIME_CALL_SITES[name]
    assert Path(constants_with_home_fallback[name]) == home / ".openhands" / subpath


@pytest.mark.parametrize("name", sorted(_AGENTS_DIR_CALL_SITES))
def test_agents_dir_call_sites_ignore_persistence_env(
    name: str, constants_with_persistence_env: dict[str, str]
) -> None:
    """即使设置了 env，``~/.agents`` 条目仍保留在 ``$HOME/.agents`` 上。"""
    _mod, _attr, subpath = _AGENTS_DIR_CALL_SITES[name]
    home = Path(constants_with_persistence_env["HOME"])
    resolved = Path(constants_with_persistence_env[name])
    # 锚定在 $HOME/.agents/...，从未重定向到持久化目录。
    assert resolved == home / subpath
    assert ".openhands" not in resolved.parts


# --------------------------------------------------------------------------- #
# 调用时函数——在进程中进行真实的读/写操作。
# --------------------------------------------------------------------------- #


@pytest.fixture
def persistence_dir(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """``OH_PERSISTENCE_DIR`` 指向调用时站点的干净临时目录。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("OH_PERSISTENCE_DIR", tmpdir)
        yield Path(tmpdir)


def test_credentials_dir_uses_persistence_dir(persistence_dir: Path) -> None:
    from openhands.sdk.llm.auth.credentials import get_credentials_dir

    assert get_credentials_dir() == persistence_dir / "auth"


def test_skills_cache_dir_uses_persistence_dir(persistence_dir: Path) -> None:
    from openhands.sdk.skills.utils import get_skills_cache_dir

    assert get_skills_cache_dir() == persistence_dir / "cache" / "skills"


def test_hook_config_reads_user_hooks_json(persistence_dir: Path) -> None:
    from openhands.sdk.hooks.config import HookConfig

    (persistence_dir / "hooks.json").write_text(
        json.dumps(
            {
                "pre_tool_use": [
                    {
                        "matcher": "*",
                        "hooks": [{"type": "command", "command": "echo hi"}],
                    }
                ]
            }
        )
    )
    # 没有本地挂钩的项目目录会强制进行用户级查找。
    with tempfile.TemporaryDirectory() as project:
        cfg = HookConfig.load(working_dir=project)
    assert cfg.pre_tool_use[0].hooks[0].command == "echo hi"


def test_load_user_agents_reads_persistence_dir(persistence_dir: Path) -> None:
    from openhands.sdk.subagent.load import load_user_agents

    agents_dir = persistence_dir / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: reviews code\n---\nBe a reviewer.\n"
    )
    names = {a.name for a in load_user_agents()}
    assert "reviewer" in names


def test_load_memory_reads_user_index(persistence_dir: Path) -> None:
    from openhands.sdk.context.memory import load_memory

    memory_dir = persistence_dir / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text("Remember: the launch code is 0000.")
    with tempfile.TemporaryDirectory() as project:
        combined = load_memory(working_dir=project)
    assert "the launch code is 0000." in (combined or "")


def test_prompt_jinja_cache_lives_in_persistence_dir(persistence_dir: Path) -> None:
    from openhands.sdk.agent import base
    from openhands.sdk.context.prompts import prompt as prompt_mod

    prompt_mod._get_env.cache_clear()
    try:
        prompt_mod._get_env(base._BUILTIN_PROMPT_DIR)
        assert (persistence_dir / "cache" / "jinja").is_dir()
    finally:
        prompt_mod._get_env.cache_clear()


def test_tom_consult_file_store_root(persistence_dir: Path) -> None:
    pytest.importorskip("tom_swe")
    from typing import cast

    from openhands.sdk.conversation.state import ConversationState
    from openhands.sdk.io import LocalFileStore
    from openhands.tools.tom_consult.definition import (
        SleeptimeComputeTool,
        TomConsultTool,
    )
    from openhands.tools.tom_consult.executor import TomConsultExecutor

    # ``create`` 忽略 ``conv_state``（状态在执行时传递），因此类型化的 ``None`` 可以在不
    # 构建完整状态对象的情况下保持 Pyright 满意。
    #
    conv_state = cast(ConversationState, None)
    for tool_cls in (TomConsultTool, SleeptimeComputeTool):
        tools = tool_cls.create(conv_state=conv_state)
        executor = tools[0].executor
        assert isinstance(executor, TomConsultExecutor)
        file_store = executor.file_store
        assert isinstance(file_store, LocalFileStore)
        assert file_store.root == str(persistence_dir)


def test_canvas_extensions_dir_uses_persistence_dir(persistence_dir: Path) -> None:
    from openhands.agent_server.canvas_extensions.installed import (
        get_installed_canvas_extensions_dir,
    )

    assert (
        get_installed_canvas_extensions_dir()
        == persistence_dir / "canvas-extensions" / "installed"
    )


def test_agent_server_profile_persistence_dir(persistence_dir: Path) -> None:
    from openhands.agent_server.persistence.store import _get_profile_persistence_dir

    assert _get_profile_persistence_dir() == persistence_dir


def test_default_llm_profile_store_survives_resume() -> None:
    """端到端：默认构造的存储在 HOME 擦除中持续存在。

    复制短暂的沙盒简历。 ``LLMProfileStore()``（无
    ``base_dir``) 使用导入时默认值，因此每次运行都在其自己的子进程中进行，以诚实地执
    行该解决方案。 运行 1 使用一次性写入 HOME； 然后删除
    HOME，并使用新的空 HOME 进行运行 2，该运行仍必须从 ``OH_PERSISTENCE_DIR`` 读回配
    置文件。
    """
    import shutil

    with (
        tempfile.TemporaryDirectory() as persist,
        tempfile.TemporaryDirectory() as home_root,
    ):
        home1 = Path(home_root) / "home1"
        home1.mkdir()

        write = (
            "from openhands.sdk.llm import LLM\n"
            "from openhands.sdk.llm.llm_profile_store import LLMProfileStore\n"
            "LLMProfileStore().save('prod', LLM(model='gpt-4o', usage_id='prod'))\n"
        )
        r1 = subprocess.run(
            [sys.executable, "-c", write],
            env=_subprocess_env(OH_PERSISTENCE_DIR=persist, HOME=str(home1)),
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert r1.returncode == 0, r1.stderr
        assert (Path(persist) / "profiles" / "prod.json").is_file()
        assert not (home1 / ".openhands").exists()

        # 恢复：摧毁短暂的HOME，手跑2个全新的空的。
        shutil.rmtree(home1)
        home2 = Path(home_root) / "home2"
        home2.mkdir()

        read = (
            "from openhands.sdk.llm.llm_profile_store import LLMProfileStore\n"
            "print(LLMProfileStore().load('prod').model)\n"
        )
        r2 = subprocess.run(
            [sys.executable, "-c", read],
            env=_subprocess_env(OH_PERSISTENCE_DIR=persist, HOME=str(home2)),
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert r2.returncode == 0, r2.stderr
        assert r2.stdout.strip().splitlines()[-1] == "gpt-4o"
