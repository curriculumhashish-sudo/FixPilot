import os
import shlex
import subprocess
import sys
import threading
from collections.abc import Mapping
from typing import Final

from openhands.sdk.logger import get_logger
from openhands.sdk.utils.redact import redact_text_secrets


logger = get_logger(__name__)


# SDK/服务器需要凭据，而不是智能体-运行子进程。
_SENSITIVE_ENV_VARS = frozenset(
    {
        "SESSION_API_KEY",
        "OH_SECRET_KEY",
        "LMNR_PROJECT_API_KEY",
        "OTEL_HEADERS",
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
    }
)

# 会话密钥也作为索引列表 ``OH_SESSION_API_KEYS_0`` 提供，
# ``OH_SESSION_API_KEYS_1``, ... (V1). 按前缀剥离每个槽，因此重命名或添加的旋转键无法默
# 默地重新公开凭据到子进程。
#
_SENSITIVE_ENV_PREFIXES: tuple[str, ...] = ("OH_SESSION_API_KEYS_",)
_AI_AGENT_ENV_VAR: Final[str] = "AI_AGENT"


def sanitized_env(
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """返回 *env* 的 sanitized 值的副本。

    基于 PyInstaller 的二进制文件重写 ``LD_LIBRARY_PATH``，因此他们的供应库获胜。 该
    函数恢复原始值，以便子进程不会使用它们。

    敏感的环境变量 (e.g., ``SESSION_API_KEY``) 被剥离，以防止 LLM 驱动的智能体通过终
    端命令访问凭据。

    ``AI_AGENT`` 默认为 ``openhands``，因此下游工具可以选择智能体友好的输出，而无需依
    赖于特定于产品的启发式方法。
    """

    base_env: dict[str, str]
    if env is None:
        base_env = dict(os.environ)
    else:
        base_env = dict(env)

    # 剥离敏感环境变量以防止通过 bash 命令访问智能体
    for key in _SENSITIVE_ENV_VARS:
        base_env.pop(key, None)

    # 剥离索引/前缀凭据插槽 (e.g. OH_SESSION_API_KEYS_0..N).
    for key in [
        k
        for k in base_env
        if any(k.startswith(prefix) for prefix in _SENSITIVE_ENV_PREFIXES)
    ]:
        base_env.pop(key, None)

    if not base_env.get(_AI_AGENT_ENV_VAR, "").strip():
        base_env[_AI_AGENT_ENV_VAR] = "openhands"

    if "LD_LIBRARY_PATH_ORIG" in base_env:
        origin = base_env["LD_LIBRARY_PATH_ORIG"]
        if origin:
            base_env["LD_LIBRARY_PATH"] = origin
        else:
            base_env.pop("LD_LIBRARY_PATH", None)
    return base_env


def execute_command(
    cmd: list[str] | str,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    timeout: float | None = None,
    print_output: bool = True,
) -> subprocess.CompletedProcess:
    # 对于字符串命令，使用 shell=True 正确处理 shell 操作符
    if isinstance(cmd, str):
        cmd_to_run = cmd
        use_shell = True
        cmd_str = cmd
    else:
        cmd_to_run = cmd
        use_shell = False
        cmd_str = " ".join(shlex.quote(c) for c in cmd)

    # 使用敏感值记录命令已脱敏
    logger.info("$ %s", redact_text_secrets(cmd_str))

    proc = subprocess.Popen(
        cmd_to_run,
        cwd=cwd,
        env=sanitized_env(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        shell=use_shell,
    )
    if proc is None:
        raise RuntimeError("Failed to start process")

    # 逐行读取，回显到父级 stdout/stderr
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    if proc.stdout is None or proc.stderr is None:
        raise RuntimeError("Failed to capture stdout/stderr")

    def read_stream(stream, lines, output_stream):
        try:
            for line in stream:
                if print_output:
                    output_stream.write(line)
                    output_stream.flush()
                lines.append(line)
        except Exception as e:
            logger.error(f"Failed to read stream: {e}")

    # 同时读取 stdout 和 stderr 以避免死锁
    stdout_thread = threading.Thread(
        target=read_stream, args=(proc.stdout, stdout_lines, sys.stdout)
    )
    stderr_thread = threading.Thread(
        target=read_stream, args=(proc.stderr, stderr_lines, sys.stderr)
    )

    stdout_thread.start()
    stderr_thread.start()

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout_thread.join()
        stderr_thread.join()
        return subprocess.CompletedProcess(
            cmd_to_run,
            -1,  # 用 -1 退出代码指示超时
            "".join(stdout_lines),
            "".join(stderr_lines),
        )

    stdout_thread.join(timeout=timeout)
    stderr_thread.join(timeout=timeout)

    return subprocess.CompletedProcess(
        cmd_to_run,
        proc.returncode,
        "".join(stdout_lines),
        "".join(stderr_lines),
    )
