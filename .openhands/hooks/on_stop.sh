#!/bin/bash
# 停止挂钩：运行预提交 pytest，并在允许智能体完成之前检查 CI 状态
#
# 当智能体尝试停止/完成时，此挂钩运行。 它可以 BLOCK 经停：
#   - 使用代码 2 退出（被阻止）
#   - 输出JSON: {"decision": "deny", "additionalContext": "反馈信息"}
#
# 环境变量可用：
#   OPENHANDS_PROJECT_DIR - 项目目录 OPENHANDS_SESSION_ID - 会话 ID GITHUB_TOKEN - GitHub API token（如果可用）
#

set -o pipefail

PROJECT_DIR="${OPENHANDS_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR" || exit 1

# 收集所有问题以报告给智能体
ISSUES=""
BLOCK_STOP=false

log_issue() {
    ISSUES="${ISSUES}${1}\n"
    BLOCK_STOP=true
}

>&2 echo "=== Stop Hook ==="
>&2 echo "Project directory: $PROJECT_DIR"
>&2 echo ""

# --------------------------
# 第 1 步：对所有文件运行预提交
# --------------------------
>&2 echo "=== Running pre-commit run --all-files ==="
if command -v uv &> /dev/null; then
    PRECOMMIT_OUTPUT=$(uv run pre-commit run --all-files 2>&1)
    PRECOMMIT_EXIT=$?
else
    PRECOMMIT_OUTPUT=$(pre-commit run --all-files 2>&1)
    PRECOMMIT_EXIT=$?
fi

>&2 echo "$PRECOMMIT_OUTPUT"

if [ $PRECOMMIT_EXIT -ne 0 ]; then
    >&2 echo "⚠️  pre-commit found issues (exit code: $PRECOMMIT_EXIT)"
    log_issue "## Pre-commit Failed\n\nPre-commit checks failed. Please fix the following issues:\n\n\`\`\`\n${PRECOMMIT_OUTPUT}\n\`\`\`"
else
    >&2 echo "✓ pre-commit passed"
fi
>&2 echo ""

# --------------------------
# 第 2 步：检测更改的文件并运行适当的测试
# --------------------------
>&2 echo "=== Detecting changed files and running appropriate tests ==="

# 从 git 获取更改的文件（暂存、未暂存和未跟踪）
CHANGED_FILES=$(git status --porcelain 2>/dev/null | awk '{print $NF}')

if [ -n "$CHANGED_FILES" ]; then
    >&2 echo "Changed files:"
    >&2 echo "$CHANGED_FILES" | head -20
    >&2 echo ""

    # 将更改的文件映射到测试目录
    PROJECTS_TO_TEST=""

    add_project() {
        local project="$1"
        if [[ ! "$PROJECTS_TO_TEST" =~ "$project" ]]; then
            PROJECTS_TO_TEST="$PROJECTS_TO_TEST $project"
        fi
    }

    while IFS= read -r file; do
        case "$file" in
            openhands-sdk/*) add_project "tests/sdk" ;;
            openhands-tools/*) add_project "tests/tools" ;;
            openhands-workspace/*) add_project "tests/workspace" ;;
            openhands-agent-server/*) add_project "tests/agent_server" ;;
            tests/sdk/*) add_project "tests/sdk" ;;
            tests/tools/*) add_project "tests/tools" ;;
            tests/workspace/*) add_project "tests/workspace" ;;
            tests/agent_server/*) add_project "tests/agent_server" ;;
            tests/cross/*) add_project "tests/cross" ;;
            tests/examples/*) add_project "tests/examples" ;;
            tests/github_workflows/*) add_project "tests/github_workflows" ;;
            examples/*) add_project "tests/examples" ;;
            scripts/*) add_project "tests/cross" ;;
            pyproject.toml|uv.lock) add_project "tests/cross" ;;
        esac
    done <<< "$CHANGED_FILES"

    PROJECTS_TO_TEST=$(echo "$PROJECTS_TO_TEST" | xargs)

    if [ -n "$PROJECTS_TO_TEST" ]; then
        >&2 echo "Running tests for: $PROJECTS_TO_TEST"
        >&2 echo ""

        for project in $PROJECTS_TO_TEST; do
            if [ -d "$project" ]; then
                >&2 echo "=== Testing $project ==="
                if command -v uv &> /dev/null; then
                    PYTEST_OUTPUT=$(uv run pytest "$project" -v --tb=short -x 2>&1)
                    PYTEST_EXIT=$?
                else
                    PYTEST_OUTPUT=$(pytest "$project" -v --tb=short -x 2>&1)
                    PYTEST_EXIT=$?
                fi
                >&2 echo "$PYTEST_OUTPUT"

                if [ $PYTEST_EXIT -ne 0 ]; then
                    >&2 echo "⚠️  pytest failed for $project"
                    log_issue "## Pytest Failed for $project\n\nTests failed. Please fix the following:\n\n\`\`\`\n${PYTEST_OUTPUT}\n\`\`\`"
                fi
                >&2 echo ""
            fi
        done
    else
        >&2 echo "No tests to run for changed files"
    fi
else
    >&2 echo "No changed files detected, skipping local tests"
fi
>&2 echo ""

# --------------------------
# 步骤 3：检查是否有推送提交并等待 CI
# --------------------------
>&2 echo "=== Checking GitHub CI status ==="

# 检查我们是否在具有 GitHub 远程的 git 存储库中
GITHUB_REMOTE=$(git remote -v 2>/dev/null | grep -E "(github\.com.*push)" | head -1)
if [ -z "$GITHUB_REMOTE" ]; then
    >&2 echo "No GitHub remote found, skipping CI check"
else
    # 从远程提取所有者/存储库 URL 处理 HTTPS 和 SSH 格式
    #
    REPO_INFO=$(echo "$GITHUB_REMOTE" | sed -E 's|.*github\.com[:/]([^/]+)/([^/.]+)(\.git)?.*|\1/\2|')
    
    if [ -z "$REPO_INFO" ]; then
        >&2 echo "Could not parse GitHub repository info"
    else
        >&2 echo "Repository: $REPO_INFO"
        
        # 获取当前分支
        CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
        >&2 echo "Current branch: $CURRENT_BRANCH"
        
        # 获取最新提交 SHA
        LOCAL_SHA=$(git rev-parse HEAD 2>/dev/null)
        >&2 echo "Local commit: ${LOCAL_SHA:0:8}"
        
        # 检查此提交是否已推送
        REMOTE_SHA=$(git ls-remote origin "$CURRENT_BRANCH" 2>/dev/null | awk '{print $1}')
        
        if [ -z "$REMOTE_SHA" ]; then
            >&2 echo "Branch not pushed to remote, skipping CI check"
        elif [ "$LOCAL_SHA" != "$REMOTE_SHA" ]; then
            >&2 echo "Local commit differs from remote (remote: ${REMOTE_SHA:0:8}), skipping CI check"
        else
            >&2 echo "Commit has been pushed, checking CI status..."
            
            # 检查GITHUB_TOKEN是否可用
            if [ -z "$GITHUB_TOKEN" ]; then
                >&2 echo "GITHUB_TOKEN not set, cannot check CI status"
            else
                # 如果可用，请使用 gh CLI，否则回退到 API
                if command -v gh &> /dev/null; then
                    >&2 echo "Using gh CLI to check CI status..."
                    
                    # 获取此提交的检查运行
                    CI_STATUS=$(gh api "repos/$REPO_INFO/commits/$LOCAL_SHA/check-runs" \
                        --jq '.check_runs | map({name: .name, status: .status, conclusion: .conclusion})' 2>&1)
                    
                    if [ $? -ne 0 ]; then
                        >&2 echo "Failed to get CI status: $CI_STATUS"
                    else
                        # 解析状态
                        TOTAL_CHECKS=$(echo "$CI_STATUS" | jq 'length')
                        
                        if [ "$TOTAL_CHECKS" -eq 0 ]; then
                            >&2 echo "No CI checks found for this commit"
                        else
                            >&2 echo "Found $TOTAL_CHECKS CI check(s)"
                            
                            # 检查正在进行的运行
                            IN_PROGRESS=$(echo "$CI_STATUS" | jq '[.[] | select(.status != "completed")] | length')
                            FAILED=$(echo "$CI_STATUS" | jq '[.[] | select(.conclusion == "failure" or .conclusion == "timed_out" or .conclusion == "cancelled")] | length')
                            
                            if [ "$IN_PROGRESS" -gt 0 ]; then
                                >&2 echo "⏳ $IN_PROGRESS check(s) still in progress"
                                
                                # 等待 CI 完成（与超时一起）
                                MAX_WAIT=300  # 5分钟
                                WAIT_INTERVAL=15
                                TOTAL_WAITED=0
                                
                                while [ "$IN_PROGRESS" -gt 0 ] && [ "$TOTAL_WAITED" -lt "$MAX_WAIT" ]; do
                                    >&2 echo "Waiting for CI... (${TOTAL_WAITED}s / ${MAX_WAIT}s max)"
                                    sleep $WAIT_INTERVAL
                                    TOTAL_WAITED=$((TOTAL_WAITED + WAIT_INTERVAL))
                                    
                                    CI_STATUS=$(gh api "repos/$REPO_INFO/commits/$LOCAL_SHA/check-runs" \
                                        --jq '.check_runs | map({name: .name, status: .status, conclusion: .conclusion})' 2>&1)
                                    IN_PROGRESS=$(echo "$CI_STATUS" | jq '[.[] | select(.status != "completed")] | length')
                                done
                                
                                if [ "$IN_PROGRESS" -gt 0 ]; then
                                    >&2 echo "⚠️  CI still running after ${MAX_WAIT}s timeout"
                                    log_issue "## CI Still Running\n\nCI checks are still in progress after waiting ${MAX_WAIT} seconds. Please wait for CI to complete before finishing."
                                fi
                            fi
                            
                            # 等待后重新检查是否失败
                            FAILED=$(echo "$CI_STATUS" | jq '[.[] | select(.conclusion == "failure" or .conclusion == "timed_out" or .conclusion == "cancelled")] | length')
                            
                            if [ "$FAILED" -gt 0 ]; then
                                >&2 echo "❌ $FAILED check(s) failed!"
                                
                                # 获取失败检查的详细信息
                                FAILED_DETAILS=$(echo "$CI_STATUS" | jq -r '.[] | select(.conclusion == "failure" or .conclusion == "timed_out" or .conclusion == "cancelled") | "- \(.name): \(.conclusion)"')
                                >&2 echo "$FAILED_DETAILS"
                                
                                # 尝试获取失败日志
                                FAILED_NAMES=$(echo "$CI_STATUS" | jq -r '.[] | select(.conclusion == "failure") | .name')
                                
                                FAILURE_MSG="## CI Failed\n\nThe following CI checks failed:\n\n${FAILED_DETAILS}\n"
                                
                                # 尝试获取工作流运行日志以了解更多信息上下文
                                WORKFLOW_RUNS=$(gh api "repos/$REPO_INFO/actions/runs?head_sha=$LOCAL_SHA" \
                                    --jq '.workflow_runs[] | select(.conclusion == "failure") | {id: .id, name: .name}' 2>/dev/null)
                                
                                if [ -n "$WORKFLOW_RUNS" ]; then
                                    FAILURE_MSG="${FAILURE_MSG}\nYou can view the full logs at: https://github.com/$REPO_INFO/actions\n"
                                    
                                    # 尝试获取作业日志
                                    FIRST_RUN_ID=$(echo "$WORKFLOW_RUNS" | jq -r '.id' | head -1)
                                    if [ -n "$FIRST_RUN_ID" ]; then
                                        JOBS_OUTPUT=$(gh api "repos/$REPO_INFO/actions/runs/$FIRST_RUN_ID/jobs" \
                                            --jq '.jobs[] | select(.conclusion == "failure") | "### \(.name)\nConclusion: \(.conclusion)\nSteps:\n" + (.steps | map("- \(.name): \(.conclusion)") | join("\n"))' 2>/dev/null | head -100)
                                        if [ -n "$JOBS_OUTPUT" ]; then
                                            FAILURE_MSG="${FAILURE_MSG}\n### Failed Job Details:\n\`\`\`\n${JOBS_OUTPUT}\n\`\`\`"
                                        fi
                                    fi
                                fi
                                
                                log_issue "$FAILURE_MSG"
                            else
                                >&2 echo "✓ All CI checks passed!"
                            fi
                        fi
                    fi
                else
                    # 回退方案卷曲
                    >&2 echo "gh CLI not available, using API directly..."
                    CI_RESPONSE=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
                        -H "Accept: application/vnd.github.v3+json" \
                        "https://api.github.com/repos/$REPO_INFO/commits/$LOCAL_SHA/check-runs" 2>&1)
                    
                    TOTAL_CHECKS=$(echo "$CI_RESPONSE" | jq '.total_count // 0')
                    
                    if [ "$TOTAL_CHECKS" -gt 0 ]; then
                        IN_PROGRESS=$(echo "$CI_RESPONSE" | jq '[.check_runs[] | select(.status != "completed")] | length')
                        FAILED=$(echo "$CI_RESPONSE" | jq '[.check_runs[] | select(.conclusion == "failure")] | length')
                        
                        if [ "$IN_PROGRESS" -gt 0 ]; then
                            >&2 echo "⏳ CI checks still in progress"
                            log_issue "## CI In Progress\n\nCI checks are still running. Please wait for CI to complete."
                        elif [ "$FAILED" -gt 0 ]; then
                            FAILED_NAMES=$(echo "$CI_RESPONSE" | jq -r '.check_runs[] | select(.conclusion == "failure") | .name')
                            >&2 echo "❌ CI failed: $FAILED_NAMES"
                            log_issue "## CI Failed\n\nThe following CI checks failed:\n${FAILED_NAMES}\n\nPlease fix the issues and try again."
                        else
                            >&2 echo "✓ All CI checks passed!"
                        fi
                    else
                        >&2 echo "No CI checks found"
                    fi
                fi
            fi
        fi
    fi
fi
>&2 echo ""

# --------------------------
# 最终决定
# --------------------------
if [ "$BLOCK_STOP" = true ]; then
    >&2 echo "=== BLOCKING STOP: Issues found ==="
    # 输出 JSON 向智能体提供反馈逃避 JSON 的问题
    #
    ESCAPED_ISSUES=$(echo -e "$ISSUES" | jq -Rs .)
    echo "{\"decision\": \"deny\", \"reason\": \"Checks failed\", \"additionalContext\": $ESCAPED_ISSUES}"
    exit 2
fi

>&2 echo "=== All checks passed, allowing stop ==="
echo '{"decision": "allow"}'
exit 0
