#!/usr/bin/env python3
"""
API 合规性测试运行程序。

针对多个 LLM 提供程序运行格式错误的消息模式测试，并生成记录 API 行为的报告。

用途：
    # 针对所有模型运行所有模式
    uv run python tests/integration/api_compliance/run_compliance.py

    # 运行特定模式
    uv run python tests/integration/api_compliance/run_compliance.py \
        --模式unmatched_tool_use,interleaved_user_message

    # 针对特定模型运行
    uv run python tests/integration/api_compliance/run_compliance.py \
        --模型克劳德十四行诗-4-5，gpt-5.5

    # 输出到指定目录
    uv run python tests/integration/api_compliance/run_compliance.py \
        --输出目录 ./compliance-results
"""

import argparse
import importlib.util
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from openhands.sdk.logger import get_logger
from tests.integration.api_compliance.base import BaseAPIComplianceTest, create_test_llm
from tests.integration.api_compliance.result import (
    APIResponse,
    ComplianceReport,
    ComplianceTestResult,
    PatternResults,
)


logger = get_logger(__name__)

# 要测试的默认模型 - 来自每个主要提供商的一名代表每个条目都有：模型路径、可选配置覆盖和
# 简短显示名称
# 注意：避免推理模型（deepseek-reasoner），因为它们需要特殊字段
DEFAULT_MODELS: dict[str, dict[str, Any]] = {
    "claude-sonnet-4-5": {
        "model": "litellm_proxy/claude-sonnet-4-5-20250929",
        "temperature": 0.0,
        "_display": "claude",
    },
    "gpt-5.5": {
        "model": "litellm_proxy/openai/gpt-5.5",
        "_display": "gpt",
    },
    "gemini-3.1-pro": {
        "model": "litellm_proxy/gemini-3.1-pro-preview",
        "_display": "gemini",
    },
}


def load_compliance_tests(patterns: list[str] | None = None) -> list[tuple[str, type]]:
    """从测试文件加载所有 API 合规性测试类。

    Args:
        patterns: 用于过滤的可选模式名称列表

    Returns:
        (file_path, test_class) 元组列表
    """
    test_dir = Path(__file__).parent.parent / "tests"
    test_files = sorted(test_dir.glob("a[0-9][0-9]_*.py"))

    tests = []
    for test_file in test_files:
        try:
            spec = importlib.util.spec_from_file_location("test_module", test_file)
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 找到测试类
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseAPIComplianceTest)
                    and attr is not BaseAPIComplianceTest
                ):
                    # 检查模式过滤器
                    test_instance = attr()
                    if patterns is None or test_instance.pattern_name in patterns:
                        tests.append((str(test_file), attr))
                    break

        except Exception as e:
            logger.warning(f"Failed to load test from {test_file}: {e}")

    return tests


def run_single_test(
    test_class: type[BaseAPIComplianceTest],
    llm_config: dict[str, Any],
    model_id: str,
) -> ComplianceTestResult:
    """针对单个模型运行单个合规性测试。

    Args:
        test_class: 要实例化并运行的测试类
        llm_config: LLM 配置字典
        model_id: 用于显示的短型号标识符

    Returns:
        ComplianceTestResult
    """
    test = test_class()

    try:
        llm = create_test_llm(llm_config)
        result = test.run_test(llm, model_id)
        return result
    except Exception as e:
        return ComplianceTestResult(
            pattern_name=test.pattern_name,
            model=llm_config.get("model", "unknown"),
            model_id=model_id,
            provider="unknown",
            response_type=APIResponse.CONNECTION_ERROR,
            error_message=f"Failed to create LLM: {e}",
            error_type=type(e).__name__,
        )


def run_compliance_tests(
    patterns: list[str] | None = None,
    model_ids: list[str] | None = None,
) -> ComplianceReport:
    """跨多个模型和模式运行合规性测试。

    Args:
        patterns: 要测试的模式名称列表（None = 全部）
        model_ids: 要测试的模型 ID 列表（None = 所有默认值）

    Returns:
        ComplianceReport 包含所有结果
    """
    # 负载测试
    tests = load_compliance_tests(patterns)
    if not tests:
        logger.error("No compliance tests found!")
        sys.exit(1)

    logger.info(f"Loaded {len(tests)} compliance test(s)")

    # 确定要测试的模型
    if model_ids:
        models = {
            mid: DEFAULT_MODELS[mid] for mid in model_ids if mid in DEFAULT_MODELS
        }
        if not models:
            logger.error(
                f"No valid models found. Available: {list(DEFAULT_MODELS.keys())}"
            )
            sys.exit(1)
    else:
        models = DEFAULT_MODELS

    logger.info(f"Testing against {len(models)} model(s): {list(models.keys())}")

    # 生成运行ID
    run_id = f"compliance_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 运行所有测试
    pattern_results: dict[str, PatternResults] = {}

    for file_path, test_class in tests:
        test_instance = test_class()
        pattern_name = test_instance.pattern_name

        if pattern_name not in pattern_results:
            pattern_results[pattern_name] = PatternResults(
                pattern_name=pattern_name,
                pattern_description=test_instance.pattern_description,
            )

        for model_id, llm_config in models.items():
            logger.info(f"Testing pattern '{pattern_name}' against {model_id}...")

            result = run_single_test(test_class, llm_config, model_id)
            pattern_results[pattern_name].add_result(result)

            # 记录结果
            status = (
                "✓ ACCEPTED"
                if result.response_type == APIResponse.ACCEPTED
                else "✗ REJECTED"
            )
            if result.response_type not in (APIResponse.ACCEPTED, APIResponse.REJECTED):
                status = f"⚠ {result.response_type.value.upper()}"

            logger.info(f"  {model_id}: {status}")
            if result.error_message:
                # 截断长错误消息
                msg = (
                    result.error_message[:200] + "..."
                    if len(result.error_message) > 200
                    else result.error_message
                )
                logger.info(f"    Error: {msg}")

    # 构建报告
    report = ComplianceReport(
        test_run_id=run_id,
        timestamp=datetime.now().isoformat(),
        patterns_tested=len(pattern_results),
        models_tested=list(models.keys()),
        results=list(pattern_results.values()),
    )

    return report


def save_report(report: ComplianceReport, output_dir: str) -> str:
    """将报告保存到输出目录。

    Args:
        report: ComplianceReport 保存
        output_dir: 保存到的目录

    Returns:
        保存报告的路径
    """
    os.makedirs(output_dir, exist_ok=True)

    # 保存JSON报告
    json_path = os.path.join(output_dir, "compliance_report.json")
    with open(json_path, "w") as f:
        f.write(report.model_dump_json(indent=2))

    # 生成并保存 Markdown 报告
    md_path = os.path.join(output_dir, "compliance_report.md")
    with open(md_path, "w") as f:
        f.write(generate_markdown_report(report))

    return json_path


# 用于链接到测试文件的 Base URL
GITHUB_BASE_URL = (
    "https://github.com/OpenHands/software-agent-sdk/blob/main/tests/integration/tests"
)

# 将模式名称映射到测试文件名
PATTERN_TO_FILE = {
    "unmatched_tool_use": "a01_unmatched_tool_use.py",
    "unmatched_tool_result": "a02_unmatched_tool_result.py",
    "interleaved_user_message": "a03_interleaved_user_msg.py",
    "interleaved_assistant_message": "a04_interleaved_asst_msg.py",
    "duplicate_tool_call_id": "a05_duplicate_tool_call_id.py",
    "wrong_tool_call_id": "a06_wrong_tool_call_id.py",
    "parallel_missing_result": "a07_parallel_missing_result.py",
    "parallel_wrong_order": "a08_parallel_wrong_order.py",
}

# 每种模式的简要描述（一行摘要）
PATTERN_SUMMARIES = {
    "unmatched_tool_use": "tool_use without following tool_result",
    "unmatched_tool_result": "tool_result referencing non-existent tool_use ID",
    "interleaved_user_message": "User message between tool_use and tool_result",
    "interleaved_assistant_message": "Assistant message between tool_use/tool_result",
    "duplicate_tool_call_id": "Same tool_call ID used in multiple tool_use blocks",
    "wrong_tool_call_id": "tool_result with mismatched tool_call_id",
    "parallel_missing_result": "Parallel tool calls with one result missing",
    "parallel_wrong_order": "Parallel tool call results in wrong order",
}


def generate_markdown_report(report: ComplianceReport) -> str:
    """生成紧凑、人类可读的 Markdown 报告。

    Args:
        report: ComplianceReport 格式化

    Returns:
        Markdown 字符串
    """
    lines = [
        "# API Compliance Test Report",
        "",
        f"**Run:** `{report.test_run_id}` | "
        f"**Time:** {report.timestamp} | "
        f"**Duration:** {report.elapsed_time:.1f}s",
        "",
    ]

    # 构建结果矩阵：模式 -> model_id -> 结果
    models = report.models_tested
    results_map: dict[str, dict[str, str]] = {}

    for pattern in report.results:
        results_map[pattern.pattern_name] = {}
        for result in pattern.results:
            # 将响应类型映射到表情符号（颜色+形状以实现可访问性）
            result_symbol = "⚠️"  # Warning = other/error
            if result.response_type == APIResponse.ACCEPTED:
                result_symbol = "✅"  # 绿色勾号 = 已接受
            elif result.response_type == APIResponse.REJECTED:
                result_symbol = "❌"  # 红色 X = 拒绝

            # 直接使用model_id（不需要子串匹配）
            if result.model_id in models:
                results_map[pattern.pattern_name][result.model_id] = result_symbol

    # 生成结果表
    lines.append("## Results Matrix")
    lines.append("")
    lines.append("✅ accepted  ❌ rejected  ⚠️ error")
    lines.append("")

    # 获取表标题的简短显示名称
    display_names = [DEFAULT_MODELS.get(m, {}).get("_display", m) for m in models]

    # 带有短显示名称的表标题
    header = "| Pattern | " + " | ".join(display_names) + " |"
    separator = "|:--------|" + "|".join([":---:" for _ in models]) + "|"
    lines.append(header)
    lines.append(separator)

    # 表格行数
    for pattern_name in results_map:
        summary = PATTERN_SUMMARIES.get(pattern_name, "")
        file_name = PATTERN_TO_FILE.get(pattern_name, "")
        if file_name:
            link = f"[`{pattern_name}`]({GITHUB_BASE_URL}/{file_name})"
        else:
            link = f"`{pattern_name}`"

        row = f"| {link}<br><sub>{summary}</sub> |"
        for model in models:
            result = results_map[pattern_name].get(model, "-")
            row += f" {result} |"
        lines.append(row)

    lines.append("")

    # 摘要统计数据
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total tests:** {report.total_tests}")
    lines.append(
        f"- **Rejected (expected for malformed input):** {report.total_rejected}"
    )
    lines.append(f"- **Accepted (lenient API behavior):** {report.total_accepted}")
    lines.append("")

    # 请注意带有工作流程运行链接的详细响应
    lines.append("---")
    lines.append("")
    # 链接到工作流程运行页面（可以从那里下载工件）
    github_run_id = os.environ.get("GITHUB_RUN_ID")
    if github_run_id:
        run_url = (
            "https://github.com/OpenHands/software-agent-sdk/actions/runs/"
            f"{github_run_id}"
        )
        lines.append(
            f"*Full API responses available in [workflow artifacts]({run_url})*"
        )
    else:
        lines.append("*Full API responses available in `compliance_report.json`*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Run API compliance tests against LLM providers"
    )
    parser.add_argument(
        "--patterns",
        type=str,
        default=None,
        help="Comma-separated list of pattern names to test (default: all)",
    )
    available_models = ", ".join(DEFAULT_MODELS.keys())
    parser.add_argument(
        "--models",
        type=str,
        default=None,
        help=f"Comma-separated list of model IDs. Available: {available_models}",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="tests/integration/api_compliance/outputs",
        help="Output directory for reports",
    )
    parser.add_argument(
        "--list-patterns",
        action="store_true",
        help="List available patterns and exit",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available models and exit",
    )

    args = parser.parse_args()

    if args.list_models:
        print("Available models:")
        for model_id, config in DEFAULT_MODELS.items():
            print(f"  {model_id}: {config.get('model', 'unknown')}")
        return

    if args.list_patterns:
        tests = load_compliance_tests()
        print("Available patterns:")
        for _, test_class in tests:
            test = test_class()
            first_line = test.pattern_description.strip().split(chr(10))[0]
            print(f"  {test.pattern_name}: {first_line}")
        return

    # 解析过滤器
    patterns = args.patterns.split(",") if args.patterns else None
    model_ids = args.models.split(",") if args.models else None

    # 运行测试
    logger.info("=" * 60)
    logger.info("API COMPLIANCE TEST RUNNER")
    logger.info("=" * 60)

    start_time = time.time()
    report = run_compliance_tests(patterns=patterns, model_ids=model_ids)
    elapsed = time.time() - start_time
    report.elapsed_time = elapsed

    # 保存报告
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(args.output_dir, f"run_{timestamp}")
    save_report(report, output_dir)

    # 打印摘要
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total tests: {report.total_tests}")
    logger.info(f"Rejected (expected): {report.total_rejected}")
    logger.info(f"Accepted (unexpected): {report.total_accepted}")
    logger.info(f"Elapsed time: {elapsed:.1f}s")
    logger.info(f"Report saved to: {output_dir}")


if __name__ == "__main__":
    main()
