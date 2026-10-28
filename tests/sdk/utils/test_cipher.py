"""Cipher 实用程序类的测试。"""

from base64 import urlsafe_b64encode

from cryptography.fernet import Fernet
from pydantic import SecretStr

from openhands.sdk.utils.cipher import Cipher


def test_cipher_encrypt_decrypt():
    """测试基本的加密和解密功能。"""
    # 生成正确的 Fernet 密钥
    key = urlsafe_b64encode(b"a" * 32).decode("ascii")
    cipher = Cipher(key)

    secret = SecretStr("my-secret-api-key")

    # 测试加密
    encrypted = cipher.encrypt(secret)
    assert encrypted is not None
    assert encrypted != secret.get_secret_value()
    assert isinstance(encrypted, str)

    # 测试解密
    decrypted = cipher.decrypt(encrypted)
    assert decrypted is not None
    assert decrypted.get_secret_value() == secret.get_secret_value()


def test_cipher_encrypt_none():
    """测试加密 None 返回 None。"""
    key = urlsafe_b64encode(b"a" * 32).decode("ascii")
    cipher = Cipher(key)

    result = cipher.encrypt(None)
    assert result is None


def test_cipher_decrypt_none():
    """测试解密 None 返回 None。"""
    key = urlsafe_b64encode(b"a" * 32).decode("ascii")
    cipher = Cipher(key)

    result = cipher.decrypt(None)
    assert result is None


def test_cipher_decrypt_invalid_data():
    """测试解密无效数据是否返回 None 并记录警告。"""
    key = urlsafe_b64encode(b"a" * 32).decode("ascii")
    cipher = Cipher(key)

    # 使用完全无效的数据进行测试
    result = cipher.decrypt("invalid-encrypted-data")
    assert result is None

    # 使用格式错误的 base64 进行测试
    result = cipher.decrypt("not-base64!")
    assert result is None


def test_cipher_decrypt_wrong_key():
    """测试使用错误密钥解密是否返回 None 并记录警告。"""
    # 创建两个不同的密钥
    key1 = urlsafe_b64encode(b"a" * 32).decode("ascii")
    key2 = urlsafe_b64encode(b"b" * 32).decode("ascii")

    cipher1 = Cipher(key1)
    cipher2 = Cipher(key2)

    secret = SecretStr("test-secret")

    # 使用第一个密码进行加密
    encrypted = cipher1.encrypt(secret)
    assert encrypted is not None

    # 尝试用第二个密码解密（密钥错误）
    result = cipher2.decrypt(encrypted)
    assert result is None


def test_cipher_fernet_caching():
    """测试 Fernet 实例是否正确缓存。"""
    key = urlsafe_b64encode(b"a" * 32).decode("ascii")
    cipher = Cipher(key)

    # 获取 Fernet 实例两次
    fernet1 = cipher._get_fernet()
    fernet2 = cipher._get_fernet()

    # 应该是同一个实例（缓存）
    assert fernet1 is fernet2
    assert isinstance(fernet1, Fernet)


def test_cipher_with_real_fernet_key():
    """使用 Fernet 生成的真实密钥测试密码。"""
    # 生成正确的 Fernet 密钥
    fernet_key = Fernet.generate_key()
    key = fernet_key.decode("ascii")

    cipher = Cipher(key)
    secret = SecretStr("test-api-key-12345")

    # 测试往返加密/解密
    encrypted = cipher.encrypt(secret)
    decrypted = cipher.decrypt(encrypted)

    assert decrypted is not None
    assert decrypted.get_secret_value() == secret.get_secret_value()


def test_cipher_multiple_encryptions_different():
    """测试相同值的多次加密是否会产生不同的结果。"""
    key = urlsafe_b64encode(b"a" * 32).decode("ascii")
    cipher = Cipher(key)

    secret = SecretStr("same-secret")

    # 多次加密相同的机密
    encrypted1 = cipher.encrypt(secret)
    encrypted2 = cipher.encrypt(secret)

    # 结果应该不同（由于 Fernet 内置的随机性）
    assert encrypted1 != encrypted2

    # 但两者都应该解密为相同的值
    decrypted1 = cipher.decrypt(encrypted1)
    decrypted2 = cipher.decrypt(encrypted2)

    assert decrypted1 is not None
    assert decrypted2 is not None

    assert decrypted1.get_secret_value() == secret.get_secret_value()
    assert decrypted2.get_secret_value() == secret.get_secret_value()


def test_cipher_empty_string():
    """测试空字符串的加密/解密。"""
    key = urlsafe_b64encode(b"a" * 32).decode("ascii")
    cipher = Cipher(key)

    secret = SecretStr("")

    encrypted = cipher.encrypt(secret)
    assert encrypted is not None
    assert encrypted != ""

    decrypted = cipher.decrypt(encrypted)
    assert decrypted is not None
    assert decrypted.get_secret_value() == ""


def test_cipher_unicode_content():
    """测试 unicode 内容的加密/解密。"""
    key = urlsafe_b64encode(b"a" * 32).decode("ascii")
    cipher = Cipher(key)

    secret = SecretStr("🔐 Secret with émojis and ñoñ-ASCII chars! 中文")

    encrypted = cipher.encrypt(secret)
    decrypted = cipher.decrypt(encrypted)

    assert decrypted is not None
    assert decrypted.get_secret_value() == secret.get_secret_value()


def test_cipher_long_content():
    """测试长内容的加密/解密。"""
    key = urlsafe_b64encode(b"a" * 32).decode("ascii")
    cipher = Cipher(key)

    # 创建一个长的机密 (1KB)
    long_secret = "x" * 1024
    secret = SecretStr(long_secret)

    encrypted = cipher.encrypt(secret)
    decrypted = cipher.decrypt(encrypted)

    assert decrypted is not None
    assert decrypted.get_secret_value() == long_secret


def test_cipher_decrypts_with_previous_key_and_encrypts_with_current():
    old = Cipher("old-key")
    token = old.encrypt(SecretStr("value"))
    assert token is not None

    rotated = Cipher("new-key", previous_keys=["old-key"])
    decrypted = rotated.decrypt(token)
    assert decrypted is not None
    assert decrypted.get_secret_value() == "value"
    assert rotated.try_decrypt_str(token) == "value"
    assert not rotated.is_current(token)

    fresh = rotated.encrypt(SecretStr("value"))
    assert fresh is not None
    assert rotated.is_current(fresh)
    # 新的 token 仅位于新密钥下：旧密钥无法读取它。
    assert old.decrypt(fresh) is None
    assert Cipher("new-key").try_decrypt_str(fresh) == "value"


def test_cipher_rotate():
    token = Cipher("old-key").encrypt(SecretStr("value"))
    assert token is not None
    rotated = Cipher("new-key", previous_keys=["older-key", "old-key"])

    new_token = rotated.rotate(token)
    assert new_token is not None and new_token != token
    assert rotated.is_current(new_token)
    # 轮换后，不再需要之前的密钥。
    assert Cipher("new-key").try_decrypt_str(new_token) == "value"
    # 已在当前键下的 token 将原样返回。
    assert rotated.rotate(new_token) == new_token
    # 没有配置的密钥可以解密它：没有可旋转的对象。
    assert Cipher("new-key", previous_keys=["other"]).rotate(token) is None


def test_cipher_without_the_old_key_cannot_decrypt():
    token = Cipher("old-key").encrypt(SecretStr("value"))
    assert token is not None
    cipher = Cipher("new-key", previous_keys=["unrelated"])
    assert cipher.decrypt(token) is None
    assert cipher.try_decrypt_str(token) is None


def test_cipher_previous_keys_drop_blanks_and_the_current_key():
    cipher = Cipher("k", previous_keys=["", "  ", "k", "a", "a", "b"])
    assert cipher.previous_keys == ("a", "b")
