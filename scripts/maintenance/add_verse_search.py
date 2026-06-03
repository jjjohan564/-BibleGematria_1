#!/usr/bin/env python3
"""
add_verse_search.py — adds a text_search TEXT column to the verse table and
populates it by concatenating normalised word forms (from word.text_search) in
position order.  This powers phrase search with LIKE '%phrase%'.

Run AFTER add_text_search.py (which populates word.text_search).
Safe to re-run — UPDATE is idempotent.

Supports --config for custom config.ini location (otherwise uses auto-discover + BIBLE_DB_* env).
"""

import sys
import argparse
from pathlib import Path

# Shared DB helpers (single source of truth for DB name via BIBLE_DB_NAME only)
_scripts_dir = Path(__file__).resolve().parent.parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))
from _db import connect  # type: ignore[import-not-found]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default=None, help='Path to config.ini (optional; default auto-discover + BIBLE_DB_* env)')
    args = ap.parse_args()

    conn, cur, cfg = connect(args.config)

    # ── Guard: word.text_search must exist ────────────────────────────────────
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'word'
           AND COLUMN_NAME = 'text_search'
    """, (cfg["database"],))
    if cur.fetchone()[0] == 0:
        print("ERROR: word.text_search column not found.")
        print("Run add_text_search.py first, then re-run this script.")
        sys.exit(1)

    # ── Add verse.text_search if missing ─────────────────────────────────────
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'verse'
           AND COLUMN_NAME = 'text_search'
    """, (cfg["database"],))
    if cur.fetchone()[0] == 0:
        print("Adding verse.text_search column …")
        cur.execute("ALTER TABLE verse ADD COLUMN text_search TEXT DEFAULT NULL")
        conn.commit()
        print("Column created.")
    else:
        print("Column already exists — refreshing values.")

    # ── Populate via one UPDATE … JOIN ────────────────────────────────────────
    # GROUP_CONCAT joins each verse's normalised word forms in position order,
    # producing a single space-separated string ready for LIKE phrase search.
    #
    # Iota-subscript forms (ᾳ U+1FB3, ῃ U+1FC3, ῳ U+1FF3, and bare U+0345) are
    # stripped from the stored string so that LIKE comparisons work correctly
    # under utf8mb4_unicode_ci, which treats U+0345 as a zero-weight combining
    # character and silently fails LIKE patterns containing those characters.
    # search.php phrase mode applies the same stripping to the query.
    # word.text_search is NOT changed — text-mode exact-match (=) still works.
    print("Populating verse.text_search from word.text_search …")
    cur.execute("""
        UPDATE verse v
          JOIN (
              SELECT verse_id,
                     GROUP_CONCAT(text_search ORDER BY position SEPARATOR ' ') AS ts
                FROM word
               GROUP BY verse_id
          ) agg ON agg.verse_id = v.id
           SET v.text_search = REPLACE(
                               REPLACE(
                               REPLACE(
                               REPLACE(
                                   agg.ts,
                                   'ᾳ', 'α'),
                                   'ῃ', 'η'),
                                   'ῳ', 'ω'),
                                   'ͅ', '')
    """)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM verse WHERE text_search IS NOT NULL")
    n = cur.fetchone()[0]
    print(f"Done. {n:,} verses populated.")

    # ── Spot-checks ───────────────────────────────────────────────────────────
    for ref in [('Gen', 1, 1), ('Jhn', 1, 1)]:
        cur.execute("""
            SELECT v.text_search
              FROM verse v JOIN book b ON b.id = v.book_id
             WHERE b.osis_code = %s AND v.chapter = %s AND v.verse = %s
             LIMIT 1
        """, ref)
        row = cur.fetchone()
        ts = row[0] if row else None
        print(f"  {ref[0]} {ref[1]}:{ref[2]}: {ts!r}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
