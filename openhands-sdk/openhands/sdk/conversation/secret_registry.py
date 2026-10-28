"""机密用于处理对话中敏感数据的管理器。"""

import re
import time
from collections.abc import Callable, Collection, Mapping
from enum import Enum
from threading import RLock
from typing import Any, Final

from pydantic import BaseModel, Field, PrivateAttr, SecretStr

from openhands.sdk.logger import get_logger
from openhands.sdk.secret import SecretSource, SecretValue, StaticSecret
from openhands.sdk.utils.masking import (
    PreserveDataUrls,
    SkipSecretMasking,
    field_has_marker,
)
from openhands.sdk.utils.models import OpenHandsModel


logger = get_logger(__name__)

# 在重试失败的源之前进行退避； 无论如何，失败的查找不会掩盖任何内容。
FAILED_LOOKUP_RETRY_SECONDS: Final[float] = 60.0


def _mask_value(
    value: Any,
    mask: Callable[[str], str],
    *,
    skip_secret_masking: bool = False,
    preserve_data_urls: bool = False,
) -> Any:
    """递归屏蔽字符串，尊重不透明的载荷字段元数据。"""
    match value:
        case Enum():
            # str 子类枚举是一个 str，但屏蔽它会将成员降级为普通 str 并破坏字段的序列化
            # 。 它的词汇表是固定的，所以无论如何它都无法容纳机密。
            #
            return value
        case str():
            if skip_secret_masking:
                return value
            if preserve_data_urls and value.startswith("data:") and ";base64," in value:
                return value
            return mask(value)
        case BaseModel():
            return _mask_model(value, mask)
        case list():
            return [
                _mask_value(
                    item,
                    mask,
                    skip_secret_masking=skip_secret_masking,
                    preserve_data_urls=preserve_data_urls,
                )
                for item in value
            ]
        case tuple():
            items = [
                _mask_value(
                    item,
                    mask,
                    skip_secret_masking=skip_secret_masking,
                    preserve_data_urls=preserve_data_urls,
                )
                for item in value
            ]
            # 通过它自己的构造函数重建一个NamedTuple； tuple(items) 会像屏蔽枚举成员一样
            # 将其降级。
            #
            return type(value)(*items) if hasattr(value, "_fields") else tuple(items)
        case set() | frozenset():
            return type(value)(
                _mask_value(
                    item,
                    mask,
                    skip_secret_masking=skip_secret_masking,
                    preserve_data_urls=preserve_data_urls,
                )
                for item in value
            )
        case dict():
            return {
                key: _mask_value(
                    item,
                    mask,
                    skip_secret_masking=skip_secret_masking,
                    preserve_data_urls=preserve_data_urls,
                )
                for key, item in value.items()
            }
        case _:
            return value


def _mask_model[ModelT: BaseModel](model: ModelT, mask: Callable[[str], str]) -> ModelT:
    """重建 ``model``，屏蔽每个嵌套字符串。

    使用 ``model_copy`` 而不是验证往返，因此私有属性可以保留，并且不会重新强制任何字
    段。
    """
    updates = {}
    for name, field in type(model).model_fields.items():
        updates[name] = _mask_value(
            getattr(model, name),
            mask,
            skip_secret_masking=field_has_marker(field, SkipSecretMasking),
            preserve_data_urls=field_has_marker(field, PreserveDataUrls),
        )
    return model.model_copy(update=updates)


class StreamOutputMask:
    """屏蔽分片到达的文本。

    一个按块掩码器无法看到跨越块边界的一个机密分割，因此它阻碍了能够继续增长的最短后
    缀：减去一个字符后的最长注册值。
    """

    def __init__(self, pattern: re.Pattern[str] | None, max_len: int) -> None:
        self._pattern = pattern
        self._max_len = max_len
        self._held = ""

    def feed(self, text: str) -> str:
        """返回现在可以安全释放的屏蔽文本。"""
        pattern = self._pattern
        if pattern is None:
            return text
        self._held += text
        return self._release(pattern, max(len(self._held) - self._max_len + 1, 0))

    def flush(self) -> str:
        """归还仍保留的东西； 没有更多的输入了。"""
        pattern = self._pattern
        if pattern is None:
            return ""
        return self._release(pattern, len(self._held))

    def _release(self, pattern: re.Pattern[str], cut: int) -> str:
        out: list[str] = []
        pos = 0
        end = cut
        for match in pattern.finditer(self._held):
            # 在剪切之前开始的匹配已经是最大的：剪切在其后面留下了 max_len-1 个字符的前
            # 瞻。
            #
            if match.start() >= cut:
                break
            out.append(self._held[pos : match.start()])
            out.append("<secret-hidden>")
            pos = match.end()
            end = max(end, match.end())
        out.append(self._held[pos:end])
        self._held = self._held[end:]
        return "".join(out)


class SecretRegistry(OpenHandsModel):
    """管理机密并在需要时将它们注入到 bash 命令中。

    机密注册表存储机密键到 SecretSources 的映射，用于检索实际的机密值。 当 bash 命令
    即将执行时，它会扫描命令中的任何机密键并注入相应的环境变量。

    机密源将在序列化时根据上下文的内容酌情编辑/加密其敏感值。 如果上下文存在并且包含“
    密码”对象，则该对象用于加密。 如果它包含设置为 True 的布尔值“
    expose_secrets”标志，则机密将以纯文本形式转储。 否则机密是已脱敏。

    此外，它还跟踪最新导出的值，以实现一致的屏蔽，即使可调用机密在后续调用中失败时也
    是如此。
    """

    secret_sources: dict[str, SecretSource] = Field(default_factory=dict)
    _exported_values: dict[str, str] = PrivateAttr(default_factory=dict)
    _exported_values_lock: RLock = PrivateAttr(default_factory=RLock)
    _failed_lookups: dict[str, float] = PrivateAttr(default_factory=dict)

    def track_exported_values(self, values: Mapping[str, str]) -> None:
        """跟踪输出掩蔽值。"""
        with self._exported_values_lock:
            self._exported_values.update({k: v for k, v in values.items() if v})

    def update_secrets(
        self,
        secrets: Mapping[str, SecretValue],
    ) -> None:
        """在管理器中添加或更新机密。

        Args:
            secrets: 字典将机密键映射到任一字符串值
                    或返回字符串值的可调用函数
        """
        secret_sources = {name: _wrap_secret(value) for name, value in secrets.items()}
        self.secret_sources.update(secret_sources)

    def find_secrets_in_text(self, text: str) -> set[str]:
        """查找给定文本中提到的所有机密键。

        Args:
            text: 要搜索机密键的文本

        Returns:
            文本中找到的一组机密键
        """
        found_keys = set()
        for key in self.secret_sources.keys():
            if key.lower() in text.lower():
                found_keys.add(key)
        return found_keys

    def get_secrets_as_env_vars(self, command: str) -> dict[str, str]:
        """获取应导出为命令环境变量的机密。

        Args:
            command: 用于检查机密引用的 bash 命令

        Returns:
            要导出的环境变量字典（键 -> 值）
        """
        found_secrets = self.find_secrets_in_text(command)

        if not found_secrets:
            return {}

        logger.debug(f"Found secrets in command: {found_secrets}")

        env_vars = {}
        for key in found_secrets:
            try:
                source = self.secret_sources[key]
                value = source.get_value()
                if value:
                    env_vars[key] = value
                    self.track_exported_values({key: value})
            except Exception as e:
                logger.error(f"Failed to retrieve secret for key '{key}': {e}")
                continue

        logger.debug(f"Prepared {len(env_vars)} secrets as environment variables")
        return env_vars

    def get_all_secrets_as_env_vars(
        self, exclude: Collection[str] | None = None
    ) -> dict[str, str]:
        """将每个注册的机密解析为环境变量映射。

        与：meth:`get_secrets_as_env_vars` 不同，它会名称扫描单个命令并仅注入它引用的
        机密，这会解析整个注册表。 它适用于不透明的消费
        者（e.g. ACP CLI 子进程），不能按命令进行名称扫描，并且必须预先接收其凭据。
        跟踪解析值以进行输出屏蔽，并跳过而不是引发查找失败。

        Note: 这会注入 *whole* 注册表； 最小权限范围
        （仅提供者信用 + 明确的许可名单）被推迟到 #1039 任务 6。

        Args:
            exclude: 机密要跳过的名称 — e.g。 指定更高优先级的密钥
                无论如何都会设置，或者将文件内容机密存储到磁盘（避免了可能远程的
                ``get_value()`` 资源浪费）。

        Returns:
            要导出的环境变量字典（键 -> 值），省略空值和排除的名称。
        """
        skip = set(exclude or ())
        env_vars: dict[str, str] = {}
        for name in self.secret_sources:
            if name in skip:
                continue
            value = self.get_secret_value(name)
            if value:
                env_vars[name] = value
        return env_vars

    def mask_secrets_in_output(self, text: str) -> str:
        """给定文本中的掩码机密值。

        隐藏了每注册的机密的最后已解析的值，而不是只隐藏导出的值：一个值可以到达输出
        ，而命令从未引用其名称 (e.g。 git 远程 URL 中的 token）。
        缓存的值不会重新解析，因此旋转的机密会掩盖其先前的值。

        Args:
            text: 要屏蔽机密的文本

        Returns:
            机密值替换为 <secret-hidden> 的文本
        """
        if not text:
            return text

        # 解决未缓存的源，在失败时后退：get_value() 可能会阻塞网络 I/O 并屏蔽每个输出和
        # 每个 ACP 块的运行。
        #
        now = time.monotonic()
        for key in list(self.secret_sources):
            if key in self._exported_values:
                continue
            failed_at = self._failed_lookups.get(key)
            if failed_at is not None and now - failed_at < FAILED_LOOKUP_RETRY_SECONDS:
                continue
            if not self.get_secret_value(key):
                self._failed_lookups[key] = now

        masked_text = text
        with self._exported_values_lock:
            exported_values = tuple(self._exported_values.values())
        for value in exported_values:
            if value:
                masked_text = masked_text.replace(value, "<secret-hidden>")

        return masked_text

    def compile_stream_mask(self) -> StreamOutputMask:
        """返回一个流式传输屏蔽器，覆盖迄今为止 * 解析的值 *。

        对于不能承受 `mask_secrets_in_output` 方法的热点路径， ``get_value()`` 可能会
        因网络 I/O 而阻塞，以及在同步智
        能体路径下运行的锁路径。 减少面具的交换：用它来进步，而不是为了持久的记录。
        """
        with self._exported_values_lock:
            values = {value for value in self._exported_values.values() if value}
        if not values:
            return StreamOutputMask(None, 0)
        # 最长的优先，因此重叠的较短值无法掩盖较长值的一半并将 REST 保留为明文。
        #
        pattern = re.compile(
            "|".join(re.escape(v) for v in sorted(values, key=len, reverse=True))
        )
        return StreamOutputMask(pattern, max(len(v) for v in values))

    def mask_secrets_in_model[ModelT: BaseModel](self, model: ModelT) -> ModelT:
        """返回 ``model``，并在每个嵌套字符串中屏蔽机密值。

        屏蔽一个已知文本字段对于工具输出来说是不够的：
        ``Observation.to_llm_content`` 是可重写的，并且有几个工具构建模型从其自己的字
        段而不是 ``content`` 中看到的内容。
         遍历整个模型是默认覆盖工具 #14 的原因。
        """
        return _mask_model(model, self.mask_secrets_in_output)

    def get_secret_infos(self) -> list[dict[str, str | None]]:
        """获取提示词包含的机密信息（名称和描述）。

        Returns:
            带有“名称”和“描述”键的字典列表。 如果没有注册机密，则返回空列表。 如果不
            可用，说明将为 None。
        """
        if not self.secret_sources:
            return []
        secret_infos = []
        for name, source in self.secret_sources.items():
            description = source.description
            secret_infos.append({"name": name, "description": description})
        return secret_infos

    def get_secret_value(self, name: str) -> str | None:
        """按名称查找单个机密值。

        此方法检索特定机密的值。 它被设计为作为回调传递给需要机密查找（e.g.,
        expand_mcp_variables）的函数，而不会立即暴露所有机密。

        检索到的值在 _exported_values 中跟踪，以便在命令输出中保持一致的屏蔽。

        Args:
            name: 要检索的机密的名称。

        Returns:
            如果找到并成功检索，则为机密值，否则为 None。

        Note:
            对于缺失机密和检索失败都返回 None。 检索错误（网络、身份验证等）将记录为
            警告。
        """
        source = self.secret_sources.get(name)
        if source is None:
            return None
        try:
            value = source.get_value()
            if value:
                self.track_exported_values({name: value})
            return value
        except (OSError, TimeoutError) as e:
            # 网络/IO 错误 - 可能是暂时的、记录并返回 None
            logger.warning(
                f"Transient error retrieving secret '{name}' "
                f"(may retry later): {type(e).__name__}: {e}"
            )
            return None
        except (ValueError, KeyError, TypeError) as e:
            # 配置/数据错误 - 可能是永久性的
            logger.warning(
                f"Configuration error for secret '{name}': {type(e).__name__}: {e}"
            )
            return None
        except Exception as e:
            # 意外错误 - 记录完整详细信息以供调试
            logger.warning(
                f"Unexpected error retrieving secret '{name}': {type(e).__name__}: {e}"
            )
            return None


def _wrap_secret(value: SecretValue) -> SecretSource:
    """将给定的值转换为机密源"""
    if isinstance(value, SecretSource):
        return value
    if isinstance(value, str):
        return StaticSecret(value=SecretStr(value))
    raise ValueError("Invalid SecretValue")
