#!/usr/bin/env python3
"""
验证语义版本控制的 SDK 参考。

此脚本验证 SDK 引用是否是语义版本（e.g.、v1.0.0、1.0.0），除非设置了
allow_unreleased_branches 标志。

环境变量：
- SDK_REF: 要验证的 SDK 引用
- ALLOW_UNRELEASED_BRANCHES: 如果为“True”，则绕过语义版本验证

退出代码：
- 0: 验证通过
- 1: 验证失败
"""

import os
import re
import subprocess
import sys


# 语义版本模式：可选的“v”前缀，后跟 MAJOR.MINOR.PATCH 可选择允许预发布（-alpha.1、-beta.
# 2、-rc.1）和构建元数据
#
SEMVER_PATTERN = re.compile(
    r"^v?"  # 可选的“v”前缀
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"  # MAJOR.MINOR.PATCH
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"  # 预发布
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"  # 更多预发布内容
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"  # 构建元数据
)
COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,40}$")
BRANCH_EXAMPLES = "'main', 'feature/foo', or 'release/1.2.3'"


def is_semantic_version(ref: str) -> bool:
    """检查给定的引用是否是有效的语义版本。"""
    return bool(SEMVER_PATTERN.match(ref))


def is_commit_sha(ref: str) -> bool:
    """检查给定的引用是否是 git commit SHA。"""
    return bool(COMMIT_SHA_PATTERN.fullmatch(ref))


def is_valid_branch_name(ref: str) -> bool:
    """检查给定的引用是否是有效的 git 分支名称。"""
    return (
        subprocess.run(
            ["git", "check-ref-format", "--branch", ref],
            check=False,
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def validate_branch_name(branch_name: str, input_name: str) -> tuple[bool, str]:
    """根据 git 分支命名规则验证工作流分支输入。"""
    if is_valid_branch_name(branch_name):
        return True, f"Valid {input_name}: {branch_name}"

    return False, (
        f"{input_name} '{branch_name}' is not a valid git branch name. "
        f"Common GitHub/GitLab/Bitbucket branch names look like {BRANCH_EXAMPLES}."
    )


def validate_sdk_ref(sdk_ref: str, allow_unreleased: bool) -> tuple[bool, str]:
    """验证 SDK 引用。"""
    if is_semantic_version(sdk_ref):
        return True, f"Valid semantic version: {sdk_ref}"

    if allow_unreleased and (is_commit_sha(sdk_ref) or is_valid_branch_name(sdk_ref)):
        return True, f"Valid unreleased git ref: {sdk_ref}"

    if allow_unreleased:
        return False, (
            f"SDK reference '{sdk_ref}' is not a valid semantic version, commit SHA, "
            "or git branch name. Common GitHub/GitLab/Bitbucket branch names look "
            f"like {BRANCH_EXAMPLES}."
        )

    return False, (
        f"SDK reference '{sdk_ref}' is not a valid semantic version. "
        "Expected format: v1.0.0 or 1.0.0 (with optional pre-release like -alpha.1). "
        "To use unreleased branches, check 'Allow unreleased branches'."
    )


def main() -> None:
    sdk_ref = os.environ.get("SDK_REF", "")
    allow_unreleased_str = os.environ.get("ALLOW_UNRELEASED_BRANCHES", "false")
    eval_branch = os.environ.get("EVAL_BRANCH")
    benchmarks_branch = os.environ.get("BENCHMARKS_BRANCH")

    if not sdk_ref:
        print("ERROR: SDK_REF environment variable is not set", file=sys.stderr)
        sys.exit(1)

    allow_unreleased = allow_unreleased_str.lower() == "true"

    validations = [
        validate_sdk_ref(sdk_ref, allow_unreleased),
    ]
    if eval_branch:
        validations.append(validate_branch_name(eval_branch, "EVAL_BRANCH"))
    if benchmarks_branch:
        validations.append(validate_branch_name(benchmarks_branch, "BENCHMARKS_BRANCH"))

    for is_valid, message in validations:
        stream = sys.stdout if is_valid else sys.stderr
        print(("✓" if is_valid else "✗") + f" {message}", file=stream)
        if not is_valid:
            sys.exit(1)


if __name__ == "__main__":
    main()
