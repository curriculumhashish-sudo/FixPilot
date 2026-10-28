#!/bin/bash
# 使用自定义工具构建自定义基础映像的脚本
#
# 此脚本构建一个自定义基础映像，其中包括自定义工具和集 OH_EXTRA_PYTHON_PATH，以便二进制文件 Agent Server 可以导入它们。 当与 DockerDevWorkspace(base_image=..., target="binary") 一起使用时，Agent Server 将自动构建在此图像之上。
#
# 用途：
#   ./build_custom_image.sh [TAG]
#
# Arguments:
#   TAG：图像的可选自定义标签（默认值：custom-base-image:latest）

set -e

# 获取该脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 默认标签
TAG="${1:-custom-base-image:latest}"

echo "🐳 Building custom base image with custom tools and OH_EXTRA_PYTHON_PATH..."
echo "🏷️  Tag: $TAG"
echo "📂 Build context: $SCRIPT_DIR"
echo ""

# 从示例目录构建镜像 Dockerfile 只是将 custom_tools 复制到基础镜像中
#
docker build \
  -t "$TAG" \
  "$SCRIPT_DIR"

echo ""
echo "✅ Custom base image built successfully!"
echo "🏷️  Image tag: $TAG"
echo ""
echo "To use this image:"
echo "  1. Use in SDK with DockerDevWorkspace:"
echo "     with DockerDevWorkspace("
echo "         base_image='$TAG',"
echo "         host_port=8010,"
echo "         target='binary',"
echo "     ) as workspace:"
echo "         # The image sets OH_EXTRA_PYTHON_PATH for custom tool imports"
echo "         # your code"
echo ""
echo "  2. Push to registry (optional):"
echo "     docker tag $TAG your-registry/$TAG"
echo "     docker push your-registry/$TAG"
