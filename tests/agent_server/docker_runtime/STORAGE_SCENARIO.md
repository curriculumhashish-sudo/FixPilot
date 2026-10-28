<a id="storage-reclaim-scenario-docker-runtime"></a>

# 存储回收场景（Docker运行时）

Docker-模式智能体-服务器必须如何处理其对话留下的存储。 更改 `openhands/agent_server/storage/` 后运行它或
`docker_runtime/`，或碰撞智能体服务器映像时。

<a id="automated"></a>

## 自动化

需要一个正在运行的 Docker 守护进程和智能体服务器映像（已拉取，未构建）：

```
docker pull ghcr.io/openhands/agent-server:latest-python
uv run pytest -m docker_live tests/agent_server/docker_runtime/test_storage_scenario.py
```

`OH_STORAGE_SCENARIO_IMAGE` 选择另一个图像，e.g。 一个是用树枝建造的。 默认情况下取消选择测试（`docker_live` 标记），并在 Docker 或图像丢失时跳过。

每个测试都通过 `OH_*` 环境变量配置服务器，就像 CLI 一样，并驱动真实的容器。 每个人都会检查什么必须生存，以及什么必须消失：

1. **仅可重建文件。**两个对话写入缓存、shell 历史记录、配置文件、带有未跟踪注释的已提交存储库、被忽略的存储库
   `.env`、`node_modules/`、`.venv/`、`build/`、被忽略的克隆
   `vendor/`，以及带有自己的 `node_modules/` 的嵌套结账。 停止其中一个只会掉落其 `~/.cache` 和 `~/.npm`。 传递磁盘预算后，将删除其四个依赖目录，而不会删除其他任何内容。 正在运行的对话逐个文件都没有改变。
2. **植入的链接已被删除，从未被关注。**沙箱指向 `~/.npm` 和运行时外部主机路径中被忽略的 `build/` 内的链接，以及
   `~/.cache` 位于主机上自己的工作区中的相对路径。 链接和`build/`去； 所有目标都存活下来。
3. **来电者提供的工作区永远不会被丢弃**，即使超出预算； 沙箱自己的缓存仍然存在。
4. **重置对话继续进行，工作正常**阅读一个工作区通过文件 API 重启它，它的提交在那里，它可以再次写入缓存和依赖项。
5. **一个已归档的对话是只读直到删除** （保留1天，1天前的对话）：运行时已消失，历史仍然可读，运行时返回410，最近的保留，删除仍然删除所有。

工作区：调用者规则或410都会失败匹配测试。

<a id="by-hand"></a>

## 手工

针对真实服务器，当测试本身有疑问时。 从空目录运行； 服务器将所有内容保留在 `./workspace/` 下。

```
OH_SECRET_KEY=$(openssl rand -hex 32) OH_CONVERSATION_RUNTIME=docker \
  OH_CONVERSATION_STORAGE_DISK_BUDGET=0.01 \
  uv run --project <sdk checkout> python -m openhands.agent_server --port 8000
```

`0.01` 使任何实际磁盘超出预算。 在第二个 shell 中，启动两个对话并编写安装内容。 运行时目录已绑定
mounts: `persistence/` 是沙箱的 `$HOME`，`workspace/` 是沙箱的 `/workspace`。

```
start() {
  curl -s localhost:8000/api/conversations -H 'content-type: application/json' \
    -d '{"agent": {"kind": "Agent", "llm": {"model": "test"}, "tools": []}}' | jq -r .id
}
A=$(start); B=$(start)
for id in $A $B; do
  dir=workspace/.openhands/runtime-data/${id//-/}
  mkdir -p $dir/persistence/.cache/uv $dir/workspace/node_modules/left-pad
  echo x > $dir/persistence/.cache/uv/wheel.whl
  echo 1 > $dir/workspace/node_modules/left-pad/index.js
  echo 'print(1)' > $dir/workspace/main.py
  (cd $dir/workspace && git init -q && echo node_modules/ > .gitignore)
done
curl -s -X DELETE localhost:8000/api/conversations/$A/runtime
```

预计：

- 停止后，A 的 `persistence/.cache` 消失了，它的
  `workspace/node_modules` 仍然存在。
- 五分钟内（维护间隔）服务器记录
  `Conversation storage: freed …`，而A的`workspace/node_modules`没有了；
  `main.py` 和 `.gitignore` 保留。
- B 在运行时保留所有内容。
