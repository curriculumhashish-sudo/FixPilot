"""用于事件溯源的共享实用程序基准测试。"""

import json
import os
import tarfile


def extract_conversation(tarpath: str, dest: str) -> str | None:
    """提取对话 .tar.gz 并返回 events/ dir 路径。"""
    with tarfile.open(tarpath, "r:gz") as tf:
        tf.extractall(dest, filter="data")
    for root, _, _ in os.walk(dest):
        if os.path.basename(root) == "events":
            return root
    return None


def read_event_files(events_dir: str) -> list[dict]:
    """读取所有事件 JSON 文件。

    返回带有键的字典列表：文件名、json_str、size_bytes、种类。
    """
    files = sorted(f for f in os.listdir(events_dir) if f.endswith(".json"))
    result = []
    for fname in files:
        path = os.path.join(events_dir, fname)
        with open(path) as f:
            content = f.read()
        try:
            kind = json.loads(content).get("kind", "unknown")
        except Exception:
            kind = "unknown"
        result.append(
            {
                "filename": fname,
                "json_str": content,
                "size_bytes": len(content.encode("utf-8")),
                "kind": kind,
            }
        )
    return result


def register_tool_types() -> None:
    """导入具体的工具类，将它们注册到
    ToolDefinition 歧视联盟，启用反序列化引用这些工具的真实评估事件。
    """
    import openhands.tools.file_editor  # noqa: F401
    import openhands.tools.task_tracker  # noqa: F401
    import openhands.tools.terminal  # noqa: F401
