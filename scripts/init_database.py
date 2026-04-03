#!/usr/bin/env python3
"""Database initialization script."""

import asyncio
import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "apps" / "api" / "src"))

from grimoire_api.repositories.database import DatabaseConnection  # noqa: E402
from grimoire_api.services.vectorizer import VectorizerService  # noqa: E402


async def initialize_database() -> bool:
    """データベースとWeaviateスキーマを初期化."""
    print("🔧 Initializing database...")

    try:
        # SQLiteデータベース初期化
        db = DatabaseConnection()
        await db.initialize_tables()
        print("✅ SQLite database tables created successfully!")

        # Weaviateスキーマ初期化
        print("🔧 Initializing Weaviate schema...")
        from unittest.mock import MagicMock

        vectorizer = VectorizerService(
            MagicMock(),  # type: ignore
            MagicMock(),  # type: ignore
            MagicMock(),  # type: ignore
        )  # スキーマ作成のみなのでダミーオブジェクト

        # Weaviate接続確認
        if await vectorizer.health_check():
            await vectorizer.ensure_schema()
            print("✅ Weaviate schema created successfully!")
        else:
            print("⚠️  Weaviate is not running. Please start Weaviate first:")
            print("   docker compose up -d weaviate")
            return False

    except Exception as e:
        print(f"❌ Database initialization failed: {str(e)}")
        return False

    print("🎉 Database initialization completed!")
    return True


async def initialize_sqlite_only() -> bool:
    """データベースのみ初期化（Weaviate不要）."""
    print("🔧 Initializing SQLite database...")

    try:
        # SQLiteデータベース初期化
        db = DatabaseConnection()
        await db.initialize_tables()
        print("✅ SQLite database tables created successfully!")

    except Exception as e:
        print(f"❌ SQLite initialization failed: {str(e)}")
        return False

    print("🎉 SQLite initialization completed!")
    print(
        "📝 Next: Start Weaviate and run "
        "'python scripts/init_database.py init' for full setup"
    )
    return True


async def check_database_status() -> bool:
    """データベース状態確認."""
    print("🔍 Checking database status...")

    try:
        db = DatabaseConnection()

        # テーブル存在確認
        tables_query = """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name IN ('pages', 'process_logs')
        """
        tables = await db.fetch_all(tables_query)
        table_names = [table["name"] for table in tables]

        print(f"📊 Found tables: {table_names}")

        if "pages" in table_names and "process_logs" in table_names:
            print("✅ All required tables exist")

            # レコード数確認
            pages_result = await db.fetch_one("SELECT COUNT(*) as count FROM pages")
            logs_result = await db.fetch_one(
                "SELECT COUNT(*) as count FROM process_logs"
            )

            pages_count = pages_result["count"] if pages_result else 0
            logs_count = logs_result["count"] if logs_result else 0

            print(f"📈 Pages: {pages_count} records")
            print(f"📈 Process logs: {logs_count} records")
        else:
            print("❌ Required tables are missing")
            return False

    except Exception as e:
        print(f"❌ Database check failed: {str(e)}")
        return False

    return True


async def reset_database() -> bool:
    """データベースリセット（開発用）."""
    print("🗑️  Resetting database...")

    try:
        db = DatabaseConnection()

        # テーブル削除
        await db.execute("DROP TABLE IF EXISTS process_logs")
        await db.execute("DROP TABLE IF EXISTS pages")
        print("🗑️  Existing tables dropped")

        # テーブル再作成
        await db.initialize_tables()
        print("✅ Tables recreated successfully!")

    except Exception as e:
        print(f"❌ Database reset failed: {str(e)}")
        return False

    print("🎉 Database reset completed!")
    return True


def print_usage() -> None:
    """使用方法を表示."""
    print("""
🔧 Database Initialization Script

Usage:
    python scripts/init_database.py [command]

Commands:
    init       Initialize database and Weaviate schema (default)
    sqlite     Initialize SQLite database only (Weaviate not required)
    check      Check database status
    reset      Reset database (WARNING: All data will be lost!)
    help       Show this help message

Examples:
    python scripts/init_database.py
    python scripts/init_database.py init
    python scripts/init_database.py sqlite
    python scripts/init_database.py check
    python scripts/init_database.py reset
""")


async def main() -> None:
    """メイン処理."""
    command = sys.argv[1] if len(sys.argv) > 1 else "init"

    if command == "help":
        print_usage()
        return

    print("🚀 Grimoire Keeper Database Manager")
    print("=" * 40)

    if command == "init":
        success = await initialize_database()
    elif command == "sqlite":
        success = await initialize_sqlite_only()
    elif command == "check":
        success = await check_database_status()
    elif command == "reset":
        # 確認プロンプト
        response = input("⚠️  This will delete all data. Continue? (y/N): ")
        if response.lower() != "y":
            print("❌ Operation cancelled")
            return
        success = await reset_database()
    else:
        print(f"❌ Unknown command: {command}")
        print_usage()
        return

    if success:
        print("\n✅ Operation completed successfully!")
    else:
        print("\n❌ Operation failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
