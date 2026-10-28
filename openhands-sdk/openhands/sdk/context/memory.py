"""两层持久内存加载器。

将智能体维护的 ``MEMORY.md`` 索引 - ``~/.openhands/memory/``（用户层）和
``<workspace>/.openhands/memory/``（项目层） - 读取到一个提示词就绪字符串中。
LocalConversation首先解决了这个问题
``send_message()`` / ``run()``（当AgentContext有效时，工作区路径未知）； AgentContext
仅包含已解析的文本。 同一目录中
的每日日志 (``YYYY-MM-DD.md``) 会被有意地不加载——智能体按需读取它们。
"""

from pathlib import Path
from typing import Final

from openhands.sdk.logger import get_logger
from openhands.sdk.utils.path import get_user_persistence_dir, to_posix_path


logger = get_logger(__name__)

__all__ = ["MEMORY_CHAR_BUDGET", "MEMORY_INDEX_RELPATH", "load_memory"]

MEMORY_INDEX_RELPATH: Final[str] = ".openhands/memory/MEMORY.md"
MEMORY_CHAR_BUDGET: Final[int] = 6000
_TRUNCATION_NOTICE: Final[str] = "[earlier memory truncated]"


def _read_index(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(f"Failed to read memory index {path}: {e}")
        return None
    return text or None


def _truncate_top(body: str, budget: int) -> str:
    """从 ``body`` 顶部删除整行，直到适合 ``budget``。

    截断正文以截断通知开始（计入预算）； 部分线路永远不会生存。
    """
    if len(body) <= budget:
        return body
    lines = body.splitlines()
    while lines:
        del lines[0]
        candidate = "\n".join([_TRUNCATION_NOTICE, *lines])
        if len(candidate) <= budget:
            return candidate
    return _TRUNCATION_NOTICE


def load_memory(
    working_dir: str | Path, char_budget: int = MEMORY_CHAR_BUDGET
) -> str | None:
    """加载 ``working_dir`` 的组合内存索引文本。

    用户层第一，项目层第二（后面的位置得到更多模型关注）。 当两个索引都没有内容时返回
     ``None``。 超出预算的层从顶部开始逐行截断，保留最新的尾部
    -- 维护说明告诉智能体追加 -- while tier
    标题（和截断通知）始终保留。 该框架是预算的有效下限：每当 ``char_budget`` 覆盖标
    题以及每层一个通知（两层约 150 个字符）时，就会受到尊重。
    """
    tiers: list[tuple[str, str]] = []
    user_memory_path = get_user_persistence_dir() / "memory" / "MEMORY.md"
    user_index = _read_index(user_memory_path)
    if user_index is not None:
        # 按实际读取的路径命名层，使其与 <MEMORY> 指南中公布的写入位置相匹配。 未展开的
        # ``~/.openhands`` 回退方案将每个用户的主路径保留在提示词之外，与
        # MemorySection._user_memory_line 完全相同。
        #
        user_header_path = to_posix_path(
            get_user_persistence_dir(Path("~/.openhands")) / "memory" / "MEMORY.md"
        )
        tiers.append((f"# User memory ({user_header_path})", user_index))
    project_index = _read_index(Path(working_dir) / MEMORY_INDEX_RELPATH)
    if project_index is not None:
        tiers.append((f"# Project memory ({MEMORY_INDEX_RELPATH})", project_index))
    if not tiers:
        return None

    combined = "\n\n".join(f"{header}\n{body}" for header, body in tiers)
    if len(combined) <= char_budget:
        return combined

    # 始终发出标头和空行分隔符； 剩余的预算在各个层级机构之间平均分配，一个短层级的未使
    # 用份额将滚动到另一个层级。
    #
    overhead = sum(len(header) + 1 for header, _ in tiers) + 2 * (len(tiers) - 1)
    body_budget = char_budget - overhead
    fair_share = body_budget // len(tiers)
    budgets = [min(len(body), fair_share) for _, body in tiers]
    leftover = body_budget - sum(budgets)
    for i, (_, body) in enumerate(tiers):
        extra = min(leftover, len(body) - budgets[i])
        budgets[i] += extra
        leftover -= extra
    return "\n\n".join(
        f"{header}\n{_truncate_top(body, budget)}"
        for (header, body), budget in zip(tiers, budgets)
    )
