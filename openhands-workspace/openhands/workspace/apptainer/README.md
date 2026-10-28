<a id="apptainer-workspace"></a>

# Apptainer 工作区

`ApptainerWorkspace` 使用 [Apptainer](https://apptainer.org/)（以前称为 Singularity）提供基于容器的工作区，不需要 root 访问权限。 这使其成为 HPC 和 Docker 可能不可用或不允许的共享计算环境的理想选择。

注意：此类仅适用于**预构建图像**。 它不支持从基础镜像即时构建镜像。 对于使用 Docker 进行即时构建，请改用 `DockerDevWorkspace`。

<a id="why-apptainer"></a>

## 为什么是Apptainer？

- **不需要 root **：与 Docker 不同，Apptainer 不需要 root/sudo 权限
- **HPC-友好**：专为高性能计算环境而设计
- **安全**：更好的多用户系统安全模型
- **兼容**：可以使用预构建的Docker图像

<a id="prerequisites"></a>

## 先决条件

按照[官方快速入门指南](https://apptainer.org/docs/user/main/quick_start.html)安装Apptainer。

在 Ubuntu/Debian 上：
```bash
sudo apt-get update
sudo apt-get install -y apptainer
```

在 CentOS/RHEL 上：
```bash
sudo yum install -y apptainer
```

<a id="usage"></a>

## 用途

<a id="option-1-use-pre-built-agent-server-image-recommended"></a>

### 选项 1：使用预构建的 Agent Server 图像（推荐）

```python
from openhands.workspace import ApptainerWorkspace

# 使用预先构建的 Agent Server 图像
with ApptainerWorkspace(
    server_image="ghcr.io/openhands/agent-server:latest-python",
    host_port=8010,
) as workspace:
    result = workspace.execute_command("echo 'Hello from Apptainer!'")
    print(result.stdout)
```

<a id="option-2-use-existing-sif-file"></a>

### 选项 2：使用现有 SIF 文件

```python
from openhands.workspace import ApptainerWorkspace

# 使用现有的 Apptainer SIF 文件
with ApptainerWorkspace(
    sif_file="/path/to/your/agent-server.sif",
    host_port=8010,
) as workspace:
    result = workspace.execute_command("ls -la")
    print(result.stdout)
```

<a id="mount-host-directory"></a>

### 挂载主机目录

```python
from openhands.workspace import ApptainerWorkspace

# 将主机目录挂载到容器中
with ApptainerWorkspace(
    server_image="ghcr.io/openhands/agent-server:latest-python",
    host_port=8010,
    mount_dir="/path/to/host/directory",
) as workspace:
    result = workspace.execute_command("ls /workspace")
    print(result.stdout)
```

<a id="enable-nvidia-gpu-passthrough"></a>

### 启用 NVIDIA GPU 直通

```python
from openhands.workspace import ApptainerWorkspace

with ApptainerWorkspace(
    server_image="ghcr.io/openhands/agent-server:latest-python",
    host_port=8010,
    enable_gpu=True,
) as workspace:
    result = workspace.execute_command("nvidia-smi -L")
    print(result.stdout)
```

这启动容器 `apptainer run --nv ...`, 这使得 NVIDIA  GPUs 在工作区当主机有工作时 NVIDIA runtime

<a id="configuration-options"></a>

## 配置选项

| 参数 | 类型 | 默认 | 描述 |
|-----------|------|---------|-------------|
| `server_image` | `str \| None` | `None` | 预构建的 Agent Server 图像（与 `sif_file` 互斥） |
| `sif_file` | `str \| None` | `None` | 现有 SIF 文件的路径（与 `server_image` 互斥） |
| `host_port` | `int \| None` | `None` | 要绑定的端口（如果 None，则自动分配） |
| `mount_dir` | `str \| None` | `None` | 要挂载到容器中的主机目录 |
| `cache_dir` | `str \| None` | `~/.apptainer_cache` | 缓存 SIF 个文件的目录 |
| `forward_env` | `list[str]` | `["DEBUG"]` | 环境变量转发 |
| `detach_logs` | `bool` | `True` | 在后台流式传输日志 |
| `platform` | `PlatformType` | `"linux/amd64"` | 平台架构 |
| `extra_ports` | `bool` | `False` | 暴露额外的 VSCode 端口 |
| `enable_gpu` | `bool` | `False` | 使用 `--nv` 启用 NVIDIA GPU 直通 |
| `use_fakeroot` | `bool` | `True` | 使用 --fakeroot 获得一致的文件所有权 |

<a id="how-it-works"></a>

## 它是如何运作的

1. **图像准备**：提取Docker图像并转换为ApptainerSIF格式，或使用现有SIF文件
2. **缓存**：SIF文件默认缓存在`~/.apptainer_cache`中以加快启动速度
3. **容器执行**：使用`apptainer run`运行Agent Server
4. **健康检查**：等待服务器变得健康后再接受请求
5. **Cleanup**：完成后自动停止容器

<a id="differences-from-dockerworkspace"></a>

## 与 DockerWorkspace 的差异

| 特点 | DockerWorkspace | ApptainerWorkspace |
|---------|----------------|-------------------|
| 需要root权限 | 是（通常） | 否 |
| Docker 守护进程 | 必填 | 不需要 |
| 端口映射 | 本地人 | 主机联网 |
| 图片格式 | Docker | SIF（来自Docker） |
| HPC 支持 | 有限公司 | 优秀 |
| 设置复杂性 | 较低 | 稍高一点 |

<a id="troubleshooting"></a>

## 故障排除

<a id="apptainer-not-found"></a>

### Apptainer 未找到
```
RuntimeError: Apptainer is not available
```
**解决方案**：按照[安装指南](https://apptainer.org/docs/user/main/quick_start.html)安装Apptainer。

<a id="port-already-in-use"></a>

### 端口已在使用中
```
RuntimeError: Port 8010 is not available
```
**解决方案**：要么指定不同的`host_port`，要么让系统通过不指定来自动分配它。

<a id="image-pull-fails"></a>

### 镜像拉取失败
```
Failed to pull and convert Docker image
```
**解决方案**：确保您具有网络访问权限以从 Docker 注册表中提取映像。 Apptainer 直接从 Docker 注册表拉取，无需 Docker 守护进程。

<a id="complete-example"></a>

## 完整示例

请参阅 `examples/02_remote_agent_server/07_convo_with_apptainer_sandboxed_server.py` 获取完整的工作示例，该示例演示了：
- 设置 Apptainer 工作区
- 正在运行智能体个对话
- 沙盒环境下的文件操作
- 适当的清理

**测试示例：**
```bash
# 确保Apptainer已安装
apptainer --version

# 运行示例
cd examples/02_remote_agent_server
python 07_convo_with_apptainer_sandboxed_server.py
```

<a id="performance-notes"></a>

## 性能说明

- **首次运行**：由于图像下载和SIF转换而速度较慢
- **后续运行**：如果缓存SIF文件，速度会更快
- **最适合**：长时间运行的工作负载、HPC环境、多用户系统
- **缓存位置**：定期检查和清理`~/.apptainer_cache`

<a id="security"></a>

## 安全性

Apptainer为共享系统提供更好的安全隔离：
- 作为调用用户运行（无权限升级）
- 没有以 root 身份运行的守护进程
- 专为多租户 HPC 环境而设计
- 支持加密容器（可选）
