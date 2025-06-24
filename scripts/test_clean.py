#!/usr/bin/env python3
"""警告なしでテストを実行するスクリプト."""

import os
import subprocess
import sys


def main() -> None:
    """警告を抑制してテストを実行."""
    # 環境変数を設定
    env = os.environ.copy()
    env["PYTHONWARNINGS"] = "ignore"

    # pytestを実行
    cmd = ["uv", "run", "pytest", "--tb=short", "-q", "--disable-warnings"]

    try:
        result = subprocess.run(cmd, env=env, cwd="/workspace")
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error running tests: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
