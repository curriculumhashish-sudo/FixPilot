"""Canvas 扩展清单：模式、验证和入口遏制。

Canvas 扩展是一个可安装的 UI 包，它向 OpenHands Canvas 前端提供页面。 扩展完全由智能
体服务器安装和提供服务（通过
``openhands.sdk.extensions.installation``，插件/技能使用相同的类型不可知安装跟踪框架
）； 这里没有任何东西被 ``Agent``
/``Conversation``. 消耗

该模块定义了清单模式 (``canvas-extension.json``) 及其周围的两个安全关键检查：

* 名称/贡献 ID/页面路径验证（语法，在模型上）。
* 入口遏制（文件系统级，一旦知道包根）——拒绝文本路径遍历和符号链接转义。
"""

import re
from pathlib import Path
from typing import Final, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

from openhands.sdk.extensions.installation.utils import validate_extension_name
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


# 画布扩展的清单从其包根加载的文件名。
MANIFEST_FILENAME: Final[str] = "canvas-extension.json"

# 绝对、kebab-case、多段 UI 路线，e.g。 "/dashboard/settings".
_PAGE_PATH_PATTERN: re.Pattern[str] = re.compile(
    r"^/[a-z0-9]+(?:-[a-z0-9]+)*(?:/[a-z0-9]+(?:-[a-z0-9]+)*)*$"
)


class CanvasExtensionPage(BaseModel):
    """通过扩展向 Canvas UI 提供单个页面。"""

    id: str = Field(description="Unique contribution id within the extension")
    title: str = Field(description="Page title shown in Canvas navigation")
    path: str = Field(description="Route the page is mounted at, e.g. '/dashboard'")

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        try:
            validate_extension_name(v)
        except ValueError as e:
            raise ValueError(
                f"Invalid contribution id. Expected kebab-case, got {v!r}."
            ) from e
        return v

    @field_validator("path")
    @classmethod
    def _validate_path(cls, v: str) -> str:
        if not _PAGE_PATH_PATTERN.fullmatch(v):
            raise ValueError(
                "Invalid page path. Expected an absolute kebab-case route "
                f"(e.g. '/dashboard'), got {v!r}."
            )
        return v


class CanvasExtensionContributes(BaseModel):
    """贡献 Canvas UI 的扩展。"""

    pages: list[CanvasExtensionPage] = Field(
        default_factory=list, description="Pages contributed to Canvas navigation"
    )

    @field_validator("pages")
    @classmethod
    def _validate_unique_pages(
        cls, v: list[CanvasExtensionPage]
    ) -> list[CanvasExtensionPage]:
        seen_ids: set[str] = set()
        seen_paths: set[str] = set()
        for page in v:
            if page.id in seen_ids:
                raise ValueError(f"Duplicate page contribution id: {page.id!r}")
            if page.path in seen_paths:
                raise ValueError(f"Duplicate page path: {page.path!r}")
            seen_ids.add(page.id)
            seen_paths.add(page.path)
        return v


BackendPlatform = Literal["linux-amd64", "linux-arm64"]


class CanvasExtensionBackendArtifact(BaseModel):
    """一个平台的不可变本地或 HTTPS 后端工件。"""

    path: str = Field(description="Package-relative .tar.gz artifact path")
    url: str | None = Field(
        default=None, description="Public HTTPS .tar.gz artifact URL"
    )
    sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$", description="Lowercase SHA-256 checksum"
    )
    strip_components: int = Field(
        default=0, ge=0, le=16, description="Leading archive path components to remove"
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_remote_path(cls, value: object) -> object:
        if isinstance(value, dict) and "path" not in value and value.get("url"):
            return {**value, "path": ""}
        return value

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        if value and (
            value.startswith("/")
            or ".." in Path(value).parts
            or not value.endswith(".tar.gz")
        ):
            raise ValueError("artifact path must be a relative .tar.gz path")
        return value

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or not parsed.path.endswith(".tar.gz")
        ):
            raise ValueError("artifact url must be a credential-free HTTPS .tar.gz URL")
        return value

    @model_validator(mode="after")
    def _validate_source(self) -> "CanvasExtensionBackendArtifact":
        if bool(self.path) == (self.url is not None):
            raise ValueError("artifact must declare exactly one of path or url")
        if self.path and self.strip_components:
            raise ValueError("strip_components is supported only for remote artifacts")
        return self


class CanvasExtensionBackendHealth(BaseModel):
    """后端进程的环回 HTTP 就绪探测。"""

    path: str = Field(default="/health", pattern=r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*$")
    timeout_seconds: float = Field(default=30, gt=0, le=300)
    interval_seconds: float = Field(default=0.1, gt=0, le=10)


class CanvasExtensionBackend(BaseModel):
    """模式-1 Canvas 应用程序的可选可信后端声明。"""

    schema_version: Literal[1]
    artifacts: dict[BackendPlatform, CanvasExtensionBackendArtifact] = Field(
        min_length=1
    )
    argv: list[str] = Field(min_length=1)
    health: CanvasExtensionBackendHealth = Field(
        default_factory=CanvasExtensionBackendHealth
    )
    inherit_environment: list[str] = Field(default_factory=list)

    @field_validator("argv")
    @classmethod
    def _validate_argv(cls, value: list[str]) -> list[str]:
        allowed = {"{port}", "{data_dir}", "{artifact_dir}"}
        for argument in value:
            if not argument or "\x00" in argument:
                raise ValueError("backend argv entries must be non-empty")
            placeholders = set(re.findall(r"\{[^{}]+\}", argument))
            if not placeholders.issubset(allowed):
                raise ValueError("backend argv contains an unsupported placeholder")
        return value

    @field_validator("inherit_environment")
    @classmethod
    def _validate_environment(cls, value: list[str]) -> list[str]:
        allowed = {"LANG", "LC_ALL", "LC_CTYPE", "PATH", "TMPDIR", "TZ"}
        if len(value) != len(set(value)):
            raise ValueError("inherit_environment entries must be unique")
        if not set(value).issubset(allowed):
            raise ValueError("inherit_environment contains a disallowed variable")
        return value

    @model_validator(mode="after")
    def _require_artifact_executable(self) -> "CanvasExtensionBackend":
        if "{artifact_dir}" not in self.argv[0]:
            raise ValueError("backend argv executable must be inside {artifact_dir}")
        return self


class CanvasExtensionManifest(BaseModel):
    """画布扩展清单 (``canvas-extension.json``)。"""

    schema_version: int = Field(description="Manifest schema version")
    name: str = Field(description="Extension name (kebab-case)")
    display_name: str = Field(description="Human-readable extension name")
    version: str = Field(description="Extension version")
    description: str = Field(default="", description="Extension description")
    entrypoint: str = Field(
        description=(
            "Path, relative to the extension package root, to the bundle entry file"
        )
    )
    contributes: CanvasExtensionContributes = Field(
        default_factory=CanvasExtensionContributes,
        description="Contributions this extension makes to the Canvas UI",
    )
    backend: CanvasExtensionBackend | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Optional explicitly prepared and started backend service",
    )
    icon: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Path, relative to the extension package root, to an SVG icon",
    )

    @field_validator("icon", mode="before")
    @classmethod
    def _validate_icon(cls, v: object) -> str | None:
        """不要丢一个非SVG的图标。

        每次读取时都会重新验证清单，因此在此处引发会隐藏整个扩展。 在服务时检查遏制
        :func:`resolve_icon`。
        """
        if v is None or (isinstance(v, str) and v.endswith(".svg")):
            return v
        logger.warning("Ignoring invalid canvas extension icon %r", v)
        return None

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported canvas extension schema_version")
        return value

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        validate_extension_name(v)
        return v

    @field_validator("entrypoint")
    @classmethod
    def _validate_entrypoint(cls, v: str) -> str:
        """拒绝文本遍历/绝对路径。

        仅语法 - 请参阅：func:`resolve_entrypoint` 以了解针对已安装包根的真正的、符号
        链接感知的包含检查。
        """
        if not v:
            raise ValueError("entrypoint must not be empty")
        if v.startswith("/"):
            raise ValueError("entrypoint must be relative, not absolute")
        if ".." in Path(v).parts:
            raise ValueError(
                "entrypoint cannot contain '..' (parent directory traversal)"
            )
        return v


def resolve_entrypoint(manifest: CanvasExtensionManifest, package_root: Path) -> Path:
    """安全地解决 ``manifest.entrypoint`` 与 ``package_root`` 的问题。

    字段级验证在 ``entrypoint`` 仅支持文本遍历 ``..``) 和绝对路径。 它无法捕获包内解
    析包外部的符号链接。 此操作执行真实的文件系统级隔离检查（
    包括解析符号链接），必须在扩展安装时调用，并在它的请输出简体中文译文入口读取或服
    务 HTTP.

    Args:
        manifest: 经过验证的清单。
        package_root: 扩展的安装包根目录。

    Returns:
        已解析，包含入口路径。

    Raises:
        ValueError: 如果已解析的入口转义 ``package_root``，或者
            不解析为其中的常规文件（涵盖 ``.``、目录、悬空符号链接和符号链接循环 —
            None，其中 ``is_relative_to`` 单独拒绝）。
    """
    return _resolve_contained_file("entrypoint", manifest.entrypoint, package_root)


def resolve_icon(manifest: CanvasExtensionManifest, package_root: Path) -> Path | None:
    """使用与入口相同的收容检查解决 ``manifest.icon``。

    Returns:
        None 如果清单声明没有图标。

    Raises:
        ValueError: 如果图标转义 ``package_root`` 或不是文件。
    """
    icon = manifest.icon
    return None if icon is None else _resolve_contained_file("icon", icon, package_root)


def _resolve_contained_file(label: str, relative_path: str, package_root: Path) -> Path:
    root = package_root.resolve()
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(
            f"{label} {relative_path!r} resolves outside the extension package root"
        )
    if not candidate.is_file():
        raise ValueError(
            f"{label} {relative_path!r} does not resolve to a file "
            "in the extension package"
        )
    return candidate
