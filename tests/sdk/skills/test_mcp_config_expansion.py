"""使用机密测试 MCP 配置变量扩展。"""

import json
import os

from openhands.sdk.skills.utils import expand_mcp_variables, load_mcp_config


class TestExpandMcpVariables:
    """测试 expand_mcp_variables 功能。"""

    def test_expand_basic_variables(self):
        """测试从变量字典扩展基本变量。"""
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "${SKILL_ROOT}/scripts/server.py",
                    "args": ["--port", "8080"],
                }
            }
        }
        variables = {"SKILL_ROOT": "/path/to/skill"}

        result = expand_mcp_variables(config, variables)

        assert result["mcpServers"]["test-server"]["command"] == (
            "/path/to/skill/scripts/server.py"
        )

    def test_expand_windows_path_variables_preserves_backslashes(self):
        """Windows 路径必须扩展为值，而不是原始 JSON 片段。"""
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "${SKILL_ROOT}\\scripts\\server.py",
                }
            }
        }
        variables = {"SKILL_ROOT": r"C:\Users\tester\skill"}

        result = expand_mcp_variables(config, variables)

        assert result["mcpServers"]["test-server"]["command"] == (
            r"C:\Users\tester\skill\scripts\server.py"
        )

    def test_expand_variables_in_dictionary_keys(self):
        """变量扩展应该保留遗留的键替换行为。"""
        config = {
            "mcpServers": {
                "${SERVER_NAME}": {
                    "headers": {"${HEADER_NAME}": "Bearer ${TOKEN}"},
                }
            }
        }
        variables = {
            "SERVER_NAME": "expanded-server",
            "HEADER_NAME": "Authorization",
            "TOKEN": "secret-token",
        }

        result = expand_mcp_variables(config, variables)

        assert "expanded-server" in result["mcpServers"]
        assert result["mcpServers"]["expanded-server"]["headers"] == {
            "Authorization": "Bearer secret-token"
        }

    def test_expand_environment_variables(self):
        """测试从环境中扩展变量。"""
        os.environ["TEST_MCP_VAR"] = "env-value-123"
        try:
            config = {
                "mcpServers": {
                    "test-server": {
                        "url": "https://example.com/${TEST_MCP_VAR}/api",
                    }
                }
            }
            result = expand_mcp_variables(config, {})

            assert result["mcpServers"]["test-server"]["url"] == (
                "https://example.com/env-value-123/api"
            )
        finally:
            del os.environ["TEST_MCP_VAR"]

    def test_expand_secrets(self):
        """通过 get_secret 回调测试扩展变量。"""
        config = {
            "mcpServers": {
                "my-server": {
                    "url": "https://example.com/mcp",
                    "headers": {"Authorization": "Bearer ${MCP_SECRET_TOKEN}"},
                }
            }
        }
        secrets = {"MCP_SECRET_TOKEN": "my-secret-value"}

        result = expand_mcp_variables(config, {}, get_secret=secrets.get)

        assert result["mcpServers"]["my-server"]["headers"]["Authorization"] == (
            "Bearer my-secret-value"
        )

    def test_variable_resolution_order(self):
        """测试变量 dict 优先于机密和 env。"""
        os.environ["SHARED_VAR"] = "env-value"
        try:
            config = {
                "mcpServers": {
                    "test-server": {
                        "value1": "${SHARED_VAR}",
                        "value2": "${SECRET_VAR}",
                        "value3": "${ENV_VAR}",
                    }
                }
            }
            variables = {"SHARED_VAR": "variables-value"}
            secrets = {"SHARED_VAR": "secrets-value", "SECRET_VAR": "secret-value"}

            result = expand_mcp_variables(config, variables, get_secret=secrets.get)

            # 变量 dict 应该胜过机密和 env
            assert result["mcpServers"]["test-server"]["value1"] == "variables-value"
            # 当不在变量中时应使用机密
            assert result["mcpServers"]["test-server"]["value2"] == "secret-value"
            # env 应该用于 ENV_VAR（不在变量或机密中）
            assert result["mcpServers"]["test-server"]["value3"] == "${ENV_VAR}"
        finally:
            del os.environ["SHARED_VAR"]

    def test_secrets_take_precedence_over_env(self):
        """测试机密优先于环境变量。"""
        os.environ["MCP_TOKEN"] = "env-token"
        try:
            config = {
                "mcpServers": {
                    "test-server": {
                        "headers": {"Authorization": "Bearer ${MCP_TOKEN}"},
                    }
                }
            }
            secrets = {"MCP_TOKEN": "secret-token"}

            result = expand_mcp_variables(config, {}, get_secret=secrets.get)

            # 机密应该战胜 env
            assert result["mcpServers"]["test-server"]["headers"]["Authorization"] == (
                "Bearer secret-token"
            )
        finally:
            del os.environ["MCP_TOKEN"]

    def test_default_values(self):
        """测试未找到变量时是否使用默认值。"""
        config = {
            "mcpServers": {
                "test-server": {
                    "url": "${API_URL:-https://default.example.com}",
                    "timeout": "${TIMEOUT:-30}",
                }
            }
        }

        result = expand_mcp_variables(config, {})

        assert (
            result["mcpServers"]["test-server"]["url"] == "https://default.example.com"
        )
        assert result["mcpServers"]["test-server"]["timeout"] == "30"

    def test_default_not_used_when_secret_exists(self):
        """测试当机密提供值时不使用默认值。"""
        config = {
            "mcpServers": {
                "test-server": {
                    "url": "${API_URL:-https://default.example.com}",
                }
            }
        }
        secrets = {"API_URL": "https://secret.example.com"}

        result = expand_mcp_variables(config, {}, get_secret=secrets.get)

        assert (
            result["mcpServers"]["test-server"]["url"] == "https://secret.example.com"
        )

    def test_unexpanded_variables_remain_unchanged(self):
        """测试未解决的变量是否保持原样。"""
        config = {
            "mcpServers": {
                "test-server": {
                    "url": "https://example.com/${UNKNOWN_VAR}/api",
                }
            }
        }

        result = expand_mcp_variables(config, {})

        # 由于未找到变量，因此应保持不变
        assert result["mcpServers"]["test-server"]["url"] == (
            "https://example.com/${UNKNOWN_VAR}/api"
        )

    def test_multiple_variables_in_same_string(self):
        """测试在同一字符串中扩展多个变量。"""
        config = {
            "mcpServers": {
                "test-server": {
                    "url": "https://${HOST}:${PORT}/${PATH}",
                }
            }
        }
        variables = {"HOST": "localhost"}
        secrets = {"PORT": "8080", "PATH": "api/v1"}

        result = expand_mcp_variables(config, variables, get_secret=secrets.get)

        assert result["mcpServers"]["test-server"]["url"] == (
            "https://localhost:8080/api/v1"
        )

    def test_no_get_secret_callback(self):
        """不使用 get_secret 回调进行测试（默认行为）。"""
        config = {
            "mcpServers": {
                "test-server": {"url": "${SKILL_ROOT}/api"},
            }
        }
        variables = {"SKILL_ROOT": "/path"}

        # 应该在没有 get_secret 的情况下工作
        result = expand_mcp_variables(config, variables, get_secret=None)

        assert result["mcpServers"]["test-server"]["url"] == "/path/api"


class TestLoadMcpConfigWithSecrets:
    """使用机密测试 load_mcp_config 功能。"""

    def test_load_mcp_config_with_secrets(self, tmp_path):
        """测试加载 .mcp.json 和机密扩展。"""
        mcp_json = tmp_path / ".mcp.json"
        config = {
            "mcpServers": {
                "my-server": {
                    "url": "https://example.com/mcp",
                    "headers": {"Authorization": "Bearer ${API_SECRET}"},
                }
            }
        }
        mcp_json.write_text(json.dumps(config))

        secrets = {"API_SECRET": "my-secret-token"}

        result = load_mcp_config(mcp_json, skill_root=tmp_path, get_secret=secrets.get)

        assert result["mcpServers"]["my-server"]["headers"]["Authorization"] == (
            "Bearer my-secret-token"
        )

    def test_load_mcp_config_without_secrets(self, tmp_path):
        """测试加载 .mcp.json，不带机密 (向后兼容性)。"""
        mcp_json = tmp_path / ".mcp.json"
        config = {
            "mcpServers": {
                "my-server": {
                    "command": "${SKILL_ROOT}/server.py",
                    "args": [],
                }
            }
        }
        mcp_json.write_text(json.dumps(config))

        result = load_mcp_config(mcp_json, skill_root=tmp_path)

        assert result["mcpServers"]["my-server"]["command"] == f"{tmp_path}/server.py"

    def test_load_mcp_config_skill_root_takes_precedence(self, tmp_path):
        """测试 skill_root 参数中的 SKILL_ROOT 优先于机密。"""
        mcp_json = tmp_path / ".mcp.json"
        config = {
            "mcpServers": {
                "my-server": {
                    "command": "${SKILL_ROOT}/server.py",
                }
            }
        }
        mcp_json.write_text(json.dumps(config))

        # 即使机密有 SKILL_ROOT，参数也应该获胜
        secrets = {"SKILL_ROOT": "/wrong/path"}

        result = load_mcp_config(mcp_json, skill_root=tmp_path, get_secret=secrets.get)

        assert result["mcpServers"]["my-server"]["command"] == f"{tmp_path}/server.py"

    def test_load_mcp_config_combined_variables_and_secrets(self, tmp_path):
        """测试加载使用 skill_root 和机密的配置。"""
        mcp_json = tmp_path / ".mcp.json"
        config = {
            "mcpServers": {
                "my-server": {
                    "command": "${SKILL_ROOT}/server.py",
                    "env": {
                        "API_KEY": "${API_KEY}",
                        "DB_URL": "${DATABASE_URL:-sqlite://default.db}",
                    },
                }
            }
        }
        mcp_json.write_text(json.dumps(config))

        secrets = {"API_KEY": "secret-key-123"}

        result = load_mcp_config(mcp_json, skill_root=tmp_path, get_secret=secrets.get)

        assert result["mcpServers"]["my-server"]["command"] == f"{tmp_path}/server.py"
        assert result["mcpServers"]["my-server"]["env"]["API_KEY"] == "secret-key-123"
        assert (
            result["mcpServers"]["my-server"]["env"]["DB_URL"] == "sqlite://default.db"
        )
