#!/usr/bin/env python3
"""Force cleanup ALL sandbox containers — for emergency/maintenance use.

Removes all Docker containers matching openbox-sandbox-* prefix,
and marks them as deleted in the database.

Usage:
    python scripts/cleanup_containers.py                  # cleanup Docker only
    DATABASE_URL=... python scripts/cleanup_containers.py  # cleanup Docker + DB
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def cleanup_docker():
    """Remove all sandbox containers from Docker."""
    import docker
    client = docker.from_env()
    prefix = os.environ.get("CONTAINER_NAME_PREFIX", "openbox-sandbox-")
    
    containers = client.containers.list(all=True, filters={"name": prefix})
    if not containers:
        print("No sandbox containers found.")
        return 0
    
    print(f"Found {len(containers)} sandbox container(s):")
    count = 0
    for c in containers:
        try:
            print(f"  Removing {c.name} (status={c.status})...")
            c.remove(force=True)
            count += 1
        except Exception as e:
            print(f"  Failed to remove {c.name}: {e}")
    
    print(f"Removed {count}/{len(containers)} containers.")
    return count


async def cleanup_db():
    """Mark all containers as deleted in the database."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("No DATABASE_URL set, skipping DB cleanup.")
        return
    
    from db.base import init_engine, get_db_session, close_engine
    from db.models.container import Container as ContainerORM
    from sqlalchemy import update
    from datetime import datetime, timezone
    
    init_engine(database_url)
    now = datetime.now(timezone.utc)
    
    async with get_db_session() as db:
        result = await db.execute(
            update(ContainerORM)
            .where(ContainerORM.is_deleted == False)
            .values(is_deleted=True, status="stopped", deleted_at=now, updated_at=now)
        )
        print(f"Marked {result.rowcount} container(s) as deleted in DB.")
    
    await close_engine()


def main():
    print("=== OpenBox Container Cleanup ===\n")
    
    # Docker cleanup
    cleanup_docker()
    
    # DB cleanup
    print()
    asyncio.run(cleanup_db())
    
    print("\nDone.")


if __name__ == "__main__":
    main()
