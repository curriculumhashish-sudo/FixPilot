"""注册一个 API-key 重置钩子，以便管理代理 LLMs 从 401 错误恢复。

企业/SaaS 控制平面创建托管 LiteLLM 代理密钥，并可以在拍摄会话的 LLM 快照后轮换或修复
它。 当这种情况发生时，沙盒智能体继续发送过期密钥，并且第一次调用L
LM会失败，``401 token_not_found_in_db`` — 在OpenHands/software-智能体-SDK#5189中，“第
一次对话失败，然后自我修
复”的行为。

SDK 提供了一个选择加入的缓解措施：
:meth:`openhands.sdk.llm.LLM.set_api_key_refresh_hook` 重新解析密钥一次
和重试一次在身份验证错误。 钩子是一个 Python 可调用，因此它不能被已序列化并被放入测试
环境中 LLM — 必须在这里注册，即在该过程中 LLM 实际上运行。

该模块连接到控制平面提供的重新解析源。 这是 ** 无操作，除非 ** 控制平面同时设置
``OH_LLM_API_KEY_REFRESH_URL`` 和 ``OH_LLM_API_KEY_REFRESH_BASE_URLS`` 在沙箱环境中，
因此不选择加入的对
话将保持其当前的确切行为。

控制平面必须公开什么（参见``register_managed_llm_key_refresh``）：

* ``OH_LLM_API_KEY_REFRESH_URL`` — URL 沙箱可以 GET 获取
  *current* 托管密钥作为纯文本响应正文。
* ``OH_LLM_API_KEY_REFRESH_BASE_URLS`` — 以逗号分隔的 LLM 允许列表
  ``base_url`` 托管密钥适用的值。 必需：操作员必须明确列出管理的代理，这样钩子永远无
  法注册在用户的 BYOK LLM（401 不应被重试使用管理密钥）。
* ``OH_LLM_API_KEY_REFRESH_HEADERS`` — 可选的 JSON 请求标头对象，用于验证刷新调用 (
e.g. 沙箱会话密钥）。 标头值可以使用
 ``$VAR`` / ``${VAR}`` 语法引用环境变量，从沙箱环境扩展； 这样，控制平面就可以在构建
 环境时不需知道每个沙箱的密钥，直接将头部指向
``${OH_SESSION_API_KEYS_0}``。 (远程运行时会在沙箱内部为那个密钥分配值。)
"""

from __future__ import annotations

import json
import os

from openhands.sdk.agent import AgentBase
from openhands.sdk.llm import LLM
from openhands.sdk.llm.utils.openhands_provider import litellm_call_kwargs
from openhands.sdk.logger import get_logger
from openhands.sdk.secret import LookupSecret


logger = get_logger(__name__)

REFRESH_URL_ENV = "OH_LLM_API_KEY_REFRESH_URL"
REFRESH_HEADERS_ENV = "OH_LLM_API_KEY_REFRESH_HEADERS"
REFRESH_BASE_URLS_ENV = "OH_LLM_API_KEY_REFRESH_BASE_URLS"


def _load_headers(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("%s is not valid JSON; ignoring", REFRESH_HEADERS_ENV)
        return {}
    if not isinstance(data, dict):
        logger.warning("%s must be a JSON object; ignoring", REFRESH_HEADERS_ENV)
        return {}
    # 值可以引用环境变量 (``$VAR`` / ``${VAR}``)，展开
    # from this process's environment. This lets the control plane point a header
    # 凭据在那里，它无法知道何时构建环境——特别是``OH_SESSION_API_KEYS_0``中的沙盒会话密
    # 钥，该密钥按沙盒分配，并且对于远程运行时，只有在沙盒内部才知悉。
    #
    return {str(k): os.path.expandvars(str(v)) for k, v in data.items()}


def _managed_base_urls(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {u.strip().rstrip("/") for u in raw.split(",") if u.strip()}


def _llm_is_in_scope(llm: LLM, managed_base_urls: set[str]) -> bool:
    # 订阅身份验证不是可刷新的 API 键（SDK 解析器也会跳过它）。
    if llm.auth_type != "api_key":
        return False
    base_url = (litellm_call_kwargs(llm.model, llm.base_url)["api_base"] or "").rstrip(
        "/"
    )
    return base_url in managed_base_urls


def register_managed_llm_key_refresh(agent: AgentBase) -> int:
    """在智能体的管理代理 LLMs 上注册一个刷新的 401 挂钩。

    遍历智能体's LLMs (``agent.get_all_llms()`` 会生成 run loop 使用的活的实例) 并，
    对于每个在作用域内的 LLM，注册一个
    钩子，该钩子会重新解析 ``OH_LLM_API_KEY_REFRESH_URL`` 中的当前管理键。

    返回钩子注册在 LLMs 上的次数 (``0`` 表示功能关闭或没有匹配的 LLM)。
    ``OH_LLM_API_KEY_REFRESH_URL`` 和
    ``OH_LLM_API_KEY_REFRESH_BASE_URLS`` 中的控制平面都选择后，才允许无条件调用：否则
    什么都不做。
    """
    url = os.environ.get(REFRESH_URL_ENV)
    if not url:
        return 0

    managed_base_urls = _managed_base_urls(os.environ.get(REFRESH_BASE_URLS_ENV))
    if not managed_base_urls:
        # 失败：缺少的允许列表本应匹配 BYOK LLMs。
        logger.warning(
            "%s is set but %s is empty; managed LLM key refresh stays off. "
            "Enumerate the managed proxy base_url(s) to enable it.",
            REFRESH_URL_ENV,
            REFRESH_BASE_URLS_ENV,
        )
        return 0

    headers = _load_headers(os.environ.get(REFRESH_HEADERS_ENV))

    def _refresh() -> str | None:
        # 每次调用都是新鲜的 LookupSecret，因此不会从缓存的密钥中提供轮换密钥。 永不引发
        # ：失败的刷新必须让原始的 401 浮出水面。
        #
        try:
            value = LookupSecret(url=url, headers=headers).get_value()
        except Exception:
            logger.warning(
                "Managed LLM key refresh failed; surfacing the original auth error",
                exc_info=True,
            )
            return None
        value = (value or "").strip()
        return value or None

    count = 0
    for llm in agent.get_all_llms():
        if _llm_is_in_scope(llm, managed_base_urls):
            llm.set_api_key_refresh_hook(_refresh)
            count += 1

    if count:
        logger.info("Registered managed LLM key refresh hook on %d LLM(s)", count)
    else:
        logger.debug(
            "%s is set but no LLM matched the managed-key scope; no hook registered",
            REFRESH_URL_ENV,
        )
    return count
