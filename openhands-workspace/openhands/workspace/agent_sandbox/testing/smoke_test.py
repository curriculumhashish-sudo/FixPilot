"""针对真实集群（无 LLM）对 AgentSandboxWorkspace 进行无钥匙烟雾测试。

无需 LLM：从热池中获取 Pod，运行命令，暂停/恢复，确认工作区状态在暂停后仍然存活。 针
对安全默认模板工作（无需更改网络策略），因为它永远不会离开 Pod 到达
LLM。

Prerequisites (see TESTING.md): 可通过 kubeconfig 访问的集群
安装了智能体-沙箱控制器和智能体-服务器 Pod 的温池。 然后：

    pip install openhands-workspace[agent-sandbox]
    python smoke_test.py

环境（可选）：
    AGENT_SANDBOX_WARMPOOL 暖池名称（默认：OpenHands-pool） AGENT_SANDBOX_NAMESPACE
    命名空间（默认：def
    ault）
"""

import os
import time

from openhands.workspace import AgentSandboxWorkspace


WARMPOOL = os.environ.get("AGENT_SANDBOX_WARMPOOL", "openhands-pool")
NAMESPACE = os.environ.get("AGENT_SANDBOX_NAMESPACE", "default")


def main() -> None:
    t0 = time.time()
    with AgentSandboxWorkspace(warmpool=WARMPOOL, namespace=NAMESPACE) as ws:
        print(f"claimed + connected in {time.time() - t0:.1f}s at {ws.host}")

        result = ws.execute_command("echo hello-from-pod && whoami && pwd && uname -m")
        assert result.exit_code == 0, result
        print("command output:\n" + result.stdout)

        # 写入文件，然后暂停并恢复沙箱。
        ws.execute_command("echo persisted-across-suspend > /workspace/marker.txt")
        print("pause() -> Suspended ...")
        ws.pause()
        time.sleep(3)
        print("resume() -> Running ...")
        ws.resume()

        # 对于持久卷，文件在恢复后仍然存在。
        out = ws.execute_command("cat /workspace/marker.txt")
        assert out.stdout.strip() == "persisted-across-suspend", out
        print(f"state survived suspend/resume: {out.stdout!r}")

    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
