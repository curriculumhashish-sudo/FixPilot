"""Example: 使用 LLMProfileStore 保存和重用 LLM 配置。

此示例附带一个预生成的配置文件 JSON 文件，并在运行时创建另一个配置文件。 签入的配置文
件来自正常保存，因此机密被屏蔽而不是暴露，并且非机密字段（如
`base_url`）在存在时被保留。
"""

import os
import shutil
import tempfile
from pathlib import Path

from pydantic import SecretStr

from openhands.sdk import LLM, LLMProfileStore


SCRIPT_DIR = Path(__file__).parent
EXAMPLE_PROFILES_DIR = SCRIPT_DIR / "profiles"
DEFAULT_MODEL = "gpt-5.5"


profile_store_dir = Path(tempfile.mkdtemp()) / "profiles"
shutil.copytree(EXAMPLE_PROFILES_DIR, profile_store_dir)
store = LLMProfileStore(base_dir=profile_store_dir)

print(f"Seeded profiles: {store.list()}")

api_key = os.getenv("LLM_API_KEY")
creative_llm = LLM(
    usage_id="creative",
    model=os.getenv("LLM_MODEL", DEFAULT_MODEL),
    api_key=SecretStr(api_key) if api_key else None,
    base_url=os.getenv("LLM_BASE_URL"),
    temperature=0.9,
)

# 签入的 fast.json 是通过正常保存生成的，因此它的 api_key 被屏蔽，并且任何配置的
# base_url 将被保留。 此运行时配置文件还避免保留真实的 API 键，因为默认情况下机密被屏蔽
# 。
#
store.save("creative", creative_llm)
creative_profile_json = (profile_store_dir / "creative.json").read_text()
if api_key is not None:
    assert api_key not in creative_profile_json

print(f"Stored profiles: {store.list()}")

fast_profile = store.load("fast")
creative_profile = store.load("creative")

print(
    "Loaded fast profile. "
    f"usage: {fast_profile.usage_id}, "
    f"model: {fast_profile.model}, "
    f"temperature: {fast_profile.temperature}."
)
print(
    "Loaded creative profile. "
    f"usage: {creative_profile.usage_id}, "
    f"model: {creative_profile.model}, "
    f"temperature: {creative_profile.temperature}."
)

store.delete("creative")
print(f"After deletion: {store.list()}")

print("EXAMPLE_COST: 0")
