"""
用于防止已序列化数据中的机密意外泄露的密码实用程序

SECURITY WARNINGS:
- 机密键是一个字符串，以便于使用，但应包含至少 256 位熵

KEYROTATION：A``Cipher``可以携带之前的密钥。 它总是先用当前密钥加密，然后用当前密钥解
密，接着是每个先前的密钥（例如``cryptography``'
s ``MultiFernet``），因此在密钥旋转后保存的旧密钥值仍然可读，并在下次保存时用当前密钥
重新加密。
"""

import hashlib
from base64 import b64encode
from collections.abc import Iterable
from typing import Final

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from pydantic import SecretStr


# Fernet token 前缀用于区分密文和遗留明文。 不要缩短：5 个字符的前缀与实际的 Base64 明文
# 发生冲突。
#
FERNET_TOKEN_PREFIX: Final[str] = "gAAAAA"


class Cipher:
    """
    用于防止意外机密泄露的简单加密实用程序。
    """

    def __init__(self, secret_key: str, previous_keys: Iterable[str] = ()):
        self.secret_key = secret_key
        # 仅解密的密钥（最旧的最后）。 删除当前键的空白条目和重复项； 顺序被保留，因此首
        # 先尝试最可能的密钥（最近轮换的密钥）。
        #
        previous: list[str] = []
        for key in previous_keys:
            if key.strip() and key != secret_key and key not in previous:
                previous.append(key)
        self.previous_keys: tuple[str, ...] = tuple(previous)
        self._fernet: Fernet | None = None
        self._multi_fernet: MultiFernet | None = None

    def encrypt(self, secret: SecretStr | None) -> str | None:
        if secret is None:
            return None
        secret_value = secret.get_secret_value().encode()
        fernet = self._get_fernet()
        result = fernet.encrypt(secret_value).decode()
        return result

    def decrypt(self, secret: str | None) -> SecretStr | None:
        """
        解密机密值，如果解密失败则返回 None。

        这可以处理现有对话已序列化使用不同加密密钥或包含无效加密数据的情况。 当解密失
        败并返回 None 时，会记录一条警告。 这模仿了没有定义密码的情况，因此机密
        其中已脱敏。
        """
        if secret is None:
            return None
        try:
            decrypted = self._get_multi_fernet().decrypt(secret.encode()).decode()
            return SecretStr(decrypted)
        except Exception as e:
            # 在这里导入以避免循环导入
            from openhands.sdk.logger import get_logger

            logger = get_logger(__name__)
            logger.warning(
                f"Failed to decrypt secret value (setting to None): {e}. "
                "This may occur when loading conversations encrypted with a different "
                "key or when upgrading from older versions."
            )
            return None

    def try_decrypt_str(self, value: str) -> str | None:
        """解密为字符串，或 InvalidToken 上的 ``None``（无日志记录）。"""
        try:
            return self._get_multi_fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            return None

    def is_current(self, token: str) -> bool:
        """``token`` 是否在当前密钥（不是前一个密钥）下解密。"""
        try:
            self._get_fernet().decrypt(token.encode())
        except InvalidToken:
            return False
        return True

    def rotate(self, token: str) -> str | None:
        """返回在当前密钥下重新加密的``token``。

        已在当前键下的 token 不变地返回； a token 只有先前的密钥可以解密被重新加密；
        ``None`` 当没有配置的密钥可以解密时。
        """
        if self.is_current(token):
            return token
        try:
            return self._get_multi_fernet().rotate(token.encode()).decode()
        except InvalidToken:
            return None

    @staticmethod
    def _derive_fernet(key: str) -> Fernet:
        # 对密钥进行哈希处理以确保我们拥有 256 位值
        return Fernet(b64encode(hashlib.sha256(key.encode()).digest()))

    def _get_multi_fernet(self) -> MultiFernet:
        multi = self._multi_fernet
        if multi is None:
            multi = MultiFernet(
                [self._get_fernet()]
                + [self._derive_fernet(key) for key in self.previous_keys]
            )
            object.__setattr__(self, "_multi_fernet", multi)
        return multi

    def _get_fernet(self) -> Fernet:
        fernet = self._fernet
        if fernet is None:
            fernet = self._derive_fernet(self.secret_key)
            object.__setattr__(self, "_fernet", fernet)
        return fernet
