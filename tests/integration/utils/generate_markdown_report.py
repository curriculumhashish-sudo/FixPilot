#!/usr/bin/env python3
"""
根据综合 JSON 结果生成 PR 条评论的 Markdown 报告。
"""

import argparse
import json
import sys

from tests.integration.schemas import (
    ConsolidatedResults,
    ModelTestResults,
    TokenUsageData,
)
from tests.integration.utils.format_costs import format_cost


def format_token_usage(token_usage: TokenUsageData | None) -> str:
    """词元用量格式用于显示。"""
    if token_usage is None:
        return "N/A"

    parts = []
    if token_usage.prompt_tokens > 0:
        parts.append(f"prompt: {token_usage.prompt_tokens:,}")
    if token_usage.completion_tokens > 0:
        parts.append(f"completion: {token_usage.completion_tokens:,}")
    if token_usage.cache_read_tokens > 0:
        parts.append(f"cache_read: {token_usage.cache_read_tokens:,}")
    if token_usage.cache_write_tokens > 0:
        parts.append(f"cache_write: {token_usage.cache_write_tokens:,}")
    if token_usage.reasoning_tokens > 0:
        parts.append(f"reasoning: {token_usage.reasoning_tokens:,}")

    if not parts:
        return "0"

    return ", ".join(parts)


def format_token_usage_short(token_usage: TokenUsageData | None) -> str:
    """将词元用量设置为表格的短格式。"""
    if token_usage is None:
        return "N/A"

    total = token_usage.prompt_tokens + token_usage.completion_tokens
    if total == 0:
        return "0"

    return f"{total:,}"


def generate_model_summary_table(model_results: list[ModelTestResults]) -> str:
    """生成所有模型的汇总表。"""

    table_lines = [
        ("| Model | Overall | Tests Passed | Skipped | Total | Cost | Tokens |"),
        ("|-------|---------|--------------|---------|-------|------|--------|"),
    ]

    for result in model_results:
        overall_success = f"{result.success_rate:.1%}"
        non_skipped = result.total_tests - result.skipped_tests
        tests_passed = f"{result.successful_tests}/{non_skipped}"
        skipped = f"{result.skipped_tests}"
        cost = format_cost(result.total_cost)
        tokens = format_token_usage_short(result.total_token_usage)

        model_name = result.model_name
        total_tests = result.total_tests
        row = (
            f"| {model_name} | {overall_success} | {tests_passed} | {skipped} | "
            f"{total_tests} | {cost} | {tokens} |"
        )
        table_lines.append(row)

    return "\n".join(table_lines)


def generate_detailed_results(model_results: list[ModelTestResults]) -> str:
    """为每个模型生成详细的结果。"""

    sections = []

    for result in model_results:
        non_skipped = result.total_tests - result.skipped_tests
        section_lines = [
            f"### {result.model_name}",
            "",
            f"- **Success Rate**: {result.success_rate:.1%} "
            f"({result.successful_tests}/{non_skipped})",
        ]

        section_lines.extend(
            [
                f"- **Total Cost**: {format_cost(result.total_cost)}",
                f"- **Token Usage**: {format_token_usage(result.total_token_usage)}",
                f"- **Run Suffix**: `{result.run_suffix}`",
            ]
        )

        if result.skipped_tests > 0:
            section_lines.append(f"- **Skipped Tests**: {result.skipped_tests}")

        section_lines.append("")

        # 添加跳过的测试（如果有）
        skipped_tests = [t for t in result.test_instances if t.test_result.skipped]
        if skipped_tests:
            section_lines.extend(
                [
                    "**Skipped Tests:**",
                    "",
                ]
            )

            for test in skipped_tests:
                reason = test.test_result.reason or "No reason provided"
                section_lines.append(f"- `{test.instance_id}`: {reason}")

            section_lines.append("")

        # 添加失败的测试（如果有）
        failed_tests = [
            t
            for t in result.test_instances
            if not t.test_result.success and not t.test_result.skipped
        ]
        if failed_tests:
            section_lines.extend(
                [
                    "**Failed Tests:**",
                    "",
                ]
            )

            for test in failed_tests:
                reason = test.test_result.reason or "No reason provided"
                cost = format_cost(test.cost)
                section_lines.append(f"- `{test.instance_id}`: {reason} (Cost: {cost})")

            section_lines.append("")

        # 添加错误消息（如果有）
        error_tests = [t for t in result.test_instances if t.error_message]
        if error_tests:
            section_lines.extend(
                [
                    "**Tests with Errors:**",
                    "",
                ]
            )

            for test in error_tests:
                section_lines.append(f"- `{test.instance_id}`: {test.error_message}")

            section_lines.append("")

        sections.append("\n".join(section_lines))

    return "\n".join(sections)


def derive_report_title(consolidated: ConsolidatedResults) -> str:
    """从实际运行的测试类型中得出报告标题。

    当每个结果实例共享该类型时，运行将由其单一测试类型标记； 混合或仅集成运行会回退到
    向后兼容性的默认“集成测试结果”标题。
    """
    test_types = {
        instance.test_type
        for result in consolidated.model_results
        for instance in result.test_instances
    }
    if test_types == {"behavior"}:
        return "# 🧪 Behavior Tests Results"
    if test_types == {"condenser"}:
        return "# 🧪 Condenser Tests Results"
    return "# 🧪 Integration Tests Results"


def generate_markdown_report(consolidated: ConsolidatedResults) -> str:
    """根据合并结果生成完整的 Markdown 报告。"""

    # 标头
    report_lines = [
        derive_report_title(consolidated),
        "",
        f"**Overall Success Rate**: {consolidated.overall_success_rate:.1%}",
        f"**Total Cost**: {format_cost(consolidated.total_cost_all_models)}",
        f"**Models Tested**: {consolidated.total_models}",
        f"**Timestamp**: {consolidated.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
    ]

    # 如果任何模型有 artifact URLs，添加 artifacts 部分
    artifacts_available = any(
        result.artifact_url for result in consolidated.model_results
    )
    if artifacts_available:
        report_lines.extend(
            [
                "<details>",
                "<summary>📁 Detailed Logs & Artifacts</summary>",
                "",
                (
                    "Click the links below to access detailed agent/LLM logs showing "
                    "the complete reasoning process for each model. "
                    "On the GitHub Actions page, scroll down to the 'Artifacts' "
                    "section to download the logs."
                ),
                "",
            ]
        )

        for result in consolidated.model_results:
            if result.artifact_url:
                report_lines.append(
                    f"- **{result.model_name}**: "
                    f"[📥 View & Download Logs]({result.artifact_url})"
                )

        report_lines.append("")  # 在工件部分后添加空行

    # 汇总表
    report_lines.extend(
        [
            "## 📊 Summary",
            "",
            generate_model_summary_table(consolidated.model_results),
            "",
        ]
    )

    # 详细结果
    report_lines.extend(
        [
            "## 📋 Detailed Results",
            "",
            generate_detailed_results(consolidated.model_results),
        ]
    )

    if artifacts_available:
        report_lines.extend(["", "</details>"])

    return "\n".join(report_lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate markdown report from consolidated JSON results"
    )
    parser.add_argument(
        "--input-file",
        required=True,
        help="Consolidated JSON results file",
    )
    parser.add_argument(
        "--output-file",
        help="Output markdown file (default: stdout)",
    )

    args = parser.parse_args()

    try:
        # 加载合并结果
        print(
            f"Loading consolidated results from {args.input_file}...", file=sys.stderr
        )

        with open(args.input_file) as f:
            data = json.load(f)

        consolidated = ConsolidatedResults.model_validate(data)
        print(
            f"✓ Loaded results for {consolidated.total_models} models", file=sys.stderr
        )

        # 生成 Markdown 报告
        print("Generating markdown report...", file=sys.stderr)
        markdown_report = generate_markdown_report(consolidated)

        # 输出报告
        if args.output_file:
            with open(args.output_file, "w") as f:
                f.write(markdown_report)
            print(f"✓ Report saved to {args.output_file}", file=sys.stderr)
        else:
            print(markdown_report)

        return 0

    except Exception as e:
        print(f"✗ Error generating report: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
