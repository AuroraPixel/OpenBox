#!/usr/bin/env python3
"""Migrate JSON file storage to PostgreSQL kv_store table.

Usage:
    DATABASE_URL=postgresql+asyncpg://... python scripts/migrate_json_to_pg.py

Idempotent: safe to run multiple times (skips existing keys).
"""
import asyncio
import json
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.log import create_logger

log = create_logger("migrate")


async def migrate():
    data_home = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    storage_dir = Path(data_home) / "openbox" / "storage"

    if not storage_dir.exists():
        print(f"No storage directory found at {storage_dir}")
        print("Nothing to migrate.")
        return

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is required")
        sys.exit(1)

    # Initialize DB
    from db.base import init_engine, get_db_session, close_engine
    init_engine(database_url)

    # Ensure kv_store table exists
    from sqlalchemy import text
    from db.base import get_engine
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

    # Scan all JSON files
    json_files = list(storage_dir.rglob("*.json"))
    print(f"Found {len(json_files)} JSON files in {storage_dir}")

    migrated = 0
    skipped = 0
    errors = 0

    for json_file in json_files:
        try:
            # Convert file path to storage key
            relative = json_file.relative_to(storage_dir)
            key = str(relative.with_suffix(""))  # Remove .json extension
            # Replace OS path separators with /
            key = key.replace(os.sep, "/")

            # Read JSON content
            with open(json_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Validate JSON
            json.loads(content)

            # Insert into DB (skip if exists)
            async with get_db_session() as session:
                result = await session.execute(
                    text("SELECT 1 FROM kv_store WHERE key = :key"),
                    {"key": key},
                )
                if result.first():
                    skipped += 1
                    continue

                await session.execute(
                    text("INSERT INTO kv_store (key, value) VALUES (:key, :value)"),
                    {"key": key, "value": content},
                )
                migrated += 1

        except Exception as e:
            print(f"  ERROR: {json_file}: {e}")
            errors += 1

    print(f"\nMigration complete:")
    print(f"  Migrated: {migrated}")
    print(f"  Skipped (already exists): {skipped}")
    print(f"  Errors: {errors}")

    if migrated > 0:
        # Rename storage directory to .bak
        backup_dir = storage_dir.parent / "storage.bak"
        if not backup_dir.exists():
            storage_dir.rename(backup_dir)
            print(f"\nOriginal data backed up to: {backup_dir}")
        else:
            print(f"\nBackup directory already exists: {backup_dir}")
            print("Original data left in place.")

    await close_engine()


if __name__ == "__main__":
    asyncio.run(migrate())
