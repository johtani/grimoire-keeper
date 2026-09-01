"""Test database initialization."""

import asyncio
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
    async def test_connection_worker_stops_after_context_exit(
        self, tmp_path: Path
    ) -> None:
        """aiosqlite接続の開始とワーカースレッド終了が停止しないことを確認."""
        async with asyncio.timeout(1):
            async with aiosqlite.connect(tmp_path / "lifecycle.db") as conn:
                row = await (await conn.execute("SELECT 1")).fetchone()

        assert row == (1,)

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


class TestStateCheckConstraints:
    """永続状態と処理ステップをDBレベルで制約する."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("query", "params"),
        [
            ("UPDATE pages SET status=? WHERE id=?", ("invalid", 1)),
            ("UPDATE pages SET last_success_step=? WHERE id=?", ("invalid", 1)),
            ("UPDATE jobs SET kind=? WHERE id=?", ("invalid", 1)),
            ("UPDATE jobs SET status=? WHERE id=?", ("invalid", 1)),
            ("UPDATE jobs SET current_step=? WHERE id=?", ("invalid", 1)),
            ("UPDATE jobs SET start_step=? WHERE id=?", ("invalid", 1)),
            ("UPDATE jobs SET attempt=? WHERE id=?", (-1, 1)),
            ("UPDATE repair_cases SET status=? WHERE id=?", ("invalid", 1)),
            ("UPDATE process_logs SET status=? WHERE id=?", ("invalid", 1)),
        ],
    )
    async def test_rejects_invalid_persisted_values(
        self, temp_db: DatabaseConnection, query: str, params: tuple
    ) -> None:
        page_id = await temp_db.execute(
            "INSERT INTO pages (url, title) VALUES (?, ?)",
            ("https://example.com", "example"),
        )
        await temp_db.execute(
            "INSERT INTO jobs (page_id, kind, start_step) VALUES (?, ?, ?)",
            (page_id, "initial", "download"),
        )
        await temp_db.execute(
            "INSERT INTO repair_cases (page_id, source, reasons) VALUES (?, ?, ?)",
            (page_id, "test", "[]"),
        )
        await temp_db.execute(
            "INSERT INTO process_logs (page_id, url, status) VALUES (?, ?, ?)",
            (page_id, "https://example.com", "failed"),
        )

        with pytest.raises(DatabaseError, match="CHECK constraint failed"):
            await temp_db.execute(query, params)

    @pytest.mark.asyncio
    async def test_accepts_nullable_steps(self, temp_db: DatabaseConnection) -> None:
        page_id = await temp_db.execute(
            "INSERT INTO pages (url, title, last_success_step) VALUES (?, ?, NULL)",
            ("https://example.com", "example"),
        )
        await temp_db.execute(
            "INSERT INTO jobs (page_id, kind, start_step, current_step) "
            "VALUES (?, ?, ?, NULL)",
            (page_id, "initial", "download"),
        )


class TestQueryIndexes:
    """主要repositoryクエリが実クエリ向けindexを利用する."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("query", "params", "index_name"),
        [
            (
                "SELECT * FROM jobs WHERE status='queued' "
                "ORDER BY created_at, id LIMIT 1",
                (),
                "idx_jobs_status_created",
            ),
            (
                "SELECT * FROM jobs WHERE page_id=? "
                "ORDER BY created_at DESC, id DESC LIMIT 1",
                (1,),
                "idx_jobs_page_created",
            ),
            (
                "SELECT error_message FROM process_logs "
                "WHERE page_id=? AND status='failed' "
                "ORDER BY created_at DESC LIMIT 1",
                (1,),
                "idx_process_logs_page_id",
            ),
            (
                "SELECT * FROM process_logs WHERE status=? ORDER BY created_at DESC",
                ("failed",),
                "idx_process_logs_status",
            ),
            (
                "SELECT * FROM repair_cases WHERE status=? "
                "ORDER BY detected_at DESC, id DESC",
                ("pending",),
                "idx_repair_cases_status",
            ),
        ],
    )
    async def test_query_plan_uses_expected_index(
        self,
        temp_db: DatabaseConnection,
        query: str,
        params: tuple,
        index_name: str,
    ) -> None:
        rows = await temp_db.fetch_all(f"EXPLAIN QUERY PLAN {query}", params)

        assert any(index_name in row["detail"] for row in rows)


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
        assert inspection.pending_versions == (3, 4, 5, 6, 7)
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
    async def test_legacy_timestamps_are_normalized_to_utc(
        self, tmp_path: Path
    ) -> None:
        """naive値とoffset付き値を同じUTC保存形式へ移行する."""
        db_path = str(tmp_path / "timestamps.db")
        await self.create_legacy_schema(db_path, 4)
        async with aiosqlite.connect(db_path) as conn:
            page = await conn.execute(
                """INSERT INTO pages
                (url, title, created_at, updated_at, status)
                VALUES (?, ?, ?, ?, ?)""",
                (
                    "https://example.com",
                    "example",
                    "2025-01-01 12:00:00",
                    "2025-01-02T01:30:00+09:00",
                    "queued",
                ),
            )
            page_id = int(page.lastrowid or 0)
            await conn.execute(
                """INSERT INTO process_logs
                (page_id, url, status, created_at) VALUES (?, ?, ?, ?)""",
                (page_id, "https://example.com", "started", "2025-01-01 12:00:00"),
            )
            await conn.commit()

        db = DatabaseConnection(db_path)
        await db.initialize_tables()
        page_row = await db.fetch_one(
            "SELECT created_at, updated_at FROM pages WHERE id=?", (page_id,)
        )
        log_row = await db.fetch_one(
            "SELECT created_at FROM process_logs WHERE page_id=?", (page_id,)
        )

        assert page_row is not None
        assert page_row["created_at"] == "2025-01-01T12:00:00.000Z"
        assert page_row["updated_at"] == "2025-01-01T16:30:00.000Z"
        assert log_row is not None
        assert log_row["created_at"] == "2025-01-01T12:00:00.000Z"

    @pytest.mark.asyncio
    async def test_legacy_started_log_becomes_terminal_event(
        self, tmp_path: Path
    ) -> None:
        """関連付け不能な旧 started 行は孤立した開始状態として残さない."""
        db_path = str(tmp_path / "legacy-started.db")
        await self.create_legacy_schema(db_path, 5)
        async with aiosqlite.connect(db_path) as conn:
            page = await conn.execute(
                "INSERT INTO pages (url, title, status) VALUES (?, ?, ?)",
                ("https://example.com", "example", "failed"),
            )
            page_id = int(page.lastrowid or 0)
            await conn.execute(
                "INSERT INTO process_logs (page_id, url, status) VALUES (?, ?, ?)",
                (page_id, "https://example.com", "started"),
            )
            await conn.commit()

        db = DatabaseConnection(db_path)
        await db.initialize_tables()

        log = await db.fetch_one(
            "SELECT * FROM process_logs WHERE page_id=?", (page_id,)
        )
        assert log is not None
        assert log["status"] == "legacy_orphaned"
        assert log["job_id"] is None
        assert log["attempt"] is None
        assert "recoverable job/attempt" in log["error_message"]

    @pytest.mark.asyncio
    async def test_version_6_data_is_preserved_by_constraint_migration(
        self, tmp_path: Path
    ) -> None:
        """制約追加時に親子関係とイベント履歴を保持する."""
        db_path = str(tmp_path / "version-6-data.db")
        await self.create_legacy_schema(db_path, 6)
        async with aiosqlite.connect(db_path) as conn:
            page = await conn.execute(
                "INSERT INTO pages "
                "(url, title, status, last_success_step) VALUES (?, ?, ?, ?)",
                ("https://example.com", "example", "failed", "downloaded"),
            )
            page_id = int(page.lastrowid or 0)
            job = await conn.execute(
                "INSERT INTO jobs "
                "(page_id, kind, status, start_step, current_step, attempt) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (page_id, "retry", "failed", "llm", "downloaded", 2),
            )
            job_id = int(job.lastrowid or 0)
            await conn.execute(
                "INSERT INTO repair_cases "
                "(page_id, source, reasons, status) VALUES (?, ?, ?, ?)",
                (page_id, "test", "[]", "pending"),
            )
            await conn.execute(
                "INSERT INTO process_logs "
                "(page_id, job_id, attempt, url, status) VALUES (?, ?, ?, ?, ?)",
                (page_id, job_id, 2, "https://example.com", "failed"),
            )
            await conn.commit()

        db = DatabaseConnection(db_path)
        await db.initialize_tables()

        page = await db.fetch_one("SELECT * FROM pages WHERE id=?", (page_id,))
        job = await db.fetch_one("SELECT * FROM jobs WHERE id=?", (job_id,))
        log = await db.fetch_one("SELECT * FROM process_logs WHERE job_id=?", (job_id,))
        repair = await db.fetch_one(
            "SELECT * FROM repair_cases WHERE page_id=?", (page_id,)
        )
        assert page is not None and page["last_success_step"] == "downloaded"
        assert job is not None and job["attempt"] == 2
        assert log is not None and log["page_id"] == page_id
        assert repair is not None and repair["status"] == "pending"

    @pytest.mark.asyncio
    async def test_invalid_version_6_state_rolls_back_constraint_migration(
        self, tmp_path: Path
    ) -> None:
        """不正な既存値はデータと履歴を変更せず移行を拒否する."""
        db_path = str(tmp_path / "invalid-version-6-state.db")
        await self.create_legacy_schema(db_path, 6)
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                "INSERT INTO pages (url, title, status) VALUES (?, ?, ?)",
                ("https://example.com", "example", "unknown"),
            )
            await conn.commit()

        db = DatabaseConnection(db_path)
        with pytest.raises(aiosqlite.IntegrityError, match="CHECK constraint failed"):
            await db.initialize_tables()

        row = await db.fetch_one("SELECT status FROM pages")
        assert row is not None and row["status"] == "unknown"
        async with db.connect() as conn:
            assert await get_schema_version(conn) == 6
            tables = await (
                await conn.execute(
                    "SELECT name FROM sqlite_master WHERE name LIKE 'new_%'"
                )
            ).fetchall()
        assert tables == []

    @pytest.mark.asyncio
    async def test_invalid_timestamp_migration_rolls_back_without_data_loss(
        self, tmp_path: Path
    ) -> None:
        """解釈不能な日時はNULL化せず、移行を拒否して元の値を保持する."""
        db_path = str(tmp_path / "invalid-timestamp.db")
        await self.create_legacy_schema(db_path, 4)
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                """INSERT INTO pages
                (url, title, created_at, updated_at, status)
                VALUES (?, ?, ?, ?, ?)""",
                (
                    "https://example.com",
                    "example",
                    "not-a-timestamp",
                    "2025-01-01 12:00:00",
                    "queued",
                ),
            )
            await conn.commit()

        db = DatabaseConnection(db_path)
        with pytest.raises(SchemaMigrationError, match="Invalid timestamp"):
            await db.initialize_tables()

        row = await db.fetch_one("SELECT created_at FROM pages")
        assert row is not None
        assert row["created_at"] == "not-a-timestamp"
        async with db.connect() as conn:
            assert await get_schema_version(conn) == 4

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
