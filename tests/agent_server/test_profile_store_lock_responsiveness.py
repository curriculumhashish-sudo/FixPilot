"""在配置文件/连接存储锁上等待的请求不得停止服务器。

下面的四个存储采用 ``filelock.FileLock``，其 ``acquire`` 通过阻塞睡眠（最多 30 秒）进
行轮询。 它们的路由处理程序必须运行等待事件循环
，因此 ``/alive`` 会在另一个进程持有锁时继续应答。 回归测试问题#5632。
"""

import asyncio
import threading
import time
from pathlib import Path

import httpx
import pytest
from filelock import FileLock

from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config
from openhands.agent_server.persistence import reset_stores


# 保留的锁的上限：如果处理程序阻塞事件循环，则没有任何内容可以释放锁进行测试，因此计时器
# 会在这么长的时间后释放它。
#
_SAFETY_RELEASE_SECONDS = 5.0
_ALIVE_BUDGET_SECONDS = 2.0


@pytest.mark.parametrize(
    ("lock_file", "method", "path", "json_body", "expected_status"),
    [
        pytest.param(
            "profiles/.profiles.lock",
            "POST",
            "/api/profiles/qa-busy",
            {"llm": {"model": "openai/qa-busy"}},
            201,
            id="llm-profiles",
        ),
        pytest.param(
            "agent-profiles/.agent-profiles.lock",
            "GET",
            "/api/agent-profiles/qa-busy",
            None,
            404,
            id="agent-profiles",
        ),
        pytest.param(
            "agent-profiles/.agent-profiles.lock",
            "POST",
            "/api/agent-profiles/qa-busy/materialize",
            None,
            404,
            id="agent-profiles-materialize",
        ),
        pytest.param(
            "meta-profiles/.meta-profiles.lock",
            "POST",
            "/api/meta-profiles/qa-busy",
            {
                "classifier_model": "qa-classifier",
                "classes": [{"description": "UI", "model": "qa-model"}],
            },
            201,
            id="meta-profiles",
        ),
        pytest.param(
            "provider-connections/.provider-connections.lock",
            "GET",
            "/api/llm/provider-connections",
            None,
            200,
            id="provider-connections",
        ),
    ],
)
async def test_alive_answers_while_store_request_waits_for_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lock_file: str,
    method: str,
    path: str,
    json_body: dict | None,
    expected_status: int,
) -> None:
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(tmp_path))
    reset_stores()
    app = create_app(
        Config(static_files_path=None, session_api_keys=[], secret_key=None)
    )

    lock_path = tmp_path / lock_file
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # 单独的 FileLock 实例代表保存存储锁的另一个进程。 ``thread_local=False`` 让安全定时
    # 器释放它。
    #
    held = FileLock(lock_path, thread_local=False)
    held.acquire()
    safety = threading.Timer(_SAFETY_RELEASE_SECONDS, held.release)
    safety.start()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            waiting = asyncio.create_task(
                client.request(method, path, json=json_body, timeout=60)
            )
            started = time.monotonic()
            # 让存储请求开始并在锁上阻塞。
            await asyncio.sleep(0.3)
            alive = await client.get("/alive", timeout=60)
            elapsed = time.monotonic() - started

            assert alive.status_code == 200
            assert elapsed < _ALIVE_BUDGET_SECONDS, (
                f"/alive took {elapsed:.1f}s while a store request waited "
                "for the lock: the wait is blocking the event loop"
            )
            # 存储请求实际上仍在等待锁。
            assert not waiting.done()

            safety.cancel()
            held.release()
            response = await asyncio.wait_for(waiting, timeout=30)
            assert response.status_code == expected_status, response.text
    finally:
        safety.cancel()
        if held.is_locked:
            held.release(force=True)
        reset_stores()
