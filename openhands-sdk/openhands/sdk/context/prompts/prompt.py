# prompt_utils.py
import os
import re
import sys
from functools import lru_cache

from jinja2 import (
    BaseLoader,
    Environment,
    FileSystemBytecodeCache,
    Template,
    TemplateNotFound,
)

from openhands.sdk.utils.path import get_user_persistence_dir


class FlexibleFileSystemLoader(BaseLoader):
    """支持相对路径（在基本目录内）的 Jinja2 加载器
    以及文件系统上任何位置的绝对路径。
    """

    def __init__(self, searchpath: str):
        self.searchpath = os.path.abspath(searchpath)

    def get_source(self, environment, template):  # noqa: ARG002
        # 如果template是绝对路径，则直接使用
        if os.path.isabs(template):
            path = template
        else:
            # 否则，在搜索路径中查找它
            path = os.path.join(self.searchpath, template)

        if not os.path.exists(path):
            raise TemplateNotFound(template)

        mtime = os.path.getmtime(path)
        with open(path, encoding="utf-8") as f:
            source = f.read()

        def uptodate():
            try:
                return os.path.getmtime(path) == mtime
            except OSError:
                return False

        return source, path, uptodate


def refine(text: str) -> str:
    if sys.platform == "win32":
        text = re.sub(r"\bterminal\b", "execute_powershell", text, flags=re.IGNORECASE)
        text = re.sub(
            r"(?<!execute_)(?<!_)\bbash\b", "powershell", text, flags=re.IGNORECASE
        )
    return text


@lru_cache(maxsize=64)
def _get_env(prompt_dir: str) -> Environment:
    if not prompt_dir:
        raise ValueError("prompt_dir is required")
    # BytecodeCache 避免跨进程重新解析模板使用用户特定的缓存目录以避免多用户环境中的权限
    # 问题
    #
    cache_folder = get_user_persistence_dir() / "cache" / "jinja"
    cache_folder.mkdir(parents=True, exist_ok=True)
    bcc = FileSystemBytecodeCache(directory=str(cache_folder))
    env = Environment(
        loader=FlexibleFileSystemLoader(prompt_dir),
        bytecode_cache=bcc,
        autoescape=False,
    )
    # 可选：将细化公开为过滤器，以便模板可以使用 {{ text|refine }}
    env.filters["refine"] = refine
    return env


@lru_cache(maxsize=256)
def _get_template(prompt_dir: str, template_name: str) -> Template:
    env = _get_env(prompt_dir)
    try:
        return env.get_template(template_name)
    except Exception:
        raise FileNotFoundError(
            f"Prompt file {os.path.join(prompt_dir, template_name)} not found"
        )


def render_template(prompt_dir: str, template_name: str, **ctx) -> str:
    """渲染 Jinja2 模板。

    Args:
        prompt_dir: 相对模板路径的基目录。
        template_name: 模板文件名。 可以是：
            - 从 prompt_dir 加载的相对文件名 (e.g., "system_prompt.j2")
            - 绝对路径 (e.g., "/path/to/custom_prompt.j2")
        **ctx: 模板上下文变量。

    Returns:
        渲染的模板字符串。

    Raises:
        FileNotFoundError: 如果找不到模板文件。
    """
    # 如果template_name是绝对路径，则提取目录和文件名
    if os.path.isabs(template_name):
        # 在尝试加载文件之前检查文件是否存在
        if not os.path.isfile(template_name):
            raise FileNotFoundError(f"Prompt file {template_name} not found")
        actual_dir = os.path.dirname(template_name)
        actual_filename = os.path.basename(template_name)
        tpl = _get_template(actual_dir, actual_filename)
    else:
        tpl = _get_template(prompt_dir, template_name)
    return refine(tpl.render(**ctx).strip())
