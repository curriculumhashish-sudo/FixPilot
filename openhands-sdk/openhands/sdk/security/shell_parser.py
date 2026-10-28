"""共享 tree-sitter-bash 解析入口为 SDK。

两个消费者需要对 shell 命令进行 tree-sitter-bash 解析：

- ``openhands-tools`` 用于命令分割和转义加倍 (``terminal.utils.command``)。
- ``openhands-sdk`` 用于 AST 感知安全检测（计划的 ``security.defense_in_depth.*`` 分
析器）。

将解析器托管在 ``openhands-sdk`` 中，使得消费者都依赖于相同的树-itter 版本，避免了重
复的 ``Language`` 配置，并且防止了安全分析器从需
要扫描的工具包中获取其转译依赖。

该模块有意公开了两个消费者今天需要的最小表面：单个 ``parse(command)`` 函数返回一个
``ParseResult`` 携带已解析的 ``Tree`` 和预先计算的
``has_error`` 标志。 便利的迭代器和一个公开的 ``root_node`` 字段被推迟到后续，因此第
一个动作是一个共享基座，而不是一个 API 表面扩展。

``Parser`` 是每次调用时构造的。 ``Language`` 是一次构建的
import. This mirrors the convention in
``openhands-tools/openhands/tools/terminal/utils/command.py``：跨调用共享一个解析器存
在交错状态的风险，而语言对
象是安全可重用的。
"""

from dataclasses import dataclass

import tree_sitter_bash
from tree_sitter import Language, Parser, Tree


__all__ = ["ParseResult", "parse"]

_BASH_LANGUAGE = Language(tree_sitter_bash.language())


@dataclass(frozen=True, slots=True)
class ParseResult:
    """使用 tree-sitter-bash 解析 bash 命令的结果。

    ``tree`` 是根据输入字节生成的树守护者 ``Tree``； 呼叫者可以通过标准的树保姆 API
    行走。 ``has_error`` 镜像
    ``tree.root_node.has_error`` 并在解析时具体化，因此调用者可以分支而无需重新遍历根
    。

    Frozen: 调用者不得改变结果。 未来的修订可能
    添加便利访问器（e.g., ``iter_simple_commands``）而不破坏现有的消费者。
    """

    tree: Tree
    has_error: bool


def parse(command: str) -> ParseResult:
    """将 bash 命令字符串解析为树守护者 ``ParseResult``。

    返回一个 ``ParseResult``，其 ``tree`` 是解析后的树保姆
    ``Tree`` 及其 ``has_error`` 标志指示解析器在恢复期间是否发出任何 ``ERROR`` 节点。
     树保姆本身不会对语法错误的输入提出要求； 恢复
    情况通过 ``ERROR`` 节点报告。 对输入字符串进行编码可以引发：
    ``command.encode()`` 使用严格的 UTF-8 并在调用解析器之前拒绝使用
    ``UnicodeEncodeError`` 的单独代理。 必须接受此
    类输入的调用者应在上游将其规范化。

    编码为UTF-8； 解析器在内部对字节进行操作，因此推理节点跨度的调用者应该使用字节偏
    移量，而不是代码点偏移量，反对``command.encode()``。
    """
    tree = Parser(_BASH_LANGUAGE).parse(command.encode())
    return ParseResult(tree=tree, has_error=tree.root_node.has_error)
