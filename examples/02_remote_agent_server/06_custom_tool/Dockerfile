# 使用自定义工具自定义基础镜像的 Dockerfile
#
# 此 Dockerfile 创建一个包含自定义工具的基础映像。
# 当与 DockerDevWorkspace(base_image=..., target="binary") 一起使用时，
# 二进制 Agent Server 将自动构建在此图像之上。
#
# 用途：
#   cd examples/02_remote_agent_server/06_custom_tool
#   docker build -t custom-base-image:latest .

FROM nikolaik/python-nodejs:python3.13-nodejs24-slim

# 将自定义工具复制到冻结二进制文件之外的目录中。
COPY custom_tools /app/custom_tools

# 告诉二进制文件 Agent Server 在哪里可以找到外部 Python 模块。
ENV OH_EXTRA_PYTHON_PATH="/app"
