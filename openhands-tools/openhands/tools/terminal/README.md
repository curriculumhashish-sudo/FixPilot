<a id="terminal-tool"></a>

# 终端工具

终端工具提供了一个持久的 shell 会话，用于在 OpenHands SDK 中执行 bash 命令。

<a id="features"></a>

## 特点

- **持久会话**：环境变量、虚拟环境和命令之间的工作目录持久化
- **多后端支持**：自动检测并使用tmux（如果可用），回退到基于子进程的PTY
- **可配置 shell**：支持自定义 shell 二进制文件（在 Nix、macOS 或自定义环境中有用）
- **客户端配置的环境**：添加SDK提供的会话环境变量，而不将它们公开为工具调用参数
- **长时间运行命令支持**：使用软超时和中断功能处理命令
- **终端重置**：能够在终端会话无响应时重置终端会话

<a id="shell-configuration"></a>

## 外壳配置

默认情况下，终端工具会自动检测 PATH 中的 bash（如 `#!/usr/bin/env bash`）。 您可以选择提供显式 shell 路径：

<a id="using-the-shell_path-parameter"></a>

### 使用 `shell_path` 参数

```python
from openhands.sdk import Conversation
from openhands.tools.terminal.definition import TerminalTool

# 创建对话
conversation = Conversation()

# 使用自定义 shell 路径创建终端
tools = TerminalTool.create(
    conv_state=conversation.state,
    terminal_type="subprocess",
    shell_path="/usr/local/bin/bash"
)
```

<a id="auto-detection-default"></a>

### 自动检测（默认）

如果未提供明确的 `shell_path`，该工具会使用 `which bash` 的等效项自动在 PATH 中查找 bash。 它的工作原理与 `#!/usr/bin/env bash` 类似，并且可以跨不同系统移植。

如果在 PATH 中找不到 bash，该工具将引发一个明显的错误，要求您提供显式的 `shell_path`。

<a id="environment-configuration"></a>

## 环境配置

SDK客户端在创建终端工具时可以提供额外的环境变量。 这些值将与清理后的进程环境合并，并应用于终端会话，直到重置或关闭为止。 他们不属于
`TerminalAction` 并且未暴露在面向模型的工具模式中。

```python
from openhands.sdk import Conversation
from openhands.tools.terminal.definition import TerminalTool

conversation = Conversation()
tools = TerminalTool.create(
    conv_state=conversation.state,
    env={
        "UV_INDEX_URL": "https://example.internal/simple",
        "UV_CACHE_DIR": "/workspace/.cache/uv",
    },
)
```

通过 `env` 传递的原始机密值成为会话范围的环境变量。 当您需要命令范围的机密注入行为时，请使用 SDK 机密注册表。

终端进程运行在  Agent Server's CPU 优先级高 CPU- 重命令不会让它饿死： `taskpolicy -c utility` 在 macOS, `nice -n 10` 在 Linux 和 Windows 的正常优先级以下。 套装
`OH_TERMINAL_PROCESS_PRIORITY=none`在服务器或终端环境中保持服务器的优先级，e.g。 对于基准测试。

<a id="usage-examples"></a>

## 使用示例

<a id="basic-usage"></a>

### 基本用法

```python
from openhands.sdk import Conversation
from openhands.tools.terminal.definition import TerminalTool, TerminalAction

conversation = Conversation()
tools = TerminalTool.create(conv_state=conversation.state)
terminal = tools[0]

# 执行命令
action = TerminalAction(command="echo 'Hello, World!'")
result = terminal.executor(action)
print(result.text)
```

**注：**`TerminalAction`和`TerminalObservation`取代了已弃用`ExecuteBashAction`和`ExecuteBashObservation`（在1.5.0版本中将被删除）。

<a id="with-custom-shell-on-nixmacos"></a>

### 在 Nix/macOS 上使用自定义 Shell

```python
import shutil
from openhands.sdk import Conversation
from openhands.tools.terminal.definition import TerminalTool

conversation = Conversation()

# 显式指定 bash 路径（如果 bash 位于非标准位置，则很有用）
bash_path = shutil.which("bash")
if not bash_path:
    raise RuntimeError("bash not found in PATH")

tools = TerminalTool.create(
    conv_state=conversation.state,
    terminal_type="subprocess",
    shell_path=bash_path
)
```

<a id="terminal-types"></a>

## 终端类型

该工具支持两种后端类型：

- **tmux**：使用 tmux 进行终端会话管理（可用时首选）
- **子进程**：使用 Python 子进程和 PTY 进行终端仿真 (回退方案)

您可以使用 `terminal_type` 参数强制指定类型：

```python
tools = TerminalTool.create(
    conv_state=conversation.state,
    terminal_type="subprocess"  # 或“tmux”
)
```

<a id="advanced-configuration"></a>

## 高级配置

<a id="custom-timeout"></a>

### 定制超时

```python
tools = TerminalTool.create(
    conv_state=conversation.state,
    no_change_timeout_seconds=60  # 等待 60 秒而不是默认的 10 秒
)
```

<a id="username"></a>

### 用户名

```python
tools = TerminalTool.create(
    conv_state=conversation.state,
    username="myuser"
)
```

<a id="troubleshooting"></a>

## 故障排除

<a id="bash-not-found-in-path"></a>

### 在 PATH 中未找到 Bash

如果您看到类似以下的错误：
```
RuntimeError: Could not find bash in PATH
```

这意味着 bash 在您的系统 PATH 中不可用。 解决方案：

1. 确保 bash 已安装并位于您的 PATH 中：
   ```bash
   which bash  # 应该返回类似 /usr/bin/bash 的路径
   ```

2. 如果 bash 已安装但不在 PATH 中，则在创建工具时传递显式路径：
   ```python
   tools = TerminalTool.create(
       conv_state=conversation.state,
       shell_path="/usr/local/bin/bash"
   )
   ```

<a id="shell-not-executable-error"></a>

### Shell 无法执行错误

如果您看到：
```
RuntimeError: Shell binary is not executable: /path/to/bash
```

检查文件权限：
```bash
ls -l /path/to/bash
chmod +x /path/to/bash  # 如果需要的话
```

<a id="notes"></a>

## 注释

- `shell_path`配置仅影响子进程终端类型； tmux 终端将使用 tmux 配置使用的任何 shell
- shell 必须与 bash 兼容才能正常运行
- 重置时，终端会话将保留最初配置的 shell 路径和客户端环境
