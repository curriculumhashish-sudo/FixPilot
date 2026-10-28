from rich.text import Text


def display_json(data) -> Text:
    """创建 JSON 数据的富文本表示形式。

    处理字典、列表、字符串、数字、布尔值和 None 值。
    """
    content = Text()

    if isinstance(data, dict):
        for field_name, field_value in data.items():
            if field_value is None:
                continue  # 跳过 None 个字段
            content.append(f"\n  {field_name}: ", style="bold")
            if isinstance(field_value, str):
                # 使用适当的缩进处理多行字符串
                if "\n" in field_value:
                    content.append("\n")
                    for line in field_value.split("\n"):
                        content.append(f"    {line}\n")
                else:
                    content.append(f'"{field_value}"')
            elif isinstance(field_value, (list, dict)):
                content.append(str(field_value))
            else:
                content.append(str(field_value))
    elif isinstance(data, list):
        content.append(f"[List with {len(data)} items]\n")
        for i, item in enumerate(data):
            content.append(f"  [{i}]: ", style="bold")
            if isinstance(item, str):
                content.append(f'"{item}"\n')
            else:
                content.append(f"{item}\n")
    elif isinstance(data, str):
        # 使用适当的缩进处理多行字符串
        if "\n" in data:
            content.append("String:\n")
            for line in data.split("\n"):
                content.append(f"  {line}\n")
        else:
            content.append(f'"{data}"')
    elif data is None:
        content.append("null")
    else:
        # 处理数字、布尔值和其他 JSON 原语
        content.append(str(data))

    return content
