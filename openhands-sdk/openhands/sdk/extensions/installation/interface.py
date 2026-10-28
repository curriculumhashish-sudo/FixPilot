from abc import ABC, abstractmethod
from pathlib import Path
from typing import Protocol


class ExtensionProtocol(Protocol):
    """可安装扩展的结构协议。

    所有三个属性都声明为只读，以便普通 Pydantic 字段属性和 ``@property`` 访问器都满足
    协议。
    """

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def description(self) -> str | None: ...


class InstallationInterface[T: ExtensionProtocol](ABC):
    """教导 ``InstallationManager`` 如何加载 ``T`` 的抽象接口。

    对此进行子类化并为每个具体扩展类型实现 ``load_from_dir`` (e.g. 插件、技能）。
    """

    @staticmethod
    @abstractmethod
    def load_from_dir(extension_dir: Path) -> T: ...
