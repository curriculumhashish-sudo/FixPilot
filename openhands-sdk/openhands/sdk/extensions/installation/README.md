<a id="installation"></a>

# 安装

用于从本地或远程源安装、跟踪和加载扩展的通用框架。

<a id="overview"></a>

## 概述

安装模块**与扩展类型无关**。 它由类型 `T`（具有 `name`、`version` 和 `description` 属性的任何对象）和知道如何从目录加载 `T` 的 `InstallationInterface[T]` 参数化。 其他一切——获取、复制、元数据簿记、启用/禁用状态——都是通用处理的。

<a id="usage"></a>

## 用途

<a id="1-define-your-extension-type-and-loader"></a>

### 1. 定义您的扩展类型和加载程序

```python
from pathlib import Path
from pydantic import BaseModel
from openhands.sdk.extensions.installation import (
    InstallationInterface,
    InstallationManager,
)

class Widget(BaseModel):
    name: str
    version: str
    description: str

class WidgetLoader(InstallationInterface[Widget]):
    @staticmethod
    def load_from_dir(extension_dir: Path) -> Widget:
        return Widget.model_validate_json(
            (extension_dir / "widget.json").read_text()
        )
```

<a id="2-create-a-manager"></a>

### 2. 创建经理

```python
manager = InstallationManager(
    installation_dir=Path("~/.myapp/widgets/installed").expanduser(),
    installation_interface=WidgetLoader(),
)
```

<a id="3-manage-extensions"></a>

### 3. 管理扩展

```python
# 从本地路径或远程源安装
info = manager.install("github:owner/my-widget", ref="v1.0.0")
info = manager.install("/path/to/local/widget")

# 强制覆盖现有安装（保留启用状态）
info = manager.install("github:owner/my-widget", force=True)

# 列表/加载
all_info = manager.list_installed()        # 列表[InstallationInfo]
widgets  = manager.load_installed()        # List[Widget]（仅启用）

# 启用/禁用
manager.disable("my-widget")               # 排除在load_installed()之外
manager.enable("my-widget")                # 再次包含在内

# 查找单个扩展名
info = manager.get("my-widget")            # InstallationInfo | None

# 从原始来源更新到最新版本
info = manager.update("my-widget")

# 完全移除
manager.uninstall("my-widget")
```

<a id="self-healing-metadata"></a>

## 自愈元数据

`list_installed()`（以及扩展名 `load_installed()`）自动将 `.installed.json` 元数据与磁盘上的实际内容进行协调：

- **过时条目** — 如果已手动删除跟踪的扩展程序目录，则元数据条目将被删除。
- **未跟踪的目录** — 如果存在有效的扩展目录但不在元数据中，它会被发现并添加到  `source="local"`.

这意味着元数据文件始终是唯一的事实来源 *之后* 即使外部修改了文件系统，也进行列表/加载调用。

<a id="extension-naming"></a>

## 扩展命名

扩展名必须为 **kebab-case** (`^[a-z0-9]+(-[a-z0-9]+)*$`)。 这是在安装、卸载、启用、禁用、获取和更新时强制执行的，以防止路径遍历攻击（e.g。 `../evil`).
