import sqlite3
import traceback
from pathlib import Path

from backend.db import schemas

_AUTOMATION_ACTIONS_HEARTBEAT_COLUMN = "last_heartbeat_at"


class SqliteDBHandler:
    """Base class for SQLite database handlers."""

    def __init__(self, db_path: Path) -> None:
        """Connection handler for each user's db file

        :param db_path: points to app_user_db.sqlite for one app user.
        """
        self.db_path = db_path
        self.conn: sqlite3.Connection | None = None
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Initialize the database with necessary tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for table_sql in schemas.schema_collection.values():
                cursor.execute(table_sql)
            self._ensure_automation_action_columns(cursor)
            conn.commit()

    def _ensure_automation_action_columns(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute("PRAGMA table_info(automation_actions)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        if _AUTOMATION_ACTIONS_HEARTBEAT_COLUMN not in existing_columns:
            cursor.execute(
                "ALTER TABLE automation_actions ADD COLUMN last_heartbeat_at TEXT"
            )

    def __enter__(self):
        # Keep one connection per handler (and handler is thread-local in db_service).
        if self.conn is None:
            self.conn = sqlite3.connect(
                self.db_path,
                timeout=10.0,  # Wait up to 10 seconds if database is locked
            )
            self.conn.row_factory = sqlite3.Row
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        _is_successful_close = True
        if self.conn:
            if exc_type:
                print(
                    f"Exception occurred: {exc_type}, {exc_val}. Rolling back transaction."
                )
                traceback.print_exception(exc_type, exc_val, exc_tb)
                # Rollback on error
                self.conn.rollback()
                _is_successful_close = False
            # else:
                # Commit on success
            # self.conn.commit()
            return _is_successful_close
        return False  # Don't suppress exceptions

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None
