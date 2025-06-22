#!/usr/bin/env python3
"""SQLite database CLI helper script."""

import subprocess
import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "apps" / "api" / "src"))

from grimoire_api.config import settings


def main():
    """SQLite CLIを起動."""
    db_path = settings.DATABASE_PATH

    print(f"🗄️  Opening SQLite database: {db_path}")
    print("💡 Useful commands:")
    print("   .tables          - Show all tables")
    print("   .schema          - Show table schemas")
    print("   .headers on      - Show column headers")
    print("   .mode column     - Format output as columns")
    print("   .quit            - Exit")
    print("=" * 50)

    # sqlite3コマンドを実行
    try:
        subprocess.run(["sqlite3", db_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running sqlite3: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ sqlite3 command not found. Please install sqlite3:")
        print("   sudo apt-get install sqlite3")
        sys.exit(1)


if __name__ == "__main__":
    main()
