import logging
from pathlib import Path

import pytest
from pydantic import BaseModel

from openhands.sdk.extensions.installation import (
    InstallationInfo,
    InstallationInterface,
    InstallationMetadata,
)


class MockExtension(BaseModel):
    name: str
    version: str
    description: str


class MockExtensionInstallationInterface(InstallationInterface):
    @staticmethod
    def load_from_dir(extension_dir: Path) -> MockExtension:
        return MockExtension.model_validate_json(
            (extension_dir / "extension.json").read_text()
        )


def _write_mock_extension(
    directory: Path,
    name: str = "mock-extension",
    version: str = "0.0.1",
    description: str = "Mock extension",
) -> Path:
    """将模拟对象扩展清单写入目录。"""
    directory.mkdir(parents=True, exist_ok=True)
    ext = MockExtension(name=name, version=version, description=description)
    with (directory / "extension.json").open("w") as f:
        f.write(ext.model_dump_json())
    return directory


# ============================================================================
# 旧版关键迁移测试
# ============================================================================


def test_migrate_legacy_plugins_key():
    """测试旧的 {"plugins": {...}} 格式是否迁移到扩展。"""
    data = {
        "plugins": {
            "my-plugin": {
                "name": "my-plugin",
                "source": "github:owner/repo",
                "install_path": "/tmp/installed/my-plugin",
            }
        }
    }
    metadata = InstallationMetadata.model_validate(data)
    assert "my-plugin" in metadata.extensions
    assert metadata.extensions["my-plugin"].name == "my-plugin"


def test_migrate_legacy_skills_key():
    """测试旧的 {"skills": {...}} 格式是否迁移到扩展程序。"""
    data = {
        "skills": {
            "my-skill": {
                "name": "my-skill",
                "source": "local",
                "install_path": "/tmp/installed/my-skill",
                "enabled": False,
            }
        }
    }
    metadata = InstallationMetadata.model_validate(data)
    assert "my-skill" in metadata.extensions
    assert metadata.extensions["my-skill"].enabled is False


def test_migrate_merges_both_legacy_keys():
    """当插件和技能都存在时，测试两者是否合并。"""
    data = {
        "plugins": {
            "my-plugin": {
                "name": "my-plugin",
                "source": "github:owner/repo",
                "install_path": "/tmp/installed/my-plugin",
            }
        },
        "skills": {
            "my-skill": {
                "name": "my-skill",
                "source": "local",
                "install_path": "/tmp/installed/my-skill",
            }
        },
    }
    metadata = InstallationMetadata.model_validate(data)
    assert "my-plugin" in metadata.extensions
    assert "my-skill" in metadata.extensions


def test_migrate_legacy_key_logs_warning(caplog: pytest.LogCaptureFixture):
    """每个迁移的旧密钥都会发出警告。"""
    data = {
        "plugins": {
            "p": {
                "name": "p",
                "source": "local",
                "install_path": "/tmp/p",
            }
        },
        "skills": {
            "s": {
                "name": "s",
                "source": "local",
                "install_path": "/tmp/s",
            }
        },
    }
    with caplog.at_level(logging.WARNING):
        InstallationMetadata.model_validate(data)

    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("plugins" in w for w in warnings)
    assert any("skills" in w for w in warnings)


def test_migrate_merges_legacy_into_extensions():
    """旧密钥被合并到扩展中； 扩展在冲突中获胜。"""
    data = {
        "extensions": {
            "new-ext": {
                "name": "new-ext",
                "source": "local",
                "install_path": "/tmp/installed/new-ext",
            }
        },
        "plugins": {
            "old-plugin": {
                "name": "old-plugin",
                "source": "local",
                "install_path": "/tmp/installed/old-plugin",
            }
        },
    }
    metadata = InstallationMetadata.model_validate(data)
    assert "new-ext" in metadata.extensions
    assert "old-plugin" in metadata.extensions


def test_migrate_extensions_wins_on_conflict():
    """当一个名称同时出现在扩展程序和旧密钥中时，扩展程序获胜。"""
    data = {
        "extensions": {
            "shared": {
                "name": "shared",
                "source": "local",
                "install_path": "/tmp/installed/shared",
            }
        },
        "plugins": {
            "shared": {
                "name": "shared",
                "source": "github:owner/repo",
                "install_path": "/tmp/installed/shared",
            }
        },
    }
    metadata = InstallationMetadata.model_validate(data)
    assert metadata.extensions["shared"].source == "local"


def test_migrate_conflicting_legacy_keys():
    """当插件和技能名称相同时，后一个键获胜。"""
    data = {
        "plugins": {
            "shared": {
                "name": "shared",
                "source": "github:A",
                "install_path": "/tmp/installed/shared",
            }
        },
        "skills": {
            "shared": {
                "name": "shared",
                "source": "github:B",
                "install_path": "/tmp/installed/shared",
            }
        },
    }
    metadata = InstallationMetadata.model_validate(data)
    # 技能在 _LEGACY_KEYS 中的插件之后迭代，因此它会覆盖
    assert metadata.extensions["shared"].source == "github:B"


# ============================================================================
# 加载/保存测试
# ============================================================================


def test_load_from_dir_nonexistent(tmp_path: Path):
    """从不存在的目录加载元数据的测试返回空。"""
    metadata = InstallationMetadata.load_from_dir(tmp_path / "nonexistent")
    assert metadata.extensions == {}


def test_load_from_dir_and_save_to_dir(tmp_path: Path):
    """测试保存和加载元数据。"""
    installation_dir = tmp_path / "installed"
    installation_dir.mkdir()

    info = InstallationInfo(
        name="test-extension",
        version="1.0.0",
        description="Test",
        source="github:owner/test",
        install_path=installation_dir / "test-extension",
    )

    metadata = InstallationMetadata(extensions={"test-extension": info})
    metadata.save_to_dir(installation_dir)

    loaded_metadata = InstallationMetadata.load_from_dir(installation_dir)

    assert metadata == loaded_metadata


def test_load_from_dir_invalid_json(tmp_path: Path):
    """测试加载无效 JSON 返回空元数据。"""
    installation_dir = tmp_path / "installed"
    installation_dir.mkdir()

    metadata_path = InstallationMetadata.get_metadata_path(installation_dir)
    metadata_path.write_text("invalid json {")

    metadata = InstallationMetadata.load_from_dir(installation_dir)
    assert metadata.extensions == {}


def test_save_and_load_round_trip_non_ascii(tmp_path: Path):
    """save_to_dir() 则 load_from_dir() 必须往返非 ASCII 内容。

    save_to_dir()/load_from_dir() 使用 Path.write_text()
    /read_text()，当未给出编码时，它会回退到平台默认编码（Windows 上的 cp1252）。
    cp1252 无法表示表情符号等字符，因此具有非
    ASCII 字段的元数据将无法持久化。 两端必须使用UTF-8。
    """
    installation_dir = tmp_path / "installed"
    installation_dir.mkdir()

    info = InstallationInfo(
        name="café-extension",
        version="1.0.0",
        description="Adds 🔐 secure access review — supports français",
        source="github:owner/café-extension",
        install_path=installation_dir / "café-extension",
    )
    metadata = InstallationMetadata(extensions={"café-extension": info})
    metadata.save_to_dir(installation_dir)

    # 磁盘上的元数据文件必须有效 UTF-8。
    metadata_path = InstallationMetadata.get_metadata_path(installation_dir)
    assert "🔐" in metadata_path.read_bytes().decode("utf-8")

    loaded_metadata = InstallationMetadata.load_from_dir(installation_dir)
    assert metadata == loaded_metadata
    assert loaded_metadata.extensions["café-extension"].description == (
        "Adds 🔐 secure access review — supports français"
    )


# ============================================================================
# open() 上下文管理器测试
# ============================================================================


def test_open_saves_on_clean_exit(tmp_path: Path):
    """测试上下文管理器在干净退出时自动保存。"""
    installation_dir = tmp_path / "installed"
    installation_dir.mkdir()

    info = InstallationInfo(
        name="test-ext",
        source="local",
        install_path=installation_dir / "test-ext",
    )

    with InstallationMetadata.open(installation_dir) as session:
        session.extensions["test-ext"] = info

    loaded = InstallationMetadata.load_from_dir(installation_dir)
    assert "test-ext" in loaded.extensions


def test_open_does_not_save_on_exception(tmp_path: Path):
    """测试异常发生时上下文管理器不保存。"""
    installation_dir = tmp_path / "installed"
    installation_dir.mkdir()

    info = InstallationInfo(
        name="test-ext",
        source="local",
        install_path=installation_dir / "test-ext",
    )

    try:
        with InstallationMetadata.open(installation_dir) as session:
            session.extensions["test-ext"] = info
            raise RuntimeError("simulated failure")
    except RuntimeError:
        pass

    loaded = InstallationMetadata.load_from_dir(installation_dir)
    assert loaded.extensions == {}


# ============================================================================
# validate_tracked 测试
# ============================================================================


def test_validate_tracked_prunes_invalid_names(tmp_path: Path):
    """测试 validate_tracked 是否删除具有无效名称的条目。"""
    installation_dir = tmp_path / "installed"
    installation_dir.mkdir()

    bad_info = InstallationInfo(
        name="Bad_Name",
        source="local",
        install_path=installation_dir / "Bad_Name",
    )
    good_info = InstallationInfo(
        name="good-ext",
        source="local",
        install_path=installation_dir / "good-ext",
    )
    (installation_dir / "good-ext").mkdir()

    metadata = InstallationMetadata(
        extensions={"Bad_Name": bad_info, "good-ext": good_info}
    )

    valid = metadata.validate_tracked(installation_dir)

    assert len(valid) == 1
    assert valid[0].name == "good-ext"
    assert "Bad_Name" not in metadata.extensions


# ============================================================================
# discover_untracked 测试
# ============================================================================


def test_discover_untracked_skips_mismatched_manifest_name(tmp_path: Path):
    """测试发现会跳过清单名称不匹配的目录。"""
    installation_dir = tmp_path / "installed"
    installation_dir.mkdir()

    _write_mock_extension(installation_dir / "some-ext", name="other-name")

    metadata = InstallationMetadata()
    interface = MockExtensionInstallationInterface()

    discovered = metadata.discover_untracked(installation_dir, interface)

    assert discovered == []
    assert "some-ext" not in metadata.extensions
