"""
使用 Jinja2 实现独立聊天模板。

该模块提供了一个轻量级的聊天模板渲染实现，兼容HuggingFace的转换器，但移除了对完整转换
器库的依赖。

实现遵循与 Transformer 相同的方法：
- 使用 Jinja2 进行模板渲染
- 从 tokenizer_config.json 动态加载模板
- 支持缓存已编译的模板和获取的配置
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import jinja2
from jinja2.ext import loopcontrols
from jinja2.sandbox import ImmutableSandboxedEnvironment


# 下载的分词器配置的缓存目录
CACHE_DIR = Path.home() / ".cache" / "chat_templates"


def _get_cache_path(tokenizer_name: str) -> Path:
    """获取分词器配置的缓存路径。"""
    # 从分词器名称创建安全文件名
    safe_name = hashlib.md5(tokenizer_name.encode()).hexdigest()
    return CACHE_DIR / f"{safe_name}_tokenizer_config.json"


def _fetch_tokenizer_config(
    tokenizer_name: str, use_cache: bool = True
) -> dict[str, Any]:
    """
    从 HuggingFace 集线器获取 tokenizer_config.json。

    Args:
        tokenizer_name: HuggingFace 模型/标记器名称
            (e.g., "Qwen/Qwen3-4B-Instruct-2507")
        use_cache: 是否使用缓存配置（如果可用）

    Returns:
        解析后的分词器配置字典
    """
    cache_path = _get_cache_path(tokenizer_name)

    # 尝试从缓存加载
    if use_cache and cache_path.exists():
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)

    # 从 HuggingFace 集线器获取
    url = f"https://huggingface.co/{tokenizer_name}/raw/main/tokenizer_config.json"

    try:
        request = Request(url, headers={"User-Agent": "chat_template/1.0"})
        with urlopen(request, timeout=30) as response:
            config = json.loads(response.read().decode("utf-8"))
    except URLError as e:
        raise RuntimeError(f"Failed to fetch tokenizer config from {url}: {e}")

    # 缓存配置
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(config, f)

    return config


@lru_cache(maxsize=16)
def _compile_jinja_template(chat_template: str) -> jinja2.Template:
    """
    编译 Jinja2 聊天模板。

    这将 Transformer 实现与自定义 tojson 过滤器和其他实用程序相匹配。
    """

    def raise_exception(message: str) -> None:
        raise jinja2.exceptions.TemplateError(message)

    def tojson(
        x: Any,
        ensure_ascii: bool = False,
        indent: int | None = None,
        separators: tuple[str, str] | None = None,
        sort_keys: bool = False,
    ) -> str:
        # 匹配 Transformer 实现 - 无 HTML 转义
        return json.dumps(
            x,
            ensure_ascii=ensure_ascii,
            indent=indent,
            separators=separators,
            sort_keys=sort_keys,
        )

    jinja_env = ImmutableSandboxedEnvironment(
        trim_blocks=True,
        lstrip_blocks=True,
        extensions=[loopcontrols],
    )
    jinja_env.filters["tojson"] = tojson
    jinja_env.globals["raise_exception"] = raise_exception

    return jinja_env.from_string(chat_template)


class ChatTemplateRenderer:
    """
    与 HuggingFace 转换器兼容的轻量级聊天模板渲染器。

    该类可以从HuggingFace Hub动态加载模板或直接使用提供的模板。
    """

    def __init__(
        self,
        tokenizer_name: str | None = None,
        chat_template: str | None = None,
        use_cache: bool = True,
    ):
        """
        初始化渲染器。

        Args:
            tokenizer_name: HuggingFace 要从中加载模板的分词器名称。
                如果提供，将从 HuggingFace Hub 获取 tokenizer_config.json。
            chat_template: 直接 Jinja2 模板字符串。
                如果提供，tokenizer_name 将被忽略。
            use_cache: 是否缓存获取的分词器配置。
        """
        if chat_template is not None:
            self._chat_template = chat_template
        elif tokenizer_name is not None:
            config = _fetch_tokenizer_config(tokenizer_name, use_cache=use_cache)
            self._chat_template = config.get("chat_template")
            if self._chat_template is None:
                raise ValueError(
                    f"No chat_template found in tokenizer config for {tokenizer_name}"
                )
        else:
            raise ValueError("Either tokenizer_name or chat_template must be provided")

        self._compiled_template = _compile_jinja_template(self._chat_template)

    @property
    def chat_template(self) -> str:
        """原始 Jinja2 聊天模板字符串。"""
        assert self._chat_template is not None
        return self._chat_template

    def apply_chat_template(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
        add_generation_prompt: bool = False,
        **kwargs: Any,
    ) -> str:
        """
        应用聊天模板来格式化消息。

        Args:
            messages: 带有“角色”和“内容”键的消息字典列表。
            tools: 用于函数调用的工具定义的可选列表。
            add_generation_prompt: 如果 True，则在末尾添加助手提示词。
            **kwargs: 附加模板变量。

        Returns:
            格式化字符串已准备好进行标记化。
        """
        return self._compiled_template.render(
            messages=messages,
            tools=tools,
            add_generation_prompt=add_generation_prompt,
            **kwargs,
        )


# 适用于简单用例的便捷功能
def apply_chat_template(
    messages: Sequence[dict[str, Any]],
    tokenizer_name: str | None = None,
    chat_template: str | None = None,
    tools: Sequence[dict[str, Any]] | None = None,
    add_generation_prompt: bool = False,
    use_cache: bool = True,
    **kwargs: Any,
) -> str:
    """
    应用聊天模板来格式化消息。

    这是一个创建渲染器并应用模板的便捷函数。 为了重复使用相同的分词器，最好直接使用
    ChatTemplateRenderer。

    Args:
        messages: 带有“角色”和“内容”键的消息字典列表。
        tokenizer_name: HuggingFace 要从中加载模板的分词器名称。
        chat_template: 直接 Jinja2 模板字符串。
            如果提供，tokenizer_name 将被忽略。
        tools: 用于函数调用的工具定义的可选列表。
        add_generation_prompt: 如果 True，则在末尾添加助手提示词。
        use_cache: 是否缓存获取的分词器配置。
        **kwargs: 附加模板变量。

    Returns:
        格式化字符串已准备好进行标记化。
    """
    renderer = ChatTemplateRenderer(
        tokenizer_name=tokenizer_name,
        chat_template=chat_template,
        use_cache=use_cache,
    )
    return renderer.apply_chat_template(
        messages=messages,
        tools=tools,
        add_generation_prompt=add_generation_prompt,
        **kwargs,
    )
