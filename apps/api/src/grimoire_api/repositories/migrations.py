"""Versioned SQLite schema migrations."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import aiosqlite

from ..utils.exceptions import DatabaseError

LATEST_SCHEMA_VERSION = 7


class SchemaMigrationError(DatabaseError):
    """The database schema cannot be migrated safely."""


@dataclass(frozen=True)
class Migration:
    """One ordered schema migration."""

    version: int
    name: str
    apply: Callable[[aiosqlite.Connection], Awaitable[None]]


@dataclass(frozen=True)
class SchemaInspection:
    """Read-only result used to plan a database migration."""

    current_version: int
    has_history: bool
    is_empty: bool

    @property
    def pending_versions(self) -> tuple[int, ...]:
        """Versions that still need to be applied."""
        return tuple(range(self.current_version + 1, LATEST_SCHEMA_VERSION + 1))

    @property
    def migration_required(self) -> bool:
        """Whether migration or legacy-history bootstrapping is required."""
        return bool(self.pending_versions) or not self.has_history

    @property
    def backup_required(self) -> bool:
        """Whether existing data must be backed up before migration."""
        return self.migration_required and not self.is_empty


BASE_PAGE_COLUMNS = (
    "id",
    "url",
    "title",
    "memo",
    "summary",
    "keywords",
    "created_at",
    "updated_at",
    "weaviate_id",
)
PROCESS_LOG_COLUMNS = (
    "id",
    "page_id",
    "job_id",
    "attempt",
    "url",
    "status",
    "error_message",
    "created_at",
)
JOB_COLUMNS = (
    "id",
    "page_id",
    "kind",
    "status",
    "current_step",
    "start_step",
    "attempt",
    "error_message",
    "created_at",
    "started_at",
    "finished_at",
)
REPAIR_CASE_COLUMNS = (
    "id",
    "page_id",
    "source",
    "report_url",
    "reasons",
    "status",
    "detected_at",
    "resolved_at",
)


async def _migration_1(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """CREATE TABLE pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            memo TEXT,
            summary TEXT,
            keywords TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            weaviate_id TEXT
        )"""
    )
    await conn.execute(
        """CREATE TABLE process_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER,
            url TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (page_id) REFERENCES pages(id)
        )"""
    )


async def _migration_2(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        "ALTER TABLE pages ADD COLUMN last_success_step TEXT DEFAULT NULL"
    )


async def _migration_3(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        "ALTER TABLE pages ADD COLUMN status TEXT NOT NULL DEFAULT 'queued'"
    )
    await conn.execute(
        """CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            current_step TEXT,
            start_step TEXT NOT NULL,
            attempt INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            FOREIGN KEY (page_id) REFERENCES pages(id)
        )"""
    )
    await conn.execute(
        """UPDATE pages SET status = CASE
            WHEN last_success_step = 'completed'
                 OR (summary IS NOT NULL AND weaviate_id IS NOT NULL)
            THEN 'succeeded' ELSE 'failed' END"""
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_process_logs_page_id ON process_logs(page_id)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_process_logs_status ON process_logs(status)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pages_last_success_step "
        "ON pages(last_success_step)"
    )
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_pages_status ON pages(status)")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_status_created "
        "ON jobs(status, created_at, id)"
    )
    await conn.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_active_page ON jobs(page_id)
        WHERE status IN ('queued', 'running')"""
    )


async def _migration_4(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """CREATE TABLE repair_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL UNIQUE,
            source TEXT NOT NULL,
            report_url TEXT,
            reasons TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            FOREIGN KEY (page_id) REFERENCES pages(id)
        )"""
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_repair_cases_status "
        "ON repair_cases(status, detected_at)"
    )


async def _migration_5(conn: aiosqlite.Connection) -> None:
    """Treat legacy naive timestamps as UTC and store canonical ISO 8601 values."""
    timestamp_columns = {
        "pages": ("created_at", "updated_at"),
        "process_logs": ("created_at",),
        "jobs": ("created_at", "started_at", "finished_at"),
        "repair_cases": ("detected_at", "resolved_at"),
    }
    for table, columns in timestamp_columns.items():
        for column in columns:
            invalid = await (
                await conn.execute(
                    f'''SELECT 1 FROM "{table}"
                    WHERE "{column}" IS NOT NULL
                    AND strftime('%Y-%m-%dT%H:%M:%fZ', "{column}") IS NULL
                    LIMIT 1'''
                )
            ).fetchone()
            if invalid is not None:
                raise SchemaMigrationError(
                    f"Invalid timestamp in {table}.{column}; UTC migration refused"
                )
            await conn.execute(
                f'''UPDATE "{table}"
                SET "{column}" = strftime('%Y-%m-%dT%H:%M:%fZ', "{column}")
                WHERE "{column}" IS NOT NULL'''
            )


async def _migration_6(conn: aiosqlite.Connection) -> None:
    """Turn mutable process logs into job-attempt event history."""
    await conn.execute("ALTER TABLE process_logs RENAME TO legacy_process_logs")
    await conn.execute(
        """CREATE TABLE process_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER,
            job_id INTEGER,
            attempt INTEGER,
            url TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (page_id) REFERENCES pages(id),
            FOREIGN KEY (job_id) REFERENCES jobs(id),
            CHECK (attempt IS NULL OR attempt >= 0)
        )"""
    )
    await conn.execute(
        """INSERT INTO process_logs
        (id, page_id, job_id, attempt, url, status, error_message, created_at)
        SELECT id, page_id, NULL, NULL, url,
               CASE WHEN status = 'started' THEN 'legacy_orphaned' ELSE status END,
               CASE WHEN status = 'started' AND error_message IS NULL
                    THEN 'Migrated without a recoverable job/attempt association'
                    ELSE error_message END,
               created_at
        FROM legacy_process_logs"""
    )
    await conn.execute("DROP TABLE legacy_process_logs")
    await conn.execute("CREATE INDEX idx_process_logs_page_id ON process_logs(page_id)")
    await conn.execute("CREATE INDEX idx_process_logs_status ON process_logs(status)")
    await conn.execute(
        "CREATE INDEX idx_process_logs_job_attempt "
        "ON process_logs(job_id, attempt, created_at, id)"
    )


async def _migration_7(conn: aiosqlite.Connection) -> None:
    """Constrain persisted states and align indexes with repository queries."""
    await conn.execute(
        """CREATE TABLE new_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            memo TEXT,
            summary TEXT,
            keywords TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            weaviate_id TEXT,
            last_success_step TEXT DEFAULT NULL
                CHECK (last_success_step IS NULL OR last_success_step IN
                    ('downloaded', 'llm_processed', 'vectorized', 'completed')),
            status TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'processing', 'succeeded', 'failed'))
        )"""
    )
    await conn.execute(
        """CREATE TABLE new_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('initial', 'retry', 'reprocess')),
            status TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
            current_step TEXT CHECK (current_step IS NULL OR current_step IN
                ('downloaded', 'llm_processed', 'vectorized', 'completed')),
            start_step TEXT NOT NULL
                CHECK (start_step IN ('download', 'llm', 'vectorize')),
            attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0),
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            FOREIGN KEY (page_id) REFERENCES new_pages(id)
        )"""
    )
    await conn.execute(
        """CREATE TABLE new_repair_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL UNIQUE,
            source TEXT NOT NULL,
            report_url TEXT,
            reasons TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'resolved')),
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            FOREIGN KEY (page_id) REFERENCES new_pages(id)
        )"""
    )
    await conn.execute(
        """CREATE TABLE new_process_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER,
            job_id INTEGER,
            attempt INTEGER,
            url TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN (
                'started', 'completed', 'legacy_orphaned', 'job_queued',
                'job_claimed', 'download_completed', 'llm_completed',
                'vectorize_completed', 'pipeline_completed', 'succeeded',
                'failed', 'interrupted', 'url_updated')),
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (page_id) REFERENCES new_pages(id),
            FOREIGN KEY (job_id) REFERENCES new_jobs(id),
            CHECK (attempt IS NULL OR attempt >= 0)
        )"""
    )

    for table in ("pages", "jobs", "repair_cases", "process_logs"):
        columns = ", ".join(_expected_tables(6)[table])
        await conn.execute(
            f'INSERT INTO "new_{table}" ({columns}) SELECT {columns} FROM "{table}"'
        )

    for table in ("process_logs", "repair_cases", "jobs", "pages"):
        await conn.execute(f'DROP TABLE "{table}"')
    for table in ("pages", "jobs", "repair_cases", "process_logs"):
        await conn.execute(f'ALTER TABLE "new_{table}" RENAME TO "{table}"')

    await conn.execute(
        "CREATE INDEX idx_pages_last_success_step ON pages(last_success_step)"
    )
    await conn.execute("CREATE INDEX idx_pages_status ON pages(status)")
    await conn.execute(
        "CREATE INDEX idx_jobs_status_created ON jobs(status, created_at, id)"
    )
    await conn.execute(
        "CREATE UNIQUE INDEX idx_jobs_active_page ON jobs(page_id) "
        "WHERE status IN ('queued', 'running')"
    )
    await conn.execute(
        "CREATE INDEX idx_jobs_page_created ON jobs(page_id, created_at DESC, id DESC)"
    )
    await conn.execute(
        "CREATE INDEX idx_repair_cases_status "
        "ON repair_cases(status, detected_at DESC, id DESC)"
    )
    await conn.execute(
        "CREATE INDEX idx_process_logs_page_id "
        "ON process_logs(page_id, status, created_at DESC)"
    )
    await conn.execute(
        "CREATE INDEX idx_process_logs_status ON process_logs(status, created_at DESC)"
    )
    await conn.execute(
        "CREATE INDEX idx_process_logs_job_attempt "
        "ON process_logs(job_id, attempt, created_at, id)"
    )


MIGRATIONS = (
    Migration(1, "create_pages_and_process_logs", _migration_1),
    Migration(2, "add_last_success_step", _migration_2),
    Migration(3, "add_persistent_jobs", _migration_3),
    Migration(4, "add_repair_cases", _migration_4),
    Migration(5, "normalize_timestamps_to_utc", _migration_5),
    Migration(6, "add_job_attempt_event_history", _migration_6),
    Migration(7, "add_state_constraints_and_query_indexes", _migration_7),
)


async def _table_names(conn: aiosqlite.Connection) -> set[str]:
    cursor = await conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    )
    return {row[0] for row in await cursor.fetchall()}


async def _column_names(conn: aiosqlite.Connection, table: str) -> tuple[str, ...]:
    cursor = await conn.execute(f'PRAGMA table_info("{table}")')
    return tuple(row[1] for row in await cursor.fetchall())


async def _table_sql(conn: aiosqlite.Connection, table: str) -> str:
    row = await (
        await conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
    ).fetchone()
    return " ".join(str(row[0]).split()) if row and row[0] else ""


async def _validate_history_table(conn: aiosqlite.Connection) -> None:
    """Validate the migration ledger before trusting its contents."""
    cursor = await conn.execute('PRAGMA table_info("schema_migrations")')
    signature = tuple(
        (row[1], row[2], row[3], row[4], row[5]) for row in await cursor.fetchall()
    )
    expected = (
        ("version", "INTEGER", 0, None, 1),
        ("name", "TEXT", 1, None, 0),
        ("applied_at", "TIMESTAMP", 1, "CURRENT_TIMESTAMP", 0),
    )
    if signature != expected:
        raise SchemaMigrationError(
            f"Corrupt SQLite migration history table: {signature}; expected {expected}"
        )


def _expected_tables(version: int) -> dict[str, tuple[str, ...]]:
    page_columns: tuple[str, ...] = BASE_PAGE_COLUMNS
    if version >= 2:
        page_columns += ("last_success_step",)
    if version >= 3:
        page_columns += ("status",)

    process_log_columns = (
        PROCESS_LOG_COLUMNS
        if version >= 6
        else tuple(
            column
            for column in PROCESS_LOG_COLUMNS
            if column not in {"job_id", "attempt"}
        )
    )
    tables = {
        "pages": page_columns,
        "process_logs": process_log_columns,
    }
    if version >= 3:
        tables["jobs"] = JOB_COLUMNS
    if version >= 4:
        tables["repair_cases"] = REPAIR_CASE_COLUMNS
    return tables


async def _validate_schema(conn: aiosqlite.Connection, version: int) -> None:
    expected = _expected_tables(version)
    actual_tables = await _table_names(conn)
    allowed_tables = set(expected) | {"schema_migrations"}
    unexpected = actual_tables - allowed_tables
    missing = set(expected) - actual_tables
    if missing or unexpected:
        raise SchemaMigrationError(
            f"Unknown SQLite schema at version {version}: "
            f"missing tables={sorted(missing)}, unexpected tables={sorted(unexpected)}"
        )

    for table, columns in expected.items():
        actual_columns = await _column_names(conn, table)
        if actual_columns != columns:
            raise SchemaMigrationError(
                f"Unknown SQLite schema at version {version}: table {table} "
                f"has columns {actual_columns}, expected {columns}"
            )

    if version >= 7:
        required_checks = {
            "pages": (
                "last_success_step IS NULL OR last_success_step IN",
                "status IN ('queued', 'processing', 'succeeded', 'failed')",
            ),
            "jobs": (
                "kind IN ('initial', 'retry', 'reprocess')",
                "status IN ('queued', 'running', 'succeeded', 'failed')",
                "current_step IS NULL OR current_step IN",
                "start_step IN ('download', 'llm', 'vectorize')",
                "attempt >= 0",
            ),
            "repair_cases": ("status IN ('pending', 'resolved')",),
            "process_logs": (
                "status IN (",
                "'legacy_orphaned'",
                "'url_updated'",
                "attempt IS NULL OR attempt >= 0",
            ),
        }
        for table, checks in required_checks.items():
            sql = await _table_sql(conn, table)
            if any(check not in sql for check in checks):
                raise SchemaMigrationError(
                    f"Corrupt SQLite schema: invalid CHECK constraints on {table}"
                )

    for table in set(expected) - {"pages"}:
        cursor = await conn.execute(f'PRAGMA foreign_key_list("{table}")')
        foreign_keys = {(row[3], row[2], row[4]) for row in await cursor.fetchall()}
        expected_foreign_keys = {("page_id", "pages", "id")}
        if table == "process_logs" and version >= 6:
            expected_foreign_keys.add(("job_id", "jobs", "id"))
        if foreign_keys != expected_foreign_keys:
            raise SchemaMigrationError(
                f"Corrupt SQLite schema: invalid foreign keys on {table}"
            )

    integrity = await (await conn.execute("PRAGMA integrity_check")).fetchone()
    if integrity is None or integrity[0] != "ok":
        detail = integrity[0] if integrity else "no result"
        raise SchemaMigrationError(f"Corrupt SQLite database: {detail}")

    if version >= 3:
        cursor = await conn.execute(
            "SELECT name, tbl_name, sql FROM sqlite_master WHERE type = 'index'"
        )
        actual_indexes = {row[0]: (row[1], row[2]) for row in await cursor.fetchall()}
        required_indexes = {
            "idx_process_logs_page_id": ("process_logs", ("page_id",), False),
            "idx_process_logs_status": ("process_logs", ("status",), False),
            "idx_pages_last_success_step": (
                "pages",
                ("last_success_step",),
                False,
            ),
            "idx_pages_status": ("pages", ("status",), False),
            "idx_jobs_status_created": (
                "jobs",
                ("status", "created_at", "id"),
                False,
            ),
            "idx_jobs_active_page": ("jobs", ("page_id",), True),
        }
        if version >= 4:
            required_indexes["idx_repair_cases_status"] = (
                "repair_cases",
                ("status", "detected_at"),
                False,
            )
        if version >= 6:
            required_indexes["idx_process_logs_job_attempt"] = (
                "process_logs",
                ("job_id", "attempt", "created_at", "id"),
                False,
            )
        if version >= 7:
            required_indexes.update(
                {
                    "idx_process_logs_page_id": (
                        "process_logs",
                        ("page_id", "status", "created_at"),
                        False,
                    ),
                    "idx_process_logs_status": (
                        "process_logs",
                        ("status", "created_at"),
                        False,
                    ),
                    "idx_jobs_page_created": (
                        "jobs",
                        ("page_id", "created_at", "id"),
                        False,
                    ),
                    "idx_repair_cases_status": (
                        "repair_cases",
                        ("status", "detected_at", "id"),
                        False,
                    ),
                }
            )
        missing_indexes = set(required_indexes) - set(actual_indexes)
        if missing_indexes:
            raise SchemaMigrationError(
                f"Corrupt SQLite schema: missing indexes={sorted(missing_indexes)}"
            )
        for name, (table, columns, unique) in required_indexes.items():
            actual_table, sql = actual_indexes[name]
            info = await (await conn.execute(f'PRAGMA index_info("{name}")')).fetchall()
            actual_columns = tuple(row[2] for row in info)
            index_list = await (
                await conn.execute(f'PRAGMA index_list("{table}")')
            ).fetchall()
            actual_unique = next(bool(row[2]) for row in index_list if row[1] == name)
            partial_is_valid = name != "idx_jobs_active_page" or (
                sql is not None and "WHERE status IN ('queued', 'running')" in sql
            )
            if (
                actual_table != table
                or actual_columns != columns
                or actual_unique != unique
                or not partial_is_valid
            ):
                raise SchemaMigrationError(
                    f"Corrupt SQLite schema: invalid index {name}"
                )


async def _detect_legacy_version(conn: aiosqlite.Connection) -> int:
    tables = await _table_names(conn)
    if not tables:
        return 0

    latest_tables = set(_expected_tables(LATEST_SCHEMA_VERSION))
    if tables == latest_tables:
        pages_sql = await _table_sql(conn, "pages")
        if "last_success_step IS NULL OR last_success_step IN" in pages_sql:
            return LATEST_SCHEMA_VERSION

    for version in range(1, LATEST_SCHEMA_VERSION + 1):
        expected = _expected_tables(version)
        if tables != set(expected):
            continue
        columns_match = True
        for table, columns in expected.items():
            if await _column_names(conn, table) != columns:
                columns_match = False
                break
        if columns_match:
            return version

    raise SchemaMigrationError(
        "Unknown unversioned SQLite schema; automatic migration was refused"
    )


async def _create_or_bootstrap_history(conn: aiosqlite.Connection) -> None:
    tables = await _table_names(conn)
    if "schema_migrations" in tables:
        return

    legacy_version = await _detect_legacy_version(conn)
    await conn.execute(
        """CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    for migration in MIGRATIONS[:legacy_version]:
        await conn.execute(
            "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
            (migration.version, migration.name),
        )


async def get_schema_version(conn: aiosqlite.Connection) -> int:
    """Return the current validated migration version."""
    tables = await _table_names(conn)
    if "schema_migrations" not in tables:
        raise SchemaMigrationError("SQLite schema has no migration history")

    await _validate_history_table(conn)

    cursor = await conn.execute(
        "SELECT version, name FROM schema_migrations ORDER BY version"
    )
    rows = list(await cursor.fetchall())
    if len(rows) > LATEST_SCHEMA_VERSION:
        raise SchemaMigrationError("SQLite schema version is newer than this release")

    expected = [(item.version, item.name) for item in MIGRATIONS[: len(rows)]]
    actual = [(row[0], row[1]) for row in rows]
    if actual != expected:
        raise SchemaMigrationError(
            f"Invalid SQLite migration history: {actual}; expected prefix {expected}"
        )
    return len(rows)


async def validate_database_schema(conn: aiosqlite.Connection) -> int:
    """Validate migration history and its corresponding physical schema."""
    version = await get_schema_version(conn)
    if version != LATEST_SCHEMA_VERSION:
        raise SchemaMigrationError(
            f"SQLite schema is version {version}; expected {LATEST_SCHEMA_VERSION}"
        )
    await _validate_schema(conn, version)
    return version


async def inspect_database_schema(conn: aiosqlite.Connection) -> SchemaInspection:
    """Inspect migration state without modifying the database."""
    tables = await _table_names(conn)
    if not tables:
        return SchemaInspection(current_version=0, has_history=False, is_empty=True)

    if "schema_migrations" in tables:
        version = await get_schema_version(conn)
        if version == 0:
            if tables != {"schema_migrations"}:
                raise SchemaMigrationError(
                    "Unknown SQLite schema with empty migration history"
                )
            return SchemaInspection(current_version=0, has_history=True, is_empty=True)
        await _validate_schema(conn, version)
        return SchemaInspection(
            current_version=version,
            has_history=True,
            is_empty=False,
        )

    version = await _detect_legacy_version(conn)
    await _validate_schema(conn, version)
    return SchemaInspection(
        current_version=version,
        has_history=False,
        is_empty=False,
    )


async def migrate_database(conn: aiosqlite.Connection) -> int:
    """Migrate a new or recognized legacy database to the latest version."""
    await conn.execute("BEGIN IMMEDIATE")
    try:
        await _create_or_bootstrap_history(conn)
        version = await get_schema_version(conn)
        if version:
            await _validate_schema(conn, version)
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise

    for migration in MIGRATIONS[version:]:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            await migration.apply(conn)
            await conn.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                (migration.version, migration.name),
            )
            await _validate_schema(conn, migration.version)
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    return await validate_database_schema(conn)
