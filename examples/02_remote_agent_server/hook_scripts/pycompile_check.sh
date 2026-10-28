#!/bin/bash
# 停止钩子：对工作区中的所有.py文件运行Python语法检查，如果任何Python文件有语法错误，则返回拒绝，并以错误输出作为反馈
#
# 此挂钩验证智能体没有破坏任何 Python 文件。 环境变量 CHECK_DIR 可以覆盖默认值工作目录。
#

CHECK_DIR="${CHECK_DIR:-.}"

# 查找所有 Python 文件并检查语法错误
ERRORS=""
while IFS= read -r -d '' file; do
    # 运行 Python 语法检查
    result=$(python3 -m py_compile "$file" 2>&1)
    if [ $? -ne 0 ]; then
        ERRORS="${ERRORS}\n${result}"
    fi
done < <(find "$CHECK_DIR" -name "*.py" -print0 2>/dev/null)

if [ -n "$ERRORS" ]; then
    # 将输出转义为 JSON
    ESCAPED_OUTPUT=$(echo -e "$ERRORS" | head -50 | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')
    echo "{\"decision\": \"deny\", \"additionalContext\": $ESCAPED_OUTPUT}"
    exit 2
fi

exit 0
