#!/usr/bin/env python3
"""
集成工作流程 (integration-runner.yml) 使用的实用程序将多个 JSON 文件的集成测试结果合
并到 Markdown 报告中。 此脚本处理测试结果
JSON 文件并生成适合 GitHub PR 注释的综合 Markdown 报告。
"""

import glob
import json
import os
import re
import sys
from datetime import UTC, datetime

from tests.integration.utils.format_costs import format_cost


def find_result_files(results_dir="all_results"):
    """使用简单的 glob 模式查找所有结果 JSON 文件。"""
    patterns = [f"{results_dir}/*_results.json", f"{results_dir}/*.json"]
    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern))
    return list(set(files))  # 删除重复项


def extract_success_rate(test_report):
    """从测试报告中提取成功率。"""
    if not test_report or test_report == "No report available":
        return "N/A"
    match = re.search(r"Success rate: (\d+\.\d+%)", test_report)
    return match.group(1) if match else "N/A"


def process_result_file(filepath):
    """处理单个结果文件并返回提取的数据。"""
    try:
        with open(filepath) as f:
            data = json.load(f)

        return {
            "model_name": data.get("model_name", "Unknown"),
            "run_suffix": data.get("run_suffix", "unknown"),
            "test_report": data.get("test_report", "No report available"),
            "artifact_url": data.get("artifact_url", "N/A"),
            "success_rate": extract_success_rate(data.get("test_report", "")),
            "total_cost": data.get("total_cost", 0.0),
        }
    except Exception as e:
        print(f"Error processing {filepath}: {e}", file=sys.stderr)
        return None


def generate_report(results, trigger_text, commit_sha):
    """生成综合 Markdown 报告。"""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    # 计算总成本
    total_cost = sum(result.get("total_cost", 0.0) for result in results)

    report = f"""# Integration Tests Report

**Trigger:** {trigger_text}
**Commit:** {commit_sha}
**Timestamp:** {timestamp}

## Test Results Summary

| Model | Success Rate | Cost | Test Results | Artifact Link |
|-------|--------------|------|--------------|---------------|
"""

    if not results:
        report += "| No results | N/A | N/A | No test results available | N/A |\n"
    else:
        for result in results:
            artifact_link = f"[Download]({result['artifact_url']})"
            model_name = result["model_name"]
            success_rate = result["success_rate"]
            cost = format_cost(result.get("total_cost", 0.0))
            row = (
                f"| {model_name} | {success_rate} | {cost} | "
                f"See details below | {artifact_link} |\n"
            )
            report += row

    report += "\n## Detailed Results\n\n"

    for result in results:
        report += f"### {result['model_name']}\n```\n{result['test_report']}\n```\n\n"

    report += f"---\n**Overall Status:** {len(results)} models tested\n"
    report += f"**Total Cost:** {format_cost(total_cost)}\n"

    return report


def determine_trigger_info(event_name, pr_number, manual_reason):
    """根据事件类型确定触发文本和最终 PR 数字。"""
    if event_name == "pull_request":
        trigger_text = f"Pull Request (integration-test label on PR #{pr_number})"
        final_pr_number = pr_number
    elif event_name == "workflow_dispatch":
        trigger_text = f"Manual Trigger: {manual_reason}"
        final_pr_number = "9745"  # 回退方案期号
    else:
        trigger_text = "Nightly Scheduled Run"
        final_pr_number = "9745"  # 回退方案期号

    return trigger_text, final_pr_number


def main():
    """主要功能是合并测试结果。"""
    # 获取环境变量
    event_name = os.environ.get("EVENT_NAME", "")
    pr_number = os.environ.get("PR_NUMBER", "")
    manual_reason = os.environ.get("MANUAL_REASON", "")
    commit_sha = os.environ.get("COMMIT_SHA", "")

    # 确定触发文本和PR数字
    trigger_text, final_pr_number = determine_trigger_info(
        event_name, pr_number, manual_reason
    )

    # 查找并处理结果文件
    result_files = find_result_files()
    print(f"Found {len(result_files)} result files")

    results = []
    for filepath in result_files:
        result = process_result_file(filepath)
        if result:
            results.append(result)

    # 生成报告
    report = generate_report(results, trigger_text, commit_sha)

    # 将报告保存到文件
    with open("consolidated_report.md", "w") as f:
        f.write(report)

    # 设置环境变量进行下一步
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a") as f:
            f.write(f"PR_NUMBER={final_pr_number}\n")

    print(f"Successfully processed {len(results)} models")
    return 0


if __name__ == "__main__":
    sys.exit(main())
