"""用于将环境变量转换为 Pydantic 基本模型的实用程序。 我们不能为此使用 Pydantic-设置
，因为我们需要复杂的嵌套类型和多态性。
"""

import importlib
import inspect
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from io import StringIO
from pathlib import Path
from types import UnionType
from typing import IO, Annotated, Any, Literal, Union, cast, get_args, get_origin
from uuid import UUID

from pydantic import BaseModel, SecretStr, TypeAdapter

from openhands.sdk.utils.models import (
    DiscriminatedUnionMixin,
    get_known_concrete_subclasses,
)


# 定义缺失类型
class MissingType:
    pass


MISSING = MissingType()
JsonType = str | int | float | bool | dict | list | None | MissingType


class EnvParser(ABC):
    """事件解析器类型"""

    @abstractmethod
    def from_env(self, key: str) -> JsonType:
        """将环境变量解析为类似 JSON 的结构"""

    def to_env(self, key: str, value: Any, output: IO):
        """基于此解析器生成模板"""
        if value is None:
            value = ""
        output.write(f"{key}={value}\n")


class BoolEnvParser(EnvParser):
    def from_env(self, key: str) -> bool | MissingType:
        if key not in os.environ:
            return MISSING
        return os.environ[key].upper() in ["1", "TRUE"]  # type: ignore

    def to_env(self, key: str, value: Any, output: IO):
        output.write(f"{key}={1 if value else 0}\n")


class IntEnvParser(EnvParser):
    def from_env(self, key: str) -> int | MissingType:
        if key not in os.environ:
            return MISSING
        return int(os.environ[key])


class FloatEnvParser(EnvParser):
    def from_env(self, key: str) -> float | MissingType:
        if key not in os.environ:
            return MISSING
        return float(os.environ[key])


class StrEnvParser(EnvParser):
    def from_env(self, key: str) -> str | MissingType:
        if key not in os.environ:
            return MISSING
        return os.environ[key]


class NoneEnvParser(EnvParser):
    def from_env(self, key: str) -> None | MissingType:
        key = f"{key}_IS_NONE"
        value = (os.getenv(key) or "").upper()
        if value in ["1", "TRUE"]:
            return None
        return MISSING

    def to_env(self, key: str, value: Any, output: IO):
        if value is None:
            output.write(f"{key}_IS_NONE=1\n")


@dataclass
class LiteralEnvParser(EnvParser):
    values: tuple[str, ...]

    def from_env(self, key: str) -> str | MissingType:
        value = os.getenv(key)
        if value not in self.values:
            return MISSING
        return value

    def to_env(self, key: str, value: Any, output: IO):
        output.write(f"# Permitted Values: {', '.join(self.values)}\n")
        # 对于枚举，使用值而不是字符串表示形式
        if hasattr(value, "value"):
            output.write(f"{key}={value.value}\n")
        else:
            output.write(f"{key}={value}\n")


@dataclass
class ModelEnvParser(EnvParser):
    parsers: dict[str, EnvParser]
    descriptions: dict[str, str]

    def from_env(self, key: str) -> dict | MissingType:
        # 首先我们看到有一个基值定义为 JSON...
        value = os.environ.get(key)
        if value:
            result = json.loads(value)
            assert isinstance(result, dict)
        else:
            result = MISSING

        # 检查是否有覆盖...
        for field_name, parser in self.parsers.items():
            env_var_name = f"{key}_{field_name.upper()}"

            # 首先我们检查该字段是否有可能的键以防止无限递归
            #
            has_possible_keys = next(
                (k for k in os.environ if k.startswith(env_var_name)), False
            )
            if not has_possible_keys:
                continue

            field_value = parser.from_env(env_var_name)
            if field_value is MISSING:
                continue
            if result is MISSING:
                result = {}
            existing_field_value = result.get(field_name, MISSING)  # type: ignore
            new_field_value = merge(existing_field_value, field_value)
            if new_field_value is not MISSING:
                result[field_name] = new_field_value  # type: ignore

        return result

    def to_env(self, key: str, value: Any, output: IO):
        for field_name, parser in self.parsers.items():
            field_description = self.descriptions.get(field_name)
            if field_description:
                for line in field_description.split("\n"):
                    output.write("# ")
                    output.write(line)
                    output.write("\n")
            field_key = key + "_" + field_name.upper()
            field_value = getattr(value, field_name)
            parser.to_env(field_key, field_value, output)
            output.write("\n")


class DictEnvParser(EnvParser):
    def from_env(self, key: str) -> dict | MissingType:
        # 从环境变量读取 JSON
        value = os.environ.get(key)
        if value:
            result = json.loads(value)
            assert isinstance(result, dict)
        else:
            result = MISSING

        return result


@dataclass
class ListEnvParser(EnvParser):
    item_parser: EnvParser
    item_type: type

    def from_env(self, key: str) -> list | MissingType:
        if key not in os.environ:
            # 尝试顺序读取，从0开始如果没有项则返回MISSING
            #
            result = MISSING
            index = 0
            while True:
                sub_key = f"{key}_{index}"
                item = self.item_parser.from_env(sub_key)
                if item is MISSING:
                    return result
                if result is MISSING:
                    result = []
                result.append(item)  # type: ignore
                index += 1

        # 假设值为JSON
        value = os.environ.get(key)
        result = json.loads(value)  # type: ignore
        # 数字表示结果的长度应为 N 项
        if isinstance(result, int):
            result = [MISSING] * result
        else:
            # 否则假设该项目是一个列表
            assert isinstance(result, list)

        for index in range(len(result)):
            sub_key = f"{key}_{index}"
            item = self.item_parser.from_env(sub_key)
            item = merge(result[index], item)
            # 我们允许列表中缺少项目，因为这些项目可能会在稍后与另一个解析器的输出合并时
            # 被填充
            #
            result[index] = item  # type: ignore

        return result

    def to_env(self, key: str, value: Any, output: IO):
        if len(value):
            for index, sub_value in enumerate(value):
                sub_key = f"{key}_{index}"
                self.item_parser.to_env(sub_key, sub_value, output)
        else:
            # 尝试根据默认值生成样本值...
            try:
                sub_key = f"{key}_0"
                sample_output = StringIO()
                self.item_parser.to_env(
                    sub_key, _create_sample(self.item_type), sample_output
                )
                for line in sample_output.getvalue().strip().split("\n"):
                    output.write("# ")
                    output.write(line)
                    output.write("\n")
            except Exception:
                # 无法创建示例值。 跳过
                pass


@dataclass
class UnionEnvParser(EnvParser):
    parsers: dict[type, EnvParser]

    def from_env(self, key: str) -> JsonType:
        result = MISSING
        for parser in self.parsers.values():
            parser_result = parser.from_env(key)
            result = merge(result, parser_result)
        return result

    def to_env(self, key: str, value: Any, output: IO):
        for type_, parser in self.parsers.items():
            if not isinstance(value, type_):
                # 尝试根据默认值生成样本值...
                try:
                    sample_value = _create_sample(type_)
                    sample_output = StringIO()
                    sample_output.write(f"{sample_value.__class__.__name__}\n")
                    parser.to_env(key, sample_value, sample_output)
                    for line in sample_output.getvalue().split("\n"):
                        output.write("# ")
                        output.write(line)
                        output.write("\n")
                except Exception:
                    # 无法创建示例值。 跳过
                    pass
        for type_, parser in self.parsers.items():
            if isinstance(value, type_):
                output.write(f"# {value.__class__.__name__}\n")
                parser.to_env(key, value, output)
                output.write("\n")


@dataclass
class DiscriminatedUnionEnvParser(EnvParser):
    parsers: dict[str, EnvParser]

    def from_env(self, key: str) -> JsonType:
        kind = os.environ.get(f"{key}_KIND", MISSING)
        kind_missing = False
        if kind is MISSING:
            kind_missing = True
            # 如果还有其他字段并且恰好有一种，则直接使用
            if len(self.parsers) == 1:
                kind = next(iter(self.parsers.keys()))
            else:
                return MISSING
        # 类型缩小：这里的 kind 是 str （来自 os.environ.get 或 dict 键）
        kind = cast(str, kind)

        # 如果 kind 包含点，则将其视为完整的类名
        if "." in kind:
            kind = self._import_and_register_class(kind)

        # 故意对无效的 KIND 提出 KeyError - 拼写错误应该会提前失败
        parser = self.parsers[kind]
        parser_result = parser.from_env(key)

        # 定义了一个种类，没有其他字段
        if parser_result is MISSING:
            # 如果未定义种类，则条目为 MISSING
            if kind_missing:
                return MISSING
            # 仅定义了一种
            parser_result = {}

        # 类型缩小：可区分的联合解析器总是返回字典
        parser_result = cast(dict, parser_result)
        parser_result["kind"] = kind
        return parser_result

    def _import_and_register_class(self, full_class_name: str) -> str:
        """从完整模块路径导入类并注册其解析器。

        Args:
            full_class_name: 完整的类路径 (e.g., mymodule.submodule.MyClass)

        Returns:
            非限定类名 (e.g., 'MyClass')
        """
        parts = full_class_name.rsplit(".", 1)
        module_name = parts[0]
        class_name = parts[1]

        # 如果类已经注册，只需返回名称
        if class_name in self.parsers:
            return class_name

        # 导入模块并获取类
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)

        # 为该类创建并注册解析器
        parser = get_env_parser(cls, _get_default_parsers())
        self.parsers[class_name] = parser

        return class_name

    def to_env(self, key: str, value: Any, output: IO):
        parser = self.parsers[value.kind]
        parser.to_env(key, value, output)


@dataclass
class DelayedParser(EnvParser):
    """循环依赖的延迟解析器"""

    parser: EnvParser | None = None

    def from_env(self, key: str) -> JsonType:
        assert self.parser is not None
        return self.parser.from_env(key)

    def to_env(self, key: str, value: Any, output: IO):
        assert self.parser is not None
        return self.parser.to_env(key, value, output)


def merge(a, b, *, none_overrides: bool = False):
    """将 ``b`` 合并到 ``a``。

    默认情况下，``b`` 中的 ``None`` 保留 ``a``。 对于 ``none_overrides=True``，``b``
    中的显式 ``None`` 取
    代了 ``a``（e.g。 ``OH_<FIELD>_IS_NONE=1``超过配置文件值）； ``MISSING``仍保留
    ``a``。
    """
    if a is MISSING:
        return b
    if b is MISSING:
        return a
    if isinstance(a, dict) and isinstance(b, dict):
        result = {**a}
        for key, value in b.items():
            result[key] = merge(result.get(key), value, none_overrides=none_overrides)
        return result
    if isinstance(a, list) and isinstance(b, list):
        result = a.copy()
        for index, value in enumerate(b):
            if index >= len(a):
                result[index] = value
            else:
                result[index] = merge(
                    result[index], value, none_overrides=none_overrides
                )
        return result
    # 优先考虑当前值而不是缺失值
    if b is None and not none_overrides:
        return a
    # 后面的值会覆盖前面的值
    return b


def get_env_parser(target_type: type, parsers: dict[type, EnvParser]) -> EnvParser:
    # 检查我们是否已经定义了解析器
    if target_type in parsers:
        return parsers[target_type]

    # 检查原产地
    origin = get_origin(target_type)
    if origin is Annotated:
        # 剥离注释...
        return get_env_parser(get_args(target_type)[0], parsers)
    if origin is UnionType or origin is Union:
        union_parsers = {
            t: get_env_parser(t, parsers)  # type: ignore
            for t in get_args(target_type)
        }
        return UnionEnvParser(union_parsers)
    if origin is list:
        item_type = get_args(target_type)[0]
        parser = get_env_parser(item_type, parsers)
        return ListEnvParser(parser, item_type)
    if origin is dict:
        args = get_args(target_type)
        assert args[0] is str
        assert args[1] in (str, int, float, bool)
        return DictEnvParser()
    if origin is Literal:
        args = cast(tuple[str, ...], get_args(target_type))
        return LiteralEnvParser(args)
    if origin and issubclass(origin, BaseModel):
        target_type = origin
    if issubclass(target_type, DiscriminatedUnionMixin) and (
        inspect.isabstract(target_type) or ABC in target_type.__bases__
    ):
        delayed = DelayedParser()
        parsers[target_type] = delayed  # 防止循环依赖
        sub_parsers = {
            c.__name__: get_env_parser(c, parsers)
            for c in get_known_concrete_subclasses(target_type)
        }
        parser = DiscriminatedUnionEnvParser(sub_parsers)
        delayed.parser = parser
        parsers[target_type] = parser
        return parser
    if issubclass(target_type, BaseModel):  # type: ignore
        delayed = DelayedParser()
        parsers[target_type] = delayed  # 防止循环依赖
        field_parsers = {}
        descriptions = {}
        for name, field in target_type.model_fields.items():
            field_parsers[name] = get_env_parser(field.annotation, parsers)  # type: ignore
            description = field.description
            if description:
                descriptions[name] = description

        parser = ModelEnvParser(field_parsers, descriptions)
        delayed.parser = parser
        parsers[target_type] = parser
        return parser
    if issubclass(target_type, Enum):
        values = tuple(e.value for e in target_type)
        return LiteralEnvParser(values)
    raise ValueError(f"unknown_type:{target_type}")


def _get_default_parsers() -> dict[type, EnvParser]:
    return {
        str: StrEnvParser(),
        int: IntEnvParser(),
        float: FloatEnvParser(),
        bool: BoolEnvParser(),
        type(None): NoneEnvParser(),
        UUID: StrEnvParser(),
        Path: StrEnvParser(),
        datetime: StrEnvParser(),
        SecretStr: StrEnvParser(),
    }


def _create_sample(type_: type):
    if type_ is None:
        return None
    if type_ is str:
        return "..."
    if type_ is int:
        return 0
    if type_ is float:
        return 0.0
    if type_ is bool:
        return False
    try:
        if issubclass(type_, Enum):
            return next(iter(type_))
    except Exception:
        pass
    # 尝试初始化并在失败时引发异常。
    return type_()


def from_env(
    target_type: type,
    prefix: str = "",
    parsers: dict[type, EnvParser] | None = None,
):
    if parsers is None:
        parsers = _get_default_parsers()
    parser = get_env_parser(target_type, parsers)
    json_data = parser.from_env(prefix)
    if json_data is MISSING:
        result = target_type()
    else:
        json_str = json.dumps(json_data)
        type_adapter = TypeAdapter(target_type)
        result = type_adapter.validate_json(json_str)
    return result


def to_env(
    value: Any,
    prefix: str = "",
    parsers: dict[type, EnvParser] | None = None,
) -> str:
    if parsers is None:
        parsers = _get_default_parsers()
    parser = get_env_parser(value.__class__, parsers)
    output = StringIO()
    parser.to_env(prefix, value, output)
    return output.getvalue()
