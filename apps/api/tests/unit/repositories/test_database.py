"""Test database initialization."""

import tempfile
from dataclasses import replace
from pathlib import Path

import aiosqlite
import grimoire_api.repositories.migrations as migration_module
import pytest
from grimoire_api.repositories.database import DatabaseConnection
from grimoire_api.repositories.migrations import (
    LATEST_SCHEMA_VERSION,
    MIGRATIONS,
    SchemaInspection,
    SchemaMigrationError,
    get_schema_version,
    inspect_database_schema,
)
from grimoire_api.utils.exceptions import DatabaseError


class TestDatabaseInitialization:
    """DatabaseConnection.initialize_tables() のテストクラス."""

    @pytest.mark.asyncio
    async def test_indexes_created(self, temp_db: DatabaseConnection) -> None:
        """インデックスが正しく作成されることを確認."""
        rows = await temp_db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        index_names = {row["name"] for row in rows}

        assert "idx_process_logs_page_id" in index_names
        assert "idx_process_logs_status" in index_names
        assert "idx_pages_last_success_step" in index_names

    @pytest.mark.asyncio
    async def test_indexes_idempotent(self, temp_db: DatabaseConnection) -> None:
        """initialize_tables() を再度呼び出しても例外が発生しないことを確認."""
        await temp_db.initialize_tables()

        rows = await temp_db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        index_names = {row["name"] for row in rows}

        assert "idx_process_logs_page_id" in index_names
        assert "idx_process_logs_status" in index_names
        assert "idx_pages_last_success_step" in index_names

    @pytest.mark.asyncio
    async def test_schema_history_created(self, temp_db: DatabaseConnection) -> None:
        """新規DBに連続したマイグレーション履歴が作成される."""
        async with temp_db.connect() as conn:
            version = await get_schema_version(conn)
            rows = await (
                await conn.execute(
                    "SELECT version, name FROM schema_migrations ORDER BY version"
                )
            ).fetchall()

        assert version == LATEST_SCHEMA_VERSION
        assert rows == [(item.version, item.name) for item in MIGRATIONS]

    @pytest.mark.asyncio
    async def test_latest_schema_inspection_requires_no_migration(
        self, temp_db: DatabaseConnection
    ) -> None:
        """最新版DBの読み取り専用検査では移行もバックアップも不要になる."""
        async with temp_db.connect() as conn:
            inspection = await inspect_database_schema(conn)

        assert inspection == SchemaInspection(
            current_version=LATEST_SCHEMA_VERSION,
            has_history=True,
            is_empty=False,
        )
        assert inspection.migration_required is False
        assert inspection.backup_required is False


class TestForeignKeyConstraints:
    """全接続でSQLiteの外部キー制約が有効になることを検証する."""

    @pytest.mark.asyncio
    async def test_foreign_keys_are_enabled(self, temp_db: DatabaseConnection) -> None:
        """共通接続でforeign_keys PRAGMAが有効になることを確認する."""
        async with temp_db.connect() as conn:
            row = await (await conn.execute("PRAGMA foreign_keys")).fetchone()

        assert row is not None
        assert row[0] == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("query", "params"),
        [
            (
                "INSERT INTO process_logs (page_id, url, status) VALUES (?, ?, ?)",
                (999, "https://example.com", "failed"),
            ),
            (
                "INSERT INTO jobs (page_id, kind, status, start_step) "
                "VALUES (?, ?, ?, ?)",
                (999, "initial", "queued", "download"),
            ),
            (
                "INSERT INTO repair_cases (page_id, source, reasons) VALUES (?, ?, ?)",
                (999, "test", "[]"),
            ),
        ],
    )
    async def test_rejects_unknown_page_id(
        self, temp_db: DatabaseConnection, query: str, params: tuple
    ) -> None:
        """関連テーブルに存在しないpage_idを登録できないことを確認する."""
        with pytest.raises(DatabaseError, match="FOREIGN KEY constraint failed"):
            await temp_db.execute(query, params)

    @pytest.mark.asyncio
    async def test_restricts_page_delete_until_child_is_deleted(
        self, temp_db: DatabaseConnection
    ) -> None:
        """関連行があるページは削除できず、関連行削除後は削除できる."""
        page_id = await temp_db.execute(
            "INSERT INTO pages (url, title) VALUES (?, ?)",
            ("https://example.com", "example"),
        )
        await temp_db.execute(
            "INSERT INTO process_logs (page_id, url, status) VALUES (?, ?, ?)",
            (page_id, "https://example.com", "failed"),
        )

        with pytest.raises(DatabaseError, match="FOREIGN KEY constraint failed"):
            await temp_db.execute("DELETE FROM pages WHERE id = ?", (page_id,))

        assert await temp_db.fetch_one("SELECT id FROM pages WHERE id = ?", (page_id,))
        assert await temp_db.fetch_one(
            "SELECT id FROM process_logs WHERE page_id = ?", (page_id,)
        )

        await temp_db.execute("DELETE FROM process_logs WHERE page_id = ?", (page_id,))
        await temp_db.execute("DELETE FROM pages WHERE id = ?", (page_id,))

        assert (
            await temp_db.fetch_one("SELECT id FROM pages WHERE id = ?", (page_id,))
            is None
        )


class TestReadOnlyDatabaseConnection:
    """DatabaseConnectionの読み取り専用接続を検証する."""

    @pytest.mark.asyncio
    async def test_fetches_from_read_only_database(self, tmp_path: Path) -> None:
        """読み取り専用モードでも既存DBを参照できることを確認する."""
        db_path = tmp_path / "readonly.db"
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute("CREATE TABLE samples (value TEXT NOT NULL)")
            await conn.execute("INSERT INTO samples VALUES ('ok')")
            await conn.commit()

        db = DatabaseConnection(str(db_path), read_only=True)

        row = await db.fetch_one("SELECT value FROM samples")

        assert row is not None
        assert row["value"] == "ok"

    @pytest.mark.asyncio
    async def test_read_only_database_rejects_writes(self, tmp_path: Path) -> None:
        """読み取り専用モードからの更新が失敗することを確認する."""
        db_path = tmp_path / "readonly.db"
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute("CREATE TABLE samples (value TEXT NOT NULL)")
            await conn.commit()

        db = DatabaseConnection(str(db_path), read_only=True)

        with pytest.raises(DatabaseError, match="attempt to write a readonly database"):
            await db.execute("INSERT INTO samples VALUES ('ng')")


class TestLegacyDatabaseMigration:
    """旧データベースの移行処理を検証する."""

    async def create_legacy_schema(self, db_path: str, version: int) -> None:
        """指定バージョン相当の履歴なしDBを作る."""
        async with aiosqlite.connect(db_path) as conn:
            for migration in MIGRATIONS[:version]:
                await migration.apply(conn)
            await conn.commit()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("legacy_version", range(1, LATEST_SCHEMA_VERSION + 1))
    async def test_each_known_legacy_schema_migrates(
        self, tmp_path: Path, legacy_version: int
    ) -> None:
        """既知の各旧スキーマを判定して最新版へ移行する."""
        db_path = str(tmp_path / f"legacy-{legacy_version}.db")
        await self.create_legacy_schema(db_path, legacy_version)

        db = DatabaseConnection(db_path)
        await db.initialize_tables()

        async with db.connect() as conn:
            assert await get_schema_version(conn) == LATEST_SCHEMA_VERSION

    @pytest.mark.asyncio
    async def test_legacy_inspection_is_read_only_and_requires_backup(
        self, tmp_path: Path
    ) -> None:
        """旧DBの事前検査は履歴を書かず、バックアップ必要と判定する."""
        db_path = str(tmp_path / "inspection.db")
        await self.create_legacy_schema(db_path, 2)

        db = DatabaseConnection(db_path, read_only=True)
        async with db.connect() as conn:
            inspection = await inspect_database_schema(conn)

        assert inspection.current_version == 2
        assert inspection.has_history is False
        assert inspection.pending_versions == (3, 4)
        assert inspection.backup_required is True

        async with aiosqlite.connect(db_path) as conn:
            tables = await (
                await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            ).fetchall()
        assert ("schema_migrations",) not in tables

    @pytest.mark.asyncio
    async def test_empty_database_inspection_does_not_require_backup(
        self, tmp_path: Path
    ) -> None:
        """空DBは移行対象だがバックアップ対象にはしない."""
        db_path = tmp_path / "empty.db"
        db_path.touch()

        db = DatabaseConnection(str(db_path), read_only=True)
        async with db.connect() as conn:
            inspection = await inspect_database_schema(conn)

        assert inspection.migration_required is True
        assert inspection.backup_required is False
        assert inspection.is_empty is True

    @pytest.mark.asyncio
    async def test_legacy_pages_are_backfilled_idempotently(self) -> None:
        """旧スキーマの完了・未完了ページを現在状態へ一度だけ移行する."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            async with aiosqlite.connect(db_path) as conn:
                await conn.execute(
                    """CREATE TABLE pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL, memo TEXT, summary TEXT, keywords TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    weaviate_id TEXT, last_success_step TEXT)"""
                )
                await conn.execute(
                    """CREATE TABLE process_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, page_id INTEGER,
                    url TEXT NOT NULL, status TEXT NOT NULL, error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (page_id) REFERENCES pages(id))"""
                )
                await conn.execute(
                    """INSERT INTO pages (url, title, summary, weaviate_id)
                    VALUES ('https://done.example.com', 'done', 'summary', 'uuid')"""
                )
                await conn.execute(
                    """INSERT INTO pages (url, title)
                    VALUES ('https://lost.example.com', 'lost')"""
                )
                await conn.commit()

            db = DatabaseConnection(db_path)
            await db.initialize_tables()
            await db.initialize_tables()

            rows = await db.fetch_all("SELECT url, status FROM pages ORDER BY id")
            assert [(row["url"], row["status"]) for row in rows] == [
                ("https://done.example.com", "succeeded"),
                ("https://lost.example.com", "failed"),
            ]
            jobs = await db.fetch_one("SELECT COUNT(*) AS count FROM jobs")
            assert jobs is not None and jobs["count"] == 0
        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_unknown_unversioned_schema_is_rejected(self, tmp_path: Path) -> None:
        """部分的な未知スキーマを推測で修復しない."""
        db_path = str(tmp_path / "unknown.db")
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute("CREATE TABLE pages (id INTEGER PRIMARY KEY)")
            await conn.commit()

        with pytest.raises(SchemaMigrationError, match="Unknown unversioned"):
            await DatabaseConnection(db_path).initialize_tables()

        async with aiosqlite.connect(db_path) as conn:
            tables = await (
                await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            ).fetchall()
        assert ("schema_migrations",) not in tables

    @pytest.mark.asyncio
    async def test_future_schema_version_is_rejected(self, tmp_path: Path) -> None:
        """アプリより新しいスキーマ履歴では安全に失敗する."""
        db_path = str(tmp_path / "future.db")
        db = DatabaseConnection(db_path)
        await db.initialize_tables()
        await db.execute(
            "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
            (LATEST_SCHEMA_VERSION + 1, "future"),
        )

        with pytest.raises(SchemaMigrationError, match="newer than this release"):
            await db.initialize_tables()

    @pytest.mark.asyncio
    async def test_corrupt_migration_history_table_is_rejected(
        self, tmp_path: Path
    ) -> None:
        """履歴行が正しくても履歴テーブルの制約破損を受理しない."""
        db_path = str(tmp_path / "corrupt-history.db")
        db = DatabaseConnection(db_path)
        await db.initialize_tables()
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                "ALTER TABLE schema_migrations RENAME TO old_schema_migrations"
            )
            await conn.execute(
                "CREATE TABLE schema_migrations (version INTEGER, name TEXT)"
            )
            await conn.execute(
                "INSERT INTO schema_migrations SELECT version, name "
                "FROM old_schema_migrations"
            )
            await conn.execute("DROP TABLE old_schema_migrations")
            await conn.commit()

        with pytest.raises(SchemaMigrationError, match="history table"):
            await db.initialize_tables()

    @pytest.mark.asyncio
    async def test_corrupt_versioned_schema_is_rejected(self, tmp_path: Path) -> None:
        """履歴と実スキーマが一致しないDBでは失敗する."""
        db_path = str(tmp_path / "corrupt.db")
        db = DatabaseConnection(db_path)
        await db.initialize_tables()
        await db.execute("DROP INDEX idx_pages_status")

        with pytest.raises(SchemaMigrationError, match="missing indexes"):
            await db.initialize_tables()

    @pytest.mark.asyncio
    async def test_legacy_schema_with_existing_indexes_migrates(
        self, tmp_path: Path
    ) -> None:
        """旧実装が作成済みのインデックスを保持して移行する."""
        db_path = str(tmp_path / "indexed-legacy.db")
        await self.create_legacy_schema(db_path, 2)
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                "CREATE INDEX idx_process_logs_page_id ON process_logs(page_id)"
            )
            await conn.execute(
                "CREATE INDEX idx_process_logs_status ON process_logs(status)"
            )
            await conn.execute(
                "CREATE INDEX idx_pages_last_success_step ON pages(last_success_step)"
            )
            await conn.commit()

        db = DatabaseConnection(db_path)
        await db.initialize_tables()

        async with db.connect() as conn:
            assert await get_schema_version(conn) == LATEST_SCHEMA_VERSION

    @pytest.mark.asyncio
    async def test_legacy_schema_with_invalid_named_index_is_rejected(
        self, tmp_path: Path
    ) -> None:
        """名前だけ一致する不正な既存インデックスを受理しない."""
        db_path = str(tmp_path / "invalid-index.db")
        await self.create_legacy_schema(db_path, 2)
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                "CREATE INDEX idx_process_logs_page_id ON process_logs(status)"
            )
            await conn.commit()

        with pytest.raises(SchemaMigrationError, match="invalid index"):
            await DatabaseConnection(db_path).initialize_tables()

    @pytest.mark.asyncio
    async def test_failed_migration_is_rolled_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DDL失敗時にスキーマ変更と履歴を同時にロールバックする."""
        db_path = str(tmp_path / "rollback.db")
        await self.create_legacy_schema(db_path, 2)

        migration = MIGRATIONS[2]

        async def fail_after_ddl(conn: aiosqlite.Connection) -> None:
            await migration.apply(conn)
            await conn.execute("CREATE TABLE migration_marker (id INTEGER)")
            raise aiosqlite.OperationalError("injected migration failure")

        monkeypatch.setattr(
            migration_module,
            "MIGRATIONS",
            (
                *MIGRATIONS[:2],
                replace(migration, apply=fail_after_ddl),
                *MIGRATIONS[3:],
            ),
        )

        db = DatabaseConnection(db_path)
        with pytest.raises(aiosqlite.OperationalError, match="injected"):
            await db.initialize_tables()

        async with aiosqlite.connect(db_path) as conn:
            page_columns = await (
                await conn.execute("PRAGMA table_info(pages)")
            ).fetchall()
            tables = await (
                await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            ).fetchall()
            history = await (
                await conn.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            ).fetchall()

        assert "status" not in {row[1] for row in page_columns}
        assert ("jobs",) not in tables
        assert ("migration_marker",) not in tables
        assert history == [(1,), (2,)]
