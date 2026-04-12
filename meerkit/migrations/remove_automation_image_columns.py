#!/usr/bin/env python
"""
Migration script to remove image-related columns from automation_action_items table.

These columns were previously added to store image snapshots directly on action items,
but the architecture has been updated to use the image_cache table instead.

This script safely removes:
- full_name
- profile_pic_id
- profile_pic_url

The script checks if columns exist before attempting to remove them, so it's safe
to run multiple times and on fresh databases.
"""
import sqlite3
import sys
from pathlib import Path


def get_db_path() -> Path:
    """Get database path from environment or default."""
    db_path = Path.home() / ".meerkit" / "meerkit.db"
    return db_path


def migrate(db_path: Path) -> None:
    """Remove image columns from automation_action_items table."""
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Check which columns exist
    cursor.execute("PRAGMA table_info(automation_action_items)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    columns_to_remove = ["full_name", "profile_pic_id", "profile_pic_url"]
    columns_that_exist = [col for col in columns_to_remove if col in existing_columns]

    if not columns_that_exist:
        print("No image columns found to remove. Migration skipped.")
        conn.close()
        return

    print(f"Removing columns: {', '.join(columns_that_exist)}")

    # SQLite doesn't support DROP COLUMN in all versions, so we rename and recreate
    # Get current schema
    cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='automation_action_items'"
    )
    original_schema_row = cursor.fetchone()
    if not original_schema_row:
        print("automation_action_items table not found!")
        conn.close()
        return

    original_schema = original_schema_row[0]

    # Get all data
    cursor.execute("SELECT * FROM automation_action_items")
    all_rows = cursor.fetchall()

    # Get column names
    cursor.execute("PRAGMA table_info(automation_action_items)")
    columns_info = cursor.fetchall()
    all_column_names = [col_info[1] for col_info in columns_info]

    # Create new schema without the image columns
    columns_to_keep = [col for col in all_column_names if col not in columns_that_exist]

    new_schema = f"""
CREATE TABLE automation_action_items (
    item_id TEXT PRIMARY KEY,
    action_id TEXT NOT NULL,
    app_user_id TEXT NOT NULL,
    reference_profile_id TEXT NOT NULL,
    raw_input TEXT NOT NULL,
    normalized_username TEXT,
    normalized_user_id TEXT,
    display_username TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    exclusion_reason TEXT,
    result_json TEXT,
    executed_at TEXT,
    error TEXT,
    create_date TEXT NOT NULL,
    update_date TEXT NOT NULL
)"""

    try:
        # Disable foreign key checks temporarily
        cursor.execute("PRAGMA foreign_keys = OFF")

        # Rename old table
        cursor.execute("ALTER TABLE automation_action_items RENAME TO automation_action_items_old")

        # Create new table without image columns
        cursor.execute(new_schema)

        # Copy data from old table, selecting only the columns we want to keep
        columns_to_keep_str = ", ".join(columns_to_keep)
        cursor.execute(
            f"INSERT INTO automation_action_items ({columns_to_keep_str}) "
            f"SELECT {columns_to_keep_str} FROM automation_action_items_old"
        )

        # Drop old table
        cursor.execute("DROP TABLE automation_action_items_old")

        # Re-enable foreign key checks
        cursor.execute("PRAGMA foreign_keys = ON")

        conn.commit()
        print(f"✓ Successfully removed image columns from automation_action_items table")
        print(f"  Removed columns: {', '.join(columns_that_exist)}")
        print(f"  Rows preserved: {len(all_rows)}")

    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        conn.close()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = get_db_path()
    print(f"Running migration on: {db_path}")
    migrate(db_path)
    print("Migration complete!")
