#!/usr/bin/env python3
"""データベース初期化スクリプト."""

import asyncio
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "apps" / "api" / "src"))

from grimoire_api.repositories.database import DatabaseConnection


async def main():
    """データベース初期化メイン処理."""
    try:
        print("データベース初期化を開始します...")
        
        db = DatabaseConnection()
        await db.initialize_tables()
        
        print("✅ データベース初期化が完了しました!")
        print("📍 作成されたテーブル:")
        print("  - pages (ページ情報)")
        print("  - process_logs (処理ログ)")
        
    except Exception as e:
        print(f"❌ データベース初期化に失敗しました: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())