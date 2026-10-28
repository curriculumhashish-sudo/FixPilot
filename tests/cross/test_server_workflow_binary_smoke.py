"""``server.yml`` 中智能体-服务器二进制冒烟测试的防护。

这些断言是故意用文本的：Harness 是 Bash，只在运行 GitHub 动作，所以不变量那可能是脚本
的形状，而不是任何其他东西，导致Windows任务变得不稳 Pyt
hon 行为。
"""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "server.yml"


def _smoke_step() -> str:
    """返回 ``--extra-python-path`` 冒烟测试步骤的主体。"""
    workflow = SERVER_WORKFLOW.read_text(encoding="utf-8")
    marker = "- name: Test --extra-python-path custom tool import"
    assert marker in workflow, f"{SERVER_WORKFLOW}: smoke-test step is missing"
    step = workflow.partition(marker)[2]
    # 在下一步停止，以便断言无法匹配不相关的脚本文本。
    return step.partition("- name:")[0]


def test_startup_wait_is_not_a_tight_fixed_cap() -> None:
    """PyInstaller onefile 二进制文件在第一次运行时自行解压； 感冒或
    仅加载的 Windows 运行程序就超过了旧的 45 秒上限，因此健康的服务器被报告为故障。
    等待必须既慷慨又可重写，而不是手动调整的常量。
    """
    step = _smoke_step()

    assert "BINARY_STARTUP_TIMEOUT_SECONDS" in step
    assert 'STARTUP_TIMEOUT_SECONDS="${BINARY_STARTUP_TIMEOUT_SECONDS:-' in step
    default = int(step.split("BINARY_STARTUP_TIMEOUT_SECONDS:-", 1)[1].split("}")[0])
    assert default >= 300, (
        "default startup timeout must tolerate slow first-run extraction; "
        f"got {default}s"
    )
    assert "${3:-45}" not in step, "the old fixed 45s cap should be gone"


def test_wait_for_log_takes_the_pid_and_fails_fast() -> None:
    """在进程已经死掉之后等待完整的超时只是燃烧
    跑步分钟并隐藏真正的原因，因此等待必须能够观察活跃度并说出它达到了哪个条件。
    """
    step = _smoke_step()

    assert "local pid=$3" in step
    assert 'kill -0 "$pid"' in step
    assert "exited before" in step
    assert "timed out after" in step
    for pid_var in ("NEG_PID", "POS_PID", "CLI_PID"):
        assert f'"${pid_var}"' in step, f"wait_for_log should be passed {pid_var}"


def test_failed_wait_dumps_the_log_even_when_empty() -> None:
    """`cat` 在空日志中打印了什么，这导致了缓慢启动
    失败看起来像是 CI 输出中缺少日志错误。
    """
    step = _smoke_step()

    assert "dump_log()" in step
    assert "(no output captured from the binary)" in step
    assert not any(
        line.strip().startswith("cat ") and "_test.log" in line
        for line in step.splitlines()
    ), "failure paths should call dump_log rather than a bare cat"


def test_windows_process_teardown_kills_the_whole_tree() -> None:
    """onefile 引导加载程序在子进程中运行服务器，因此杀死
    只有引导加载程序可以让该子进程保留端口。 因此，Windows 必须终止树，并且调用不能让
     MSYS 重写
    `/F /T /PID` 切换到路径。
    """
    step = _smoke_step()

    assert "MSYS_NO_PATHCONV=1 taskkill /F /T /PID" in step
    # 树杀戮必须仅限于 Windows； Unix 运行程序没有任务终止，应该保持简单的信号路径。
    #
    end_of_block = "\n                  }"
    teardown = step.partition("stop_process() {")[2].partition(end_of_block)[0]
    assert 'RUNNER_OS:-}" == "Windows"' in teardown
    assert 'kill "$pid"' in teardown
