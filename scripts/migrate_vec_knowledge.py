#!/usr/bin/env python3
"""
Trinity — Migration Script: Reindex existing facts into vec_knowledge

Scans all principal directories under CHATS_DIR, and for each state.db:
  1. Reads all active facts from the ``facts`` table
  2. Embeds each fact using FastEmbed
  3. Inserts the fact + embedding into the ``vec_knowledge`` virtual table

This script is idempotent — re-running it will skip facts that already
have vec_knowledge entries.

Usage:
    cd backend && python -m scripts.migrate_vec_knowledge
    # or:
    python scripts/migrate_vec_knowledge.py

Requirements:
    - fastembed (already in requirements.txt)
    - sqlite-vec extension (optional — if not available, creates the table
      structure so it's ready when the extension is installed)
"""

import logging
import sys
import time
from pathlib import Path

# Ensure backend is on sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from config import CHATS_DIR, EMBEDDING_DIM

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("migrate_vec_knowledge")


def _discover_principal_dirs() -> list[Path]:
    """Find all principal directories with state.db."""
    root = Path(CHATS_DIR)
    if not root.exists():
        return []
    return [
        child
        for child in root.iterdir()
        if child.is_dir() and (child / "state.db").exists()
    ]


def _ensure_vec_table(conn):
    """Create the vec_knowledge table if it doesn't exist."""
    try:
        import sqlite_vec  # noqa: F811
        conn.enable_load_extension(True)
        conn.load_extension(sqlite_vec.loadable_path())
        conn.enable_load_extension(False)

        conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_knowledge USING vec0(
                embedding float[{EMBEDDING_DIM}],
                +item_id integer,
                +item_type text,
                +principal_id text,
                +category text
            )
        """)
        conn.commit()
        return True
    except ImportError:
        logger.warning("sqlite-vec not available — skipping vec table creation")
        return False
    except Exception as e:
        logger.warning("Failed to create vec_knowledge table: %s", e)
        return False


def _get_existing_vec_ids(conn, principal_id: str) -> set[int]:
    """Get fact IDs already in vec_knowledge."""
    try:
        rows = conn.execute(
            "SELECT item_id FROM vec_knowledge WHERE principal_id = ? AND item_type = 'fact'",
            (principal_id,),
        ).fetchall()
        return {int(r[0]) for r in rows}
    except Exception:
        return set()


def _migrate_principal(principal_dir: Path) -> tuple[int, int, int]:
    """Migrate one principal's facts to vec_knowledge.

    Returns (total_facts, migrated, skipped).
    """
    import sqlite3
    import numpy as np
    from services.embeddings import embed_text

    principal_id = principal_dir.name
    db_path = principal_dir / "state.db"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    if not _ensure_vec_table(conn):
        conn.close()
        return 0, 0, 0

    # Get existing vec entries to skip
    existing_ids = _get_existing_vec_ids(conn, principal_id)

    # Load all active facts
    try:
        rows = conn.execute(
            "SELECT fact_id, text, category, importance FROM facts WHERE deleted_at IS NULL"
        ).fetchall()
    except Exception:
        conn.close()
        return 0, 0, 0

    total = len(rows)
    migrated = 0
    skipped = 0

    for row in rows:
        fact_id = int(row["fact_id"])
        if fact_id in existing_ids:
            skipped += 1
            continue

        text = row["text"]
        category = row["category"] or "general"

        # Embed the fact
        embedding = embed_text(text)
        if embedding is None:
            logger.debug("Failed to embed fact %d: %s", fact_id, text[:60])
            skipped += 1
            continue

        # Insert into vec_knowledge
        blob = np.array(embedding, dtype=np.float32).tobytes()
        try:
            conn.execute(
                """
                INSERT INTO vec_knowledge (embedding, item_id, item_type, principal_id, category)
                VALUES (?, ?, 'fact', ?, ?)
                """,
                (blob, fact_id, principal_id, category),
            )
            migrated += 1
        except Exception as e:
            logger.debug("vec insert failed for fact %d: %s", fact_id, e)
            skipped += 1

    conn.commit()
    conn.close()
    return total, migrated, skipped


def main():
    logger.info("=== Trinity vec_knowledge Migration ===")
    start = time.time()

    dirs = _discover_principal_dirs()
    if not dirs:
        logger.info("No principal directories found in %s", CHATS_DIR)
        return

    logger.info("Found %d principals to migrate", len(dirs))

    total_principals = 0
    total_facts = 0
    total_migrated = 0
    total_skipped = 0

    for principal_dir in dirs:
        principal_id = principal_dir.name
        try:
            facts, migrated, skipped = _migrate_principal(principal_dir)
            total_principals += 1
            total_facts += facts
            total_migrated += migrated
            total_skipped += skipped

            if migrated > 0:
                logger.info(
                    "✅ %s: %d facts, %d migrated, %d skipped",
                    principal_id[:16],
                    facts,
                    migrated,
                    skipped,
                )
        except Exception as e:
            logger.error("❌ %s: migration failed: %s", principal_id[:16], e)

    elapsed = time.time() - start
    logger.info(
        "=== Migration complete: %d principals, %d facts, %d migrated, %d skipped (%.1fs) ===",
        total_principals,
        total_facts,
        total_migrated,
        total_skipped,
        elapsed,
    )


if __name__ == "__main__":
    main()
