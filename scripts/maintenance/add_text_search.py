#!/usr/bin/env python3
"""
add_text_search.py — adds and populates the text_search column on the word table.

Hebrew:  strips vowel points + cantillation (U+0591-U+05C7, U+FB1E),
         keeping only consonants.
Greek:   NFD-normalise, strip combining diacritics U+0300-U+0344 and
         U+0346-U+036F (preserving iota subscript U+0345), NFC-recompose,
         then lowercase.

Run once after import_bible.py.  Safe to re-run (UPDATE is idempotent).

Supports --config for custom config.ini location (otherwise uses auto-discover + BIBLE_DB_* env).
"""

import sys
import unicodedata
import re
import argparse
from pathlib import Path

# Shared DB helpers (single source of truth for DB name via BIBLE_DB_NAME only)
_scripts_dir = Path(__file__).resolve().parent.parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))
from _db import connect  # type: ignore[import-not-found]

# ── Unicode ranges ────────────────────────────────────────────────────────────
# Hebrew: combining points/accents live in U+0591-U+05C7 plus U+FB1E (shin dot)
HEB_STRIP = re.compile(r'[֑-ׇﬞ]')

# Greek: full combining diacritic block U+0300-U+036F, MINUS U+0345 (iota subscript)
GRK_STRIP = re.compile(r'[̀-̈́͆-ͯ]')


def normalize_hebrew(text: str) -> str:
    if not text:
        return ''
    text = unicodedata.normalize('NFD', text)
    text = HEB_STRIP.sub('', text)
    # Strip STEPBible morpheme separators used inline
    text = text.replace('/', '').replace('\\', '')
    return text.strip()


def normalize_greek(text: str) -> str:
    if not text:
        return ''
    # Strip parenthetical transliteration e.g. 'Ἐν (En)' -> 'Ἐν'
    text = re.sub(r'\s*\([^)]+\)', '', text).strip()
    text = unicodedata.normalize('NFD', text)
    text = GRK_STRIP.sub('', text)
    text = unicodedata.normalize('NFC', text)
    return text.lower().strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default=None, help='Path to config.ini (optional; default auto-discover + BIBLE_DB_* env)')
    args = ap.parse_args()

    # We delegate everything (including enforcement of BIBLE_DB_NAME) to the shared helper.
    conn, cur, cfg = connect(args.config)

    # ── Add column if missing ─────────────────────────────────────────────────
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'word'
        AND COLUMN_NAME = 'text_search'
    """, (cfg["database"],))
    if cur.fetchone()[0] == 0:
        print("Adding text_search column …")
        cur.execute("ALTER TABLE word ADD COLUMN text_search VARCHAR(150) DEFAULT NULL")
        cur.execute("CREATE INDEX idx_word_text_search ON word(text_search(50))")
        conn.commit()
        print("Column + index created.")
    else:
        print("Column already exists — updating values.")

    # ── Fetch all words ───────────────────────────────────────────────────────
    print("Loading words …")
    cur.execute("SELECT id, language, text_original FROM word")
    rows = cur.fetchall()
    print(f"  {len(rows):,} words to process …")

    batch = []
    for word_id, language, text_original in rows:
        if language == 'Hebrew':
            ts = normalize_hebrew(text_original or '')
        else:
            ts = normalize_greek(text_original or '')
        batch.append((ts, word_id))

        if len(batch) >= 5000:
            cur.executemany("UPDATE word SET text_search = %s WHERE id = %s", batch)
            conn.commit()
            print(f"  … {word_id:,}", end='\r', flush=True)
            batch = []

    if batch:
        cur.executemany("UPDATE word SET text_search = %s WHERE id = %s", batch)
        conn.commit()

    print(f"\nDone. {len(rows):,} words updated.")

    # ── Spot-check ────────────────────────────────────────────────────────────
    cur.execute("""
        SELECT w.text_original, w.text_search
        FROM word w JOIN verse v ON v.id = w.verse_id
                    JOIN book  b ON b.id = v.book_id
        WHERE b.osis_code = 'Gen' AND v.chapter = 1 AND v.verse = 1
        ORDER BY w.position LIMIT 3
    """)
    print("\nGen 1:1 spot-check (original → text_search):")
    for orig, ts in cur.fetchall():
        print(f"  {orig!r:40s} → {ts!r}")

    cur.execute("""
        SELECT w.text_original, w.text_search
        FROM word w JOIN verse v ON v.id = w.verse_id
                    JOIN book  b ON b.id = v.book_id
        WHERE b.osis_code = 'Jhn' AND v.chapter = 1 AND v.verse = 1
        ORDER BY w.position LIMIT 3
    """)
    print("\nJhn 1:1 spot-check (original → text_search):")
    for orig, ts in cur.fetchall():
        print(f"  {orig!r:40s} → {ts!r}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
