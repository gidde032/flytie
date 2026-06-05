"""Database session management and schema bootstrap.

`Database` resolves the SQLite path from settings, creates the engine, applies
the schema via Alembic migrations bundled in `flytie.migrations`, and yields
sessions to callers.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.orm import Session, sessionmaker

from flytie.config import Settings
from flytie.migrations import MIGRATIONS_DIR
from flytie.models import Base


class IncompatibleDatabaseError(RuntimeError):
    """Raised when the database was migrated by a newer flytie than this build knows.

    Mitigates §8 of the spec ("the app refuses to start against a DB newer
    than its known head"). The user has typically installed a newer flytie,
    run a migration, then downgraded; continuing risks corrupting data, so
    we fail fast with an actionable recovery path.
    """


def _enable_sqlite_pragmas(dbapi_connection: object, _connection_record: object) -> None:
    """Turn on SQLite foreign key enforcement and sensible journal settings."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()


@dataclass
class Database:
    """Holds the engine and session factory for the lifetime of a command."""

    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]

    @classmethod
    def from_settings(cls, settings: Settings, echo: bool = False) -> Database:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{settings.db_path}"
        engine = create_engine(url, echo=echo, future=True)
        event.listen(engine, "connect", _enable_sqlite_pragmas)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        return cls(settings=settings, engine=engine, session_factory=session_factory)

    def create_schema(self) -> None:
        """Create the schema, guaranteeing the real tables exist afterward.

        Normally this runs the bundled Alembic migrations. But a database can
        end up *stamped but empty* — the `alembic_version` table says "head",
        yet the real tables are missing — if an earlier `init` was interrupted
        mid-run (SQLite auto-commits each DDL statement). In that state Alembic
        sees the stamp, runs nothing, and returns cleanly, so a naive
        "did upgrade raise?" check passes while the database is unusable.

        We therefore *verify* the schema after upgrading and repair it with a
        direct metadata build if the tables aren't actually there. The same
        direct build is the fallback if Alembic fails for any other reason.
        """
        try:
            self.upgrade_to_head()
        except Exception:
            self._build_schema_directly()
            return
        if not self.schema_is_complete():
            # Alembic ran (or no-op'd against a stale stamp) but the tables
            # are missing — a stamped-but-empty DB from an interrupted init.
            self._build_schema_directly()

    def schema_is_complete(self) -> bool:
        """True if the core `patterns` table physically exists in the database.

        Used both to detect a corrupt/half-built database and to decide
        whether `flytie init` should repair rather than report "already
        exists".
        """
        return inspect(self.engine).has_table("patterns")

    def _build_schema_directly(self) -> None:
        """Create every table from the ORM metadata and stamp Alembic at head."""
        Base.metadata.create_all(self.engine)
        self.stamp_alembic_head()

    def drop_schema(self) -> None:
        Base.metadata.drop_all(self.engine)
        # Drop the alembic_version table too so subsequent `upgrade` starts clean.
        with self.engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")

    def upgrade_to_head(self) -> None:
        """Run Alembic migrations up to head against this database."""
        # Lazy alembic imports — `alembic` is a heavy optional-ish dep and
        # lazy-importing keeps `import flytie.db` cheap when callers don't
        # need migrations. Import order is governed by the explicit
        # `[tool.ruff.lint.isort]` config in pyproject.toml.
        from alembic import command
        from alembic.config import Config

        cfg = Config()
        cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{self.settings.db_path}")
        command.upgrade(cfg, "head")

    def stamp_alembic_head(self) -> None:
        """Stamp the DB with the latest Alembic revision without running migrations."""
        from alembic import command
        from alembic.config import Config

        cfg = Config()
        cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{self.settings.db_path}")
        command.stamp(cfg, "head")

    def alembic_version(self) -> str | None:
        """Return the current Alembic revision recorded in the DB, or None."""
        with self.engine.begin() as conn:
            try:
                row = conn.exec_driver_sql("SELECT version_num FROM alembic_version").first()
            except Exception:
                return None
        return None if row is None else str(row[0])

    def known_revisions(self) -> set[str]:
        """The full set of revision IDs this build's bundled migrations contain."""
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config()
        cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
        script = ScriptDirectory.from_config(cfg)
        return {rev.revision for rev in script.walk_revisions()}

    def validate_compatibility(self) -> None:
        """Refuse to operate against a DB stamped at a revision we don't know.

        Spec §8 promises this guarantee. Practically, this catches the
        "user upgraded flytie, ran a migration, then downgraded" case — the
        DB has been schema-evolved beyond what this binary's bundled
        migrations describe, so continuing risks reading or writing columns
        the binary doesn't model correctly.

        A DB with no `alembic_version` row (i.e. brand-new, never inited)
        passes silently; `flytie init` will stamp it momentarily.
        """
        current = self.alembic_version()
        if current is None:
            return
        if current in self.known_revisions():
            return
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config()
        cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
        heads = ", ".join(sorted(ScriptDirectory.from_config(cfg).get_heads())) or "(none)"
        raise IncompatibleDatabaseError(
            f"Database is at Alembic revision {current!r}, which this build of "
            f"flytie does not recognize (this build knows revisions up to: "
            f"{heads}). You likely installed a newer flytie, ran a migration, "
            "then downgraded. To recover safely: install the newer flytie "
            "again, run `flytie export-db --out backup.json`, then on this "
            "build run `flytie init --force` followed by "
            "`flytie import-db backup.json`."
        )

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self.session_factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    @property
    def db_exists(self) -> bool:
        return Path(self.settings.db_path).exists()
