<a id="openai-compatible-gateway"></a>

# OpenAI兼容网关

该包包含 `/v1` 下与 OpenAI 兼容的 API 表面的智能体服务器实现。

- `router.py` 定义 FastAPI 路由并将 OpenAI 式承载身份验证映射到现有会话密钥机制。
- `models.py` 包含小型服务器端请求模型和可重用的 OpenAI 响应模型的别名。
- `service.py` 将聊天完成和响应请求转换为 OpenHands 对话，等待完成，并返回 OpenAI 形状的响应。

`POST /v1/responses` 实现无状态客户端流：每次请求都会启动一个新的 OpenHands 对话，客户端携带上下文通过回放输入和输出项来前进 `store: false`. `previous_response_id` 直到网关能够保留精确响应-转行和分支语义，否则将被拒绝。

响应界面尚不支持：

- `previous_response_id` 被 `400` 拒绝； 相反，重播输入项目。
- `store: true` 被 `400` 拒绝，因为网关不保留可检索的响应对象或实现 `GET /v1/responses/{id}`。 支持 OpenHands 会话仍然遵循智能体服务器的正常持久化策略，因此 `store: false` 不是数据保留控制。
- `stream: true` 被 `400` 拒绝（类型流式传输事件属于后续范围）。
- `tools`、`tool_choice` 和 `parallel_tool_calls` 被接受但被忽略； OpenHands 工具执行保留在智能体内部。 `temperature` 和其他生成调整字段同样被忽略。 这些被丢弃而不是被拒绝，因为它们不会破坏无状态默认流，但客户端不应该依赖它们产生效果。

网关故意与本地的智能体-服务器路由器保持分离，以便OpenAI兼容层可以进化，而不将协议翻译代码混入核心REST和API模块。
