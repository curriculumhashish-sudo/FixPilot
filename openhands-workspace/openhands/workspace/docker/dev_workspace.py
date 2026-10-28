"""Docker 开发工作区具有即时图像构建功能。"""

from pydantic import Field, model_validator

from openhands.sdk.workspace import PlatformType, TargetType

from .workspace import DockerWorkspace


class DockerDevWorkspace(DockerWorkspace):
    """Docker 工作区具有即时图像构建功能。

    此工作区扩展了 DockerWorkspace 以支持从基础映像即时构建 Docker 映像。 这对于需要
    自定义 Agent Server 环境的开发和测试场景非常
    有用。

    Note: 该类需要 OpenHands SDK 工作区结构并且应该
    仅可在 OpenHands 开发环境中或当您拥有完整的 SDK 源代码时使用。

    对于具有预构建图像的生产用例，请改用 DockerWorkspace。

    Example:
        with DockerDevWorkspace(
            base_image="python:3.13",
            target="source"
        ) 作为工作区：
            result = workspace.execute_command("ls -la")
    """

    # 将父级的 server_image 默认值覆盖为 None，以便提供 base_image 的调用者不需要显式传
    # 递 server_image=None。
    #
    server_image: str | None = Field(
        default=None,
        description="Pre-built agent server image. Mutually exclusive with base_image.",
    )

    # 添加 base_image 支持
    base_image: str | None = Field(
        default=None,
        description=(
            "Base Docker image to build the agent server from. "
            "Mutually exclusive with server_image."
        ),
    )

    # 添加特定于构建的选项
    target: TargetType = Field(
        default="source", description="Build target for the Docker image."
    )

    @model_validator(mode="after")
    def _validate_images(self):
        """确保准确提供 base_image 或 server_image 之一。"""
        if (self.base_image is None) == (self.server_image is None):
            raise ValueError(
                "Exactly one of 'base_image' or 'server_image' must be set."
            )
        if self.base_image and "ghcr.io/openhands/agent-server" in self.base_image:
            raise ValueError(
                "base_image cannot be a pre-built agent-server image. "
                "Use server_image=... instead."
            )
        return self

    @staticmethod
    def _build_image_from_base(
        *, base_image: str, target: TargetType, platform: PlatformType
    ) -> str:
        """从基础镜像构建 Docker 镜像。

        Args:
            base_image: 用于构建的基础 Docker 图像。
            target: 构建目标（e.g., 'source', 'dev'）。
            platform: 要构建的平台 (e.g., 'linux/amd64')。

        Returns:
            内置的Docker图像标签。

        Raises:
            RuntimeError: 如果 base_image 是预构建的智能体-服务器映像
                或者如果构建失败。
        """
        from openhands.agent_server.docker.build import BuildOptions, build

        if "ghcr.io/openhands/agent-server" in base_image:
            raise RuntimeError(
                "base_image cannot be a pre-built agent-server image. "
                "Use server_image=... instead."
            )

        build_opts = BuildOptions(
            base_image=base_image,
            target=target,
            platforms=[platform],
            push=False,
        )
        tags = build(opts=build_opts)
        if not tags:
            raise RuntimeError("Build failed, no image tags returned")
        return tags[0]

    def get_image(self) -> str:
        """如果提供了 base_image，则构建图像，否则使用 server_image。

        这会覆盖父方法以添加即时图像构建功能。

        Returns:
            要使用的 Docker 图像标签。
        """
        if self.base_image:
            # 从 base_image 构建图像
            return self._build_image_from_base(
                base_image=self.base_image,
                target=self.target,
                platform=self.platform,
            )
        elif self.server_image:
            # 使用预先构建的图像
            return self.server_image
        else:
            raise ValueError("Either base_image or server_image must be set")
