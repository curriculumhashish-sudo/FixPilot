"""已知与 OpenHands 配合良好的模型的精选列表。

这些列表提供模型选择器 (智能体-服务器 ``/llm/verified-models``) 和 ``openhands/`` 提
供商允许列表。 它们应该很短。

Rule: 对于每个型号系列，仅保留两个最新版本。 保留的变体
版本（``-pro``、``-mini``、``-codex``、``-flash``、带日期的别名）保留。 未版本化的“当
前”别名（例如
``deepseek-chat``、``kimi-for-coding``）保留。 当新版本发布时，将最旧的版本放在同一行
中。
"""

# GPT：gpt-6 和 gpt-5.6。 法典：gpt-5.3-codex 和 gpt-5.2-codex。
VERIFIED_OPENAI_MODELS = [
    "gpt-6.1-sol",
    "gpt-6-sol",
    "gpt-6-luna",
    "gpt-6-astra",
    "gpt-5.6",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
    "gpt-5.3-codex",
    "gpt-5.2-codex",
]

# 作品：5.5 和 5。 十四行诗：5.5 和 5。 俳句：5.5 和 4.5。 寓言：5.1和5。
VERIFIED_ANTHROPIC_MODELS = [
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-sonnet-5-5",
    "claude-sonnet-5",
    "claude-haiku-5-5",
    "claude-haiku-4-5-20251001",
    "claude-fable-5-1",
    "claude-fable-5",
]

# Devstral 2512（两种尺寸）。
VERIFIED_MISTRAL_MODELS = [
    "devstral-2512",
    "devstral-medium-2512",
]

# 氩气：4。 优点：3.1。 闪存：3.8 和 3.7。 Flash-lite：3.5 和 3.1。
VERIFIED_GEMINI_MODELS = [
    "gemini-4-argon",
    "gemini-3.1-pro",
    "gemini-3.1-pro-preview",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]

# V4和V3.2； ``deepseek-chat`` 是当前别名。
VERIFIED_DEEPSEEK_MODELS = [
    "deepseek-chat",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
    "deepseek-v4-flash-vision-exp",
    "deepseek-v4.1-flash",
    "deepseek-v3.2-reasoner",
]

# 基米K3和K2.7； ``kimi-for-coding`` 是 Moonshot 自己的别名（仅直接 API； OpenHands 代理
# 不为其提供服务，因此它不在 OpenHands 列表中）。
#
VERIFIED_MOONSHOT_MODELS = [
    "kimi-k3",
    "kimi-k2.7-code",
    "kimi-for-coding",
]

# M3（包括闪光灯）和 M2.7。
VERIFIED_MINIMAX_MODELS = [
    "minimax-m3.1-flash",
    "minimax-m3",
    "minimax-m2.7",
]

# GLM5.3和5.2。
VERIFIED_GLM_MODELS = [
    "glm-5.3",
    "glm-5.3-flash",
    "glm-5.2",
]

# Nemotron 3.5 和 3。
VERIFIED_NVIDIA_MODELS = [
    "nemotron-3.5-lightning-30b-a3b",
    "nemotron-3-nano",
    "nemotron-3-nano-omni-30b-a3b-reasoning",
    "nemotron-3-super-120b-a12b",
    "nemotron-3-ultra-550b-a55b",
]

# 加：3.7 和 3.6。 最大值：3.8 和 3.7。 闪存：3.8 和 3.7。 编码器：未版本化。
VERIFIED_QWEN_MODELS = [
    "qwen3.7-plus",
    "qwen3.6-plus",
    "qwen3.8-max",
    "qwen3.7-max",
    "qwen3.8-flash",
    "qwen3.7-flash",
    "qwen3-coder-480b",
    "qwen3-coder-next",
    "qwen3-coder-plus",
    "qwen3-coder-flash",
]

# OpenRouter路由其他供应商的模型。 条目是删除了 ``openrouter/`` 前缀的 OpenRouter id（因
# 此这里的 ``anthropic/claude-opus-5`` 对应于 ``openrouter/anthropic/claude-opus-5``）。
#  使用 OpenRouter 的实际模型 ID 仅保留 OpenHands 代理服务的边界路由。
#
VERIFIED_OPENROUTER_MODELS = [
    "anthropic/claude-opus-5",
    "anthropic/claude-sonnet-5.5",
    "anthropic/claude-sonnet-5",
    "anthropic/claude-haiku-5.5",
    "anthropic/claude-haiku-4.5",
    "openai/gpt-6.1-sol",
    "openai/gpt-6-astra",
    "openai/gpt-5.6-sol",
    "openai/gpt-5.3-codex",
    "openai/gpt-5.2-codex",
    "deepseek/deepseek-chat",
    "deepseek/deepseek-v4-pro",
    "deepseek/deepseek-v4-flash",
    "google/gemini-4-argon",
    "google/gemini-3.1-pro-preview",
    "google/gemini-3.8-flash",
    "google/gemini-3.7-flash",
    "google/gemini-3.5-flash-lite",
    "moonshotai/kimi-k3",
    "moonshotai/kimi-k2.7-code",
    "mistralai/devstral-2512",
    "z-ai/glm-5.3",
    "z-ai/glm-5.3-flash",
    "z-ai/glm-5.2",
    "minimax/minimax-m3",
]

# DigitalOcean 推理 ID (``GET https://inference.do-ai.run/v1/models``)。 仅包含工具调用
# 的聊天完成模型：gpt-6 行需要工具的响应 API，因此被排除在外。
#
VERIFIED_DIGITALOCEAN_MODELS = [
    "anthropic-claude-opus-5.5",
    "anthropic-claude-opus-5",
    "anthropic-claude-sonnet-5.5",
    "anthropic-claude-5-sonnet",
    "openai-gpt-5.6-sol",
    "openai-gpt-5.6-terra",
    "openai-gpt-5.6-luna",
    "deepseek-v4-pro",
    "glm-5.3",
    "glm-5.2",
    "kimi-k3",
    "qwen3.8-max",
]

# ``openhands/`` 提供商提供的服务。 规则相同； 除仅限 OpenHands 的型号外，每个条目还必须
# 位于上面的提供程序列表中。
#
VERIFIED_OPENHANDS_MODELS = [
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-sonnet-5-5",
    "claude-sonnet-5",
    "claude-fable-5-1",
    "claude-fable-5",
    "gpt-6.1-sol",
    "gpt-6-sol",
    "gpt-6-luna",
    "gpt-6-astra",
    "gpt-5.6",
    "gpt-5.3-codex",
    "gpt-5.2-codex",
    "minimax-m3.1-flash",
    "minimax-m3",
    "minimax-m2.7",
    "gemini-3.1-pro",
    "gemini-3.1-pro-preview",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash-lite",
    "deepseek-chat",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
    "deepseek-v4-flash-vision-exp",
    "deepseek-v4.1-flash",
    "deepseek-v3.2-reasoner",
    "kimi-k3",
    "kimi-k2.7-code",
    "devstral-2512",
    "devstral-medium-2512",
    "glm-5.3",
    "glm-5.3-flash",
    "glm-5.2",
    "nemotron-3.5-lightning-30b-a3b",
    "nemotron-3-nano",
    "nemotron-3-super-120b-a12b",
    "nemotron-3-ultra-550b-a55b",
    "qwen3.7-plus",
    "qwen3.6-plus",
    "qwen3.8-max",
    "qwen3.7-max",
    "qwen3.8-flash",
    "qwen3.7-flash",
    "qwen3-coder-480b",
    "qwen3-coder-next",
    "qwen3-coder-plus",
    "qwen3-coder-flash",
    "trinity-large-thinking",
]


VERIFIED_MODELS = {
    "openhands": VERIFIED_OPENHANDS_MODELS,
    "anthropic": VERIFIED_ANTHROPIC_MODELS,
    "openai": VERIFIED_OPENAI_MODELS,
    "mistral": VERIFIED_MISTRAL_MODELS,
    "gemini": VERIFIED_GEMINI_MODELS,
    "deepseek": VERIFIED_DEEPSEEK_MODELS,
    "moonshot": VERIFIED_MOONSHOT_MODELS,
    "minimax": VERIFIED_MINIMAX_MODELS,
    "glm": VERIFIED_GLM_MODELS,
    "nvidia": VERIFIED_NVIDIA_MODELS,
    "qwen": VERIFIED_QWEN_MODELS,
    "openrouter": VERIFIED_OPENROUTER_MODELS,
    "digitalocean": VERIFIED_DIGITALOCEAN_MODELS,
}
