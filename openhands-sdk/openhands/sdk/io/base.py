from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager


class FileStore(ABC):
    """文件存储操作的抽象基类。

    此类定义了文件存储后端的接口，可以处理基本的文件操作，例如读取、写入、列出和删除
    文件。

    实现应通过 `lock()` 上下文管理器为线程/进程安全操作提供锁定机制。
    """

    @abstractmethod
    def write(self, path: str, contents: str | bytes) -> None:
        """将内容写入指定路径的文件中。

        Args:
            path: 应写入内容的文件路径。
            contents: 要写入的数据，可以是字符串或字节。
        """

    @abstractmethod
    def read(self, path: str) -> str:
        """读取文件内容并将其作为字符串返回。

        Args:
            path: 要读取的文件路径。

        Returns:
            文件内容作为字符串。
        """

    @abstractmethod
    def list(self, path: str) -> list[str]:
        """列出指定路径下的所有文件和目录。

        Args:
            path: 列出内容的目录路径。

        Returns:
            指定路径中的文件和目录名称的列表。
        """

    @abstractmethod
    def delete(self, path: str) -> None:
        """删除指定路径下的文件或目录。

        Args:
            path: 要删除的文件或目录路径。
        """

    @abstractmethod
    def exists(self, path: str) -> bool:
        """检查指定路径下是否存在文件或目录。

        Args:
            path: 要检查的文件或目录路径。

        Returns:
            如果路径存在则为 True，否则为 False。
        """

    @abstractmethod
    def get_absolute_path(self, path: str) -> str:
        """获取给定相对路径的绝对文件系统路径。

        Args:
            path: 文件存储内的相对路径。

        Returns:
            文件系统上的绝对路径。
        """

    @abstractmethod
    @contextmanager
    def lock(self, path: str, timeout: float = 30.0) -> Iterator[None]:
        """获取给定路径的独占锁。

        此上下文管理器提供线程和进程安全锁定。 实现可以使用基于文件的锁定、线程锁或其
        他适当的机制。

        Args:
            path: 到锁的路径（用于标识锁）。
            timeout: 等待锁采集的最大秒数。

        Yields:
            获取锁时为 None。

        Raises:
            TimeoutError: 如果在超时内无法获取锁。

        Note:
            基于文件的锁定（flock）确实不在 NFS 安装或网络文件系统上可靠地工作。
        """
        yield  # pragma: no cover
