"""设置和配置文件使用的 ``X-Expose-Secrets`` 流的共享助手。"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal, cast

from fastapi import HTTPException, Request, status
from pydantic import SecretStr
from pydantic_core import PydanticSerializationError

from openhands.sdk.llm import LLM
from openhands.sdk.llm.llm import LLM_SECRET_FIELDS
from openhands.sdk.llm.provider_connection_store import ProviderConnectionNotFound
from openhands.sdk.utils.cipher import FERNET_TOKEN_PREFIX, Cipher
from openhands.sdk.utils.pydantic_secrets import MissingCipherError


ExposeSecretsMode = Literal["encrypted", "plaintext"]


def get_config(request: Request):
    """从应用程序状态获取配置，如果未初始化则引发 503。"""
    config = getattr(request.app.state, "config", None)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server not fully initialized",
        )
    return config


def get_cipher(request: Request) -> Cipher | None:
    """获取配置的密码（``None``，当 ``OH_SECRET_KEY`` 未设置时）。"""
    return get_config(request).cipher


def parse_expose_secrets_header(request: Request) -> ExposeSecretsMode | None:
    """解析 ``X-Expose-Secrets`` 标头。

    返回 ``"encrypted"``、``"plaintext"`` 或 ``None``（标头不存在）。 任何其他值都会
    加注
    ``HTTPException(400)``。
    """
    header_value = request.headers.get("X-Expose-Secrets", "").lower().strip()

    if not header_value:
        return None

    # 设置流的现有客户端接受旧别名； 映射到“加密”，因此过时的“True”永远不会意外暴露明文
    # 。
    #
    if header_value == "true":
        return "encrypted"

    if header_value in ("encrypted", "plaintext"):
        return cast(ExposeSecretsMode, header_value)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Invalid X-Expose-Secrets header value: '{header_value}'. "
            "Valid values are: 'encrypted', 'plaintext'."
        ),
    )


def build_expose_context(
    expose_mode: ExposeSecretsMode | None, cipher: Cipher | None
) -> dict[str, Any]:
    """为给定的暴露模式构建 Pydantic 序列化上下文。"""
    if expose_mode is None:
        return {}
    return {"expose_secrets": expose_mode, "cipher": cipher}


def _has_missing_cipher_cause(exc: BaseException) -> bool:
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        if isinstance(cur, MissingCipherError):
            return True
        seen.add(id(cur))
        cur = cur.__cause__ or cur.__context__
    return False


def decrypt_incoming_llm_secrets(llm: LLM, cipher: Cipher) -> LLM:
    """解密客户端发回的任何预加密的 LLM 机密字段。

    FastAPI 解析请求正文，而验证上下文中没有密码，因此加密的 blob 以
    ``SecretStr("gAAAAA...")`` 形式到达。 没有这个
    pass, downstream code (e.g. profile save, ``conversation.switch_llm``) sees
    加密的密文作为 API 密钥，并将其重新加密或逐字转发给模型提供者。 纯文本输入保持不
    变。
    """
    updates: dict[str, SecretStr] = {}
    for field in LLM_SECRET_FIELDS:
        val = getattr(llm, field, None)
        if not isinstance(val, SecretStr):
            continue
        raw = val.get_secret_value()
        if not raw.startswith(FERNET_TOKEN_PREFIX):
            continue
        decrypted = cipher.decrypt(raw)
        if decrypted is not None:
            updates[field] = decrypted
    return llm.model_copy(update=updates) if updates else llm


@contextmanager
def translate_missing_cipher() -> Iterator[None]:
    """将丢失密码序列化器错误转换为 HTTP 503。"""
    try:
        yield
    except (PydanticSerializationError, MissingCipherError) as e:
        if _has_missing_cipher_cause(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Encryption not available: OH_SECRET_KEY is not configured. "
                    "Cannot return encrypted secrets."
                ),
            )
        raise


@contextmanager
def store_errors() -> Iterator[None]:
    """将配置文件存储错误（``LLMProfileStore``/``AgentProfileStore``) 映射到
    HTTP 回应。 由设置、配置文件和智能体-配置文件路由器共享。
    """
    try:
        yield
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Profile store is busy. Please retry.",
        )
    except ProviderConnectionNotFound as e:
        # ValueError 的子类，因此必须在下面的通用 ValueError 臂之前处理。 悬空的提供程序
        # 引用是一个可解决的配置问题（重新创建连接或编辑配置文件），因此是 422 而不是通
        # 用的 400。
        #
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
