<a id="llm-utils-guidelines"></a>

# LLM 实用程序指南

有关包范围的策略，请参阅 [SDK AGENTS.md](../../AGENTS.md)。

<a id="verified-model-lists-verified_modelspy"></a>

## 已验证的型号列表 (`verified_models.py`)

这些列表是一组精心策划的运行良好的模型，而不是提供商提供的所有内容的目录。 保持简短。

- 对于每个型号系列，仅保留**两个最新版本**（例如`gpt-6`和`gpt-5.6`； `claude-opus-5-5`和`claude-opus-5`）。
- 保留版本的变体（`-pro`、`-mini`、`-codex`、`-flash`、带日期的别名）保留在该版本中。 未版本控制的“当前”别名（`deepseek-chat`、`kimi-for-coding`）保留。
- 添加新版本时，请删除同一行中出现的每个列表（提供程序列表和 `VERIFIED_OPENHANDS_MODELS`）中最旧的版本。
- `VERIFIED_OPENHANDS_MODELS` 中的每个条目也必须出现在提供商列表中，除非它仅限于 OpenHands； `tests/sdk/llm/test_model_list.py`对此进行了检查。
- 不要仅仅因为 LiteLLM 或 OpenRouter 知道而添加模型。 未经验证的目录（`unverified_models.py`）涵盖了这一点。
- `openrouter` 是经过验证的提供商。 它的条目是实际的 OpenRouter id，删除了 `openrouter/` 前缀（因此 `anthropic/claude-opus-5` 对应于 `openrouter/anthropic/claude-opus-5`），因为 OpenRouter 命名空间每个模型都在其上游供应商下。 不要求这些路线出现在LiteLLM的成本图中； OpenRouter 的端点 API 提供运行时上下文限制。 仅保留 OpenHands 代理服务的边界路线，而不保留 OpenRouter 的完整目录。
