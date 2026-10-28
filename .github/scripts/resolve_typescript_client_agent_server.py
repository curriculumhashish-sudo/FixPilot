#!/usr/bin/env python3
"""报告 TypeScript 客户端的固定 Agent Server 是否已释放。

版本 PR 将客户端固定到即将发布的版本，因此版本的 openapi.json 和映像仅在 PR 合并后才
存在。 CI 使用这些输出从该窗口中分支自己的源读取合约。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tomllib
import urllib.error
import urllib.request
from pathlib import Path


IMAGE_RE = re.compile(
    r"^ghcr\.io/openhands/agent-server:(?P<version>\d+\.\d+\.\d+)-python$"
)
OPENAPI_URL = (
    "https://github.com/OpenHands/software-agent-sdk/releases/download/"
    "v{version}/openapi.json"
)


def pinned_version(client_root: Path) -> str:
    package = json.loads((client_root / "package.json").read_text())
    image = package.get("config", {}).get("agentServerImage")
    match = IMAGE_RE.match(image) if isinstance(image, str) else None
    if not match:
        raise SystemExit(
            f"config.agentServerImage must use an exact release tag, got {image!r}"
        )
    return match["version"]


def source_version(pyproject: Path) -> str:
    return tomllib.loads(pyproject.read_text())["project"]["version"]


def contract_published(version: str) -> bool:
    try:
        with urllib.request.urlopen(OPENAPI_URL.format(version=version), timeout=30):
            return True
    except urllib.error.HTTPError as exc:
        # 除了 404 之外的任何情况都是暂时性故障，而不是“未释放”。
        if exc.code == 404:
            return False
        raise


def resolve(client_root: Path, pyproject: Path) -> dict[str, str]:
    pinned = pinned_version(client_root)
    pinned_is_source = pinned == source_version(pyproject)
    use_source = pinned_is_source and not contract_published(pinned)
    return {
        "pinned_version": pinned,
        "pinned_is_source": str(pinned_is_source).lower(),
        "use_source_contract": str(use_source).lower(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-root", type=Path, default=Path("clients/typescript"))
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path("openhands-agent-server/pyproject.toml"),
    )
    args = parser.parse_args()

    outputs = resolve(args.client_root, args.pyproject)
    lines = "".join(f"{key}={value}\n" for key, value in outputs.items())
    print(lines, end="")
    if github_output := os.environ.get("GITHUB_OUTPUT"):
        with open(github_output, "a") as fh:
            fh.write(lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
