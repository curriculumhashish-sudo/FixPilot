"""共享测试夹具用于遥测测试。

将 ``test_settings_router.py`` 使用的持久化-dir 隔离与遥测接收器单例的重置相结合，因
此没有测试可以观察另一个进程的状态。
"""

import os
import tempfile
from base64 import urlsafe_b64encode
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from openhands.agent_server.config import Config, TelemetryExporterKind, TelemetrySpec
from openhands.agent_server.persistence.store import reset_stores
from openhands.agent_server.telemetry import reset_telemetry_sink
from openhands.agent_server.telemetry.policy import (
    CONSENT_ENV,
    CONSENT_MODE_ENV,
    DO_NOT_TRACK_ENV,
)


@pytest.fixture(autouse=True)
def _clean_telemetry_env(monkeypatch):
    """确保开发人员自己的 DO_NOT_TRACK 无法翻转测试结果。"""
    monkeypatch.delenv(DO_NOT_TRACK_ENV, raising=False)
    monkeypatch.delenv(CONSENT_ENV, raising=False)
    monkeypatch.delenv(CONSENT_MODE_ENV, raising=False)
    monkeypatch.delenv("OH_TELEMETRY", raising=False)


@pytest.fixture(autouse=True)
def _reset_sink():
    reset_telemetry_sink()
    yield
    reset_telemetry_sink()


@pytest.fixture
def temp_persistence_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        reset_stores()
        old_val = os.environ.get("OH_PERSISTENCE_DIR")
        os.environ["OH_PERSISTENCE_DIR"] = tmpdir
        yield Path(tmpdir)
        reset_stores()
        if old_val is not None:
            os.environ["OH_PERSISTENCE_DIR"] = old_val
        else:
            os.environ.pop("OH_PERSISTENCE_DIR", None)


@pytest.fixture
def secret_key() -> str:
    return urlsafe_b64encode(b"a" * 32).decode("ascii")


@pytest.fixture
def config_factory(temp_persistence_dir, secret_key):
    def _factory(
        exporter: TelemetryExporterKind = "none", **telemetry_kwargs: Any
    ) -> Config:
        return Config(
            static_files_path=None,
            session_api_keys=[],
            secret_key=SecretStr(secret_key),
            telemetry=TelemetrySpec(exporter=exporter, **telemetry_kwargs),
        )

    return _factory
