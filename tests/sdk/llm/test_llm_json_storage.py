"""测试 LLM JSON 存储和加载功能。"""

import json
import tempfile
from pathlib import Path

from pydantic import SecretStr

from openhands.sdk.llm import LLM


def test_llm_store_and_load_json():
    """测试将 LLM 存储到 JSON 并在字段不变的情况下加载回来。"""
    # 使用机密创建原始 LLM
    original_llm = LLM(
        usage_id="test-llm",
        model="test-model",
        temperature=0.7,
        max_output_tokens=2000,
        top_p=0.9,
        api_key=SecretStr("secret-api-key"),
        aws_access_key_id=SecretStr("aws-access-key"),
        aws_secret_access_key=SecretStr("aws-secret-key"),
        base_url="https://api.example.com",
        num_retries=3,
    )

    # 存储到 JSON 并加载回来
    with tempfile.TemporaryDirectory() as temp_dir:
        filepath = Path(temp_dir) / "test_llm.json"

        # 存储到 JSON，机密暴露
        data = original_llm.model_dump(context={"expose_secrets": True})
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        loaded_llm = LLM.load_from_json(str(filepath))

        # 验证所有字段保持不变
        assert loaded_llm.model == original_llm.model
        assert loaded_llm.temperature == original_llm.temperature
        assert loaded_llm.max_output_tokens == original_llm.max_output_tokens
        assert loaded_llm.top_p == original_llm.top_p
        assert loaded_llm.base_url == original_llm.base_url
        assert loaded_llm.num_retries == original_llm.num_retries

        # 验证机密已保留
        assert loaded_llm.api_key is not None
        assert loaded_llm.aws_access_key_id is not None
        assert loaded_llm.aws_secret_access_key is not None
        assert original_llm.api_key is not None
        assert original_llm.aws_access_key_id is not None
        assert original_llm.aws_secret_access_key is not None
        assert isinstance(loaded_llm.api_key, SecretStr)
        assert isinstance(original_llm.api_key, SecretStr)
        assert isinstance(loaded_llm.aws_access_key_id, SecretStr)
        assert isinstance(original_llm.aws_access_key_id, SecretStr)
        assert isinstance(loaded_llm.aws_secret_access_key, SecretStr)
        assert isinstance(original_llm.aws_secret_access_key, SecretStr)
        assert (
            loaded_llm.api_key.get_secret_value()
            == original_llm.api_key.get_secret_value()
        )
        assert (
            loaded_llm.aws_access_key_id.get_secret_value()
            == original_llm.aws_access_key_id.get_secret_value()
        )
        assert (
            loaded_llm.aws_secret_access_key.get_secret_value()
            == original_llm.aws_secret_access_key.get_secret_value()
        )
