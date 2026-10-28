"""测试 SOCKS 代理支持 (OpenHands/OpenHands-CLI#632)。

当用户设置了 SOCKS 代理环境变量 (e.g. all_proxy=socks5://...)，httpx需要socksio包来处
理SOCKS代理连接。 如果没有它，导
入 LiteLLM（在模块级别创建 httpx.Client）会在使用 ImportError 启动时崩溃。
"""

import os
import subprocess
import sys


def test_socksio_is_installed():
    """验证socksio 是否作为httpx[socks] 的一部分安装。"""
    import socksio  # noqa: F401


def test_httpx_socks_extra_available():
    """验证当设置 SOCKS 代理环境变量时 httpx 可以创建客户端。"""
    import httpx

    # 模拟 SOCKS 代理环境变量； 客户端构造函数不应该为socksio引发ImportError。 我们使用
    # 不可路由的地址，因此不会尝试真正的连接。
    #
    client = httpx.Client(proxy="socks5://127.0.0.1:19999")
    client.close()


def test_import_with_socks_proxy_env():
    """确保all_proxy设置为socks5时可以导入并使用httpx。"""
    env = os.environ.copy()
    env["all_proxy"] = "socks5://127.0.0.1:19999"
    env["https_proxy"] = "socks5://127.0.0.1:19999"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import httpx; c = httpx.Client(); c.close(); print('ok')",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, (
        f"Import failed with SOCKS proxy env vars set:\n{result.stderr}"
    )
    assert "ok" in result.stdout
