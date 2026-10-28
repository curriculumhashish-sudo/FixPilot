#!/usr/bin/env python3
"""
将多个模型的 JSON 测试结果合并到单个结构化文件中。
"""

import argparse
import json
import os
import sys
from pathlib import Path

from tests.integration.schemas import (
    ConsolidatedResults,
    ModelTestResults,
)


def find_json_results(results_dir: str) -> list[Path]:
    """在结果目录中查找所有 JSON 个结果文件。"""
    results_path = Path(results_dir)
    if not results_path.exists():
        raise FileNotFoundError(f"Results directory not found: {results_dir}")

    # 查找两种模式：*/results.json 和 *_results.json
    json_files = list(results_path.glob("*/results.json")) + list(
        results_path.glob("*_results.json")
    )
    print(f"Found {len(json_files)} JSON result files")

    for json_file in json_files:
        print(f"  - {json_file}")

    return json_files


def load_and_validate_results(
    json_files: list[Path], artifacts_dir: str | None = None
) -> list[ModelTestResults]:
    """加载并验证 JSON 结果文件。"""
    model_results = []

    for json_file in json_files:
        try:
            print(f"Loading {json_file}...")
            with open(json_file) as f:
                data = json.load(f)

            # 使用 Pydantic 模式验证
            model_result = ModelTestResults.model_validate(data)

            # 如果提供了工件目录，则添加工件 URL
            if artifacts_dir:
                artifact_url = find_artifact_url(model_result.run_suffix, artifacts_dir)
                if artifact_url:
                    model_result.artifact_url = artifact_url

            model_results.append(model_result)
            model_name = model_result.model_name
            total_tests = model_result.total_tests
            print(f"  ✓ Loaded {model_name} with {total_tests} tests")

        except Exception as e:
            print(f"  ✗ Error loading {json_file}: {e}")
            raise

    return model_results


def extract_matrix_run_suffix(full_run_suffix: str) -> str | None:
    """
    从完整的 run_suffix 中提取矩阵游程后缀。

    完整的 run_suffix 格式为：
    {model_name}_{commit_hash}_{matrix_run_suffix}_N{count}_{timestamp}
    我们需要提取 matrix_run_suffix 部分。

    Examples:
    - litellm_proxy_anthropic_claude_sonnet_4_5_20250929_0dd44e1_sonnet_run_N7_20251006_183106 -> sonnet_run
    - litellm_proxy_deepseek_deepseek_chat_0dd44e1_deepseek_run_N7_20251006_183104 -> deepseek_run
    - litellm_proxy_openai_gpt_5_mini_0dd44e1_gpt5_mini_run_N7_20251006_183117 -> gpt5_mini_run
    """  # noqa: E501
    import re

    # 与矩阵运行后缀匹配的模式查找模式：_{7_hex_chars}_{matrix_run_suffix}_N{number}_ 提
    # 交哈希始终为 7 个十六进制字符
    #
    pattern = r"_[a-f0-9]{7}_([^_]+(?:_[^_]+)*_run)_N\d+_"
    match = re.search(pattern, full_run_suffix)

    if match:
        return match.group(1)

    # 回退方案：如果模式不匹配，则返回None
    return None


def find_artifact_url(run_suffix: str, artifacts_dir: str) -> str | None:
    """查找给定运行后缀的工件 URL。"""
    artifacts_path = Path(artifacts_dir)
    if not artifacts_path.exists():
        return None

    # 从完整的 run_suffix 中提取矩阵运行后缀
    matrix_run_suffix = extract_matrix_run_suffix(run_suffix)
    if not matrix_run_suffix:
        return None

    # 查找匹配矩阵运行后缀的 artifact 目录：Artifact 命名模式：integration-test-outputs-
    # {matrix-run-suffix}-{run-id}-{run-attempt}  # noqa: E501
    #
    expected_prefix = f"integration-test-outputs-{matrix_run_suffix}-"

    for artifact_dir in artifacts_path.iterdir():
        if artifact_dir.is_dir() and artifact_dir.name.startswith(expected_prefix):
            # 使用环境变量生成 GitHub 操作 URL
            server_url = os.getenv("GITHUB_SERVER_URL", "https://github.com")
            repository = os.getenv("GITHUB_REPOSITORY", "")
            run_id = os.getenv("GITHUB_RUN_ID", "")

            if repository and run_id:
                # 创建一个指向 GitHub 操作运行页面的 URL 用户可以从那里下载特定的工件
                #
                return f"{server_url}/{repository}/actions/runs/{run_id}"
            else:
                # 回退方案：如果环境变量不可用，则返回None
                # 这将防止显示损坏的链接
                return None

    return None


def consolidate_results(model_results: list[ModelTestResults]) -> ConsolidatedResults:
    """将各个模型结果合并到一个结构中。"""
    print(f"\nConsolidating {len(model_results)} model results...")

    consolidated = ConsolidatedResults.from_model_results(model_results)

    print(f"Overall success rate: {consolidated.overall_success_rate:.2%}")
    print(f"Total cost across all models: ${consolidated.total_cost_all_models:.4f}")

    # 打印每个模型词元用量的摘要
    # 注意：我们不会跨模型聚合 token，因为不同的模型
    # 使用不同的分词器，使得跨模型 token 和毫无意义。
    for model_result in model_results:
        if model_result.total_token_usage is not None:
            token_usage = model_result.total_token_usage
            total_tokens = token_usage.prompt_tokens + token_usage.completion_tokens
            print(f"Token usage for {model_result.model_name}: {total_tokens:,}")

    return consolidated


def save_consolidated_results(
    consolidated: ConsolidatedResults, output_file: str
) -> None:
    """将合并结果保存到 JSON 文件。"""
    print(f"\nSaving consolidated results to {output_file}...")

    # 仅当 output_file 有目录组件时才创建目录
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_file, "w") as f:
        f.write(consolidated.model_dump_json(indent=2))

    print(f"✓ Consolidated results saved to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Consolidate JSON test results from multiple models"
    )
    parser.add_argument(
        "--results-dir",
        required=True,
        help="Directory containing model result subdirectories",
    )
    parser.add_argument(
        "--output-file",
        required=True,
        help="Output file for consolidated results",
    )
    parser.add_argument(
        "--artifacts-dir",
        help="Directory containing downloaded artifacts for URL generation",
    )

    args = parser.parse_args()

    try:
        # 查找所有 JSON 个结果文件
        json_files = find_json_results(args.results_dir)

        if not json_files:
            print("No JSON result files found!")
            return 1

        # 加载并验证结果
        model_results = load_and_validate_results(json_files, args.artifacts_dir)

        # 巩固成果
        consolidated = consolidate_results(model_results)

        # 保存合并结果
        save_consolidated_results(consolidated, args.output_file)

        print("\n✓ Consolidation completed successfully!")
        return 0

    except Exception as e:
        print(f"\n✗ Error during consolidation: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
