import os

from openhands.sdk.event import ActionEvent


def get_env(key: str) -> str | None:
    """从进程环境中获取环境变量。

    加载 ``.env`` 文件是有意留给主机应用程序的（例如，CLI 在启动时调用
    ``load_dotenv()`` 一次）。 直读
    from ``os.environ`` avoids python-dotenv's ``find_dotenv()`` call-stack
    walk，执行 ``assert frame.f_back is not None`` 并引发
    ``AssertionError`` 在其帧没有磁盘文件的执行上下文中（线程运行执行/嵌入代码，一些
    异步路径）。 请参阅问题#1325。
    """
    return os.getenv(key)


def extract_action_name(action_event: ActionEvent) -> str:
    try:
        if action_event.action is not None and hasattr(action_event.action, "kind"):
            return action_event.action.kind
        else:
            return action_event.tool_name
    except Exception:
        return "agent.execute_action"
