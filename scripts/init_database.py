#!/usr/bin/env python3
"""Database initialization script."""

import asyncio
import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "apps" / "api" / "src"))

import weaviate  # noqa: E402
from grimoire_api.config import settings  # noqa: E402
from grimoire_api.repositories.database import DatabaseConnection  # noqa: E402
from grimoire_api.repositories.migrations import (  # noqa: E402
    LATEST_SCHEMA_VERSION,
    inspect_database_schema,
    validate_database_schema,
)
from grimoire_api.services.vectorizer import VectorizerService  # noqa: E402

MIGRATION_PENDING_EXIT_CODE = 10
NEW_DATABASE_EXIT_CODE = 11


async def initialize_database() -> bool:
    """データベースとWeaviateスキーマを初期化."""
    print("🔧 Initializing database...")

    try:
        # SQLiteデータベース初期化
        db = DatabaseConnection()
        await db.initialize_tables()
        print(
            "✅ SQLite database migrated successfully "
            f"(schema version {LATEST_SCHEMA_VERSION})!"
        )

        # Weaviateスキーマ初期化
        print("🔧 Initializing Weaviate schema...")
        from unittest.mock import MagicMock

        weaviate_client = weaviate.connect_to_local(
            host=settings.WEAVIATE_HOST,
            port=settings.WEAVIATE_PORT,
            headers={"X-OpenAI-Api-Key": settings.OPENAI_API_KEY},
        )
        try:
            vectorizer = VectorizerService(
                MagicMock(),  # type: ignore
                MagicMock(),  # type: ignore
                MagicMock(),  # type: ignore
                weaviate_client,
            )  # スキーマ作成のみなのでリポジトリはダミーオブジェクト

            # Weaviate接続確認
            if await vectorizer.health_check():
                await vectorizer.ensure_schema()
                print("✅ Weaviate schema created successfully!")
            else:
                print("⚠️  Weaviate is not running. Please start Weaviate first:")
                print("   docker compose -f docker-compose.prod.yml up -d weaviate")
                return False
        finally:
            weaviate_client.close()

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
        print(
            "✅ SQLite database migrated successfully "
            f"(schema version {LATEST_SCHEMA_VERSION})!"
        )

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

        async with db.connect() as conn:
            schema_version = await validate_database_schema(conn)
        print(f"✅ SQLite schema version: {schema_version}")

        # テーブル存在確認
        tables_query = """
        SELECT name FROM sqlite_master
        WHERE type='table'
          AND name IN ('pages', 'process_logs', 'jobs', 'repair_cases')
        """
        tables = await db.fetch_all(tables_query)
        table_names = [table["name"] for table in tables]

        print(f"📊 Found tables: {table_names}")

        if {"pages", "process_logs", "jobs", "repair_cases"}.issubset(table_names):
            print("✅ All required tables exist")

            # レコード数確認
            pages_result = await db.fetch_one("SELECT COUNT(*) as count FROM pages")
            logs_result = await db.fetch_one(
                "SELECT COUNT(*) as count FROM process_logs"
            )
            jobs_result = await db.fetch_one("SELECT COUNT(*) as count FROM jobs")

            pages_count = pages_result["count"] if pages_result else 0
            logs_count = logs_result["count"] if logs_result else 0
            jobs_count = jobs_result["count"] if jobs_result else 0

            print(f"📈 Pages: {pages_count} records")
            print(f"📈 Process logs: {logs_count} records")
            print(f"📈 Jobs: {jobs_count} records")
        else:
            print("❌ Required tables are missing")
            return False

    except Exception as e:
        print(f"❌ Database check failed: {str(e)}")
        return False

    return True


async def migration_status() -> int:
    """DBを変更せず、デプロイ前に必要な移行とバックアップを判定する."""
    print("🔍 Inspecting SQLite migration status...")
    db_path = Path(settings.DATABASE_PATH)
    if not db_path.exists():
        print("Current schema version: none (new database)")
        print(f"Target schema version: {LATEST_SCHEMA_VERSION}")
        print(f"Pending migrations: {LATEST_SCHEMA_VERSION}")
        print("Migration required: yes")
        print("Backup required: no")
        return NEW_DATABASE_EXIT_CODE

    try:
        db = DatabaseConnection(read_only=True)
        async with db.connect() as conn:
            inspection = await inspect_database_schema(conn)
    except Exception as e:
        print(f"❌ SQLite migration inspection failed: {str(e)}")
        return 1

    history = "versioned" if inspection.has_history else "legacy/unversioned"
    current = "none" if inspection.is_empty else str(inspection.current_version)
    print(f"Current schema version: {current} ({history})")
    print(f"Target schema version: {LATEST_SCHEMA_VERSION}")
    print(f"Pending migrations: {len(inspection.pending_versions)}")
    print(f"Migration required: {'yes' if inspection.migration_required else 'no'}")
    print(f"Backup required: {'yes' if inspection.backup_required else 'no'}")

    if inspection.backup_required:
        return MIGRATION_PENDING_EXIT_CODE
    if inspection.migration_required:
        return NEW_DATABASE_EXIT_CODE
    return 0


async def reset_database() -> bool:
    """データベースリセット（開発用）."""
    print("🗑️  Resetting database...")

    try:
        db = DatabaseConnection()

        # テーブル削除
        await db.execute("DROP TABLE IF EXISTS repair_cases")
        await db.execute("DROP TABLE IF EXISTS jobs")
        await db.execute("DROP TABLE IF EXISTS process_logs")
        await db.execute("DROP TABLE IF EXISTS pages")
        await db.execute("DROP TABLE IF EXISTS schema_migrations")
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
    migration-status
               Read-only migration preflight (exit 10=backup, 11=new DB)
    reset      Reset database (WARNING: All data will be lost!)
    help       Show this help message

Examples:
    python scripts/init_database.py
    python scripts/init_database.py init
    python scripts/init_database.py sqlite
    python scripts/init_database.py check
    python scripts/init_database.py migration-status
    python scripts/init_database.py reset
""")


async def main() -> None:
    """メイン処理."""
    command = sys.argv[1] if len(sys.argv) > 1 else "init"

    if command == "help":
        print_usage()
        return

    if command == "migration-status":
        sys.exit(await migration_status())

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
