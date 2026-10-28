from func_timeout import FunctionTimedOut, func_timeout


class TimeoutError(Exception):
    """通用 SDK 工具 TimeoutError（包装 func-超时）。"""

    pass


def run_with_timeout(func, timeout, *args, **kwargs):
    try:
        return func_timeout(timeout, func, args=args, kwargs=kwargs)
    except FunctionTimedOut:
        raise TimeoutError(f"Operation timed out after {timeout} seconds")
