#!/usr/bin/env python3
"""
fix_strongs_primary.py — Recompute word.strongs_primary from word.strongs.

The original import used a simple left-to-right regex that grabbed the first
H/G code in the string, which is wrong when a {}-bracketed root code appears
later (e.g. H9003/{H7225G} → should be H7225, not H9003).  It also kept
leading zeros (H0430 instead of H430).

The correct logic mirrors strongs_full_code() in web/helpers.php:
  1. Prefer the {}-bracketed code (STEPBible root-word marker)
  2. Fall back to the first H/G code
  3. Strip leading zeros from the number
  4. Strip letter suffix (A, G, etc.) from the number part — keep only digits

Run from the project root:
    python fix_strongs_primary.py
"""

import re
import sys
from pathlib import Path

# ── regex patterns (mirror strongs_full_code in helpers.php) ─────────────────
# Bracketed root word: {H0430G}, {H1254A}, {G3056}
BRACKETED = re.compile(r'\{([HG])(\d{3,5})[A-Za-z]?\}')
# Any code (fallback): H0430G, G3056, H7225
ANY_CODE  = re.compile(r'([HG])(\d{3,5})[A-Za-z]?')


def compute_primary(raw: str) -> str:
    """Return the corrected strongs_primary value for a raw strongs string."""
    if not raw:
        return ''
    m = BRACKETED.search(raw)
    if not m:
        m = ANY_CODE.search(raw)
    if not m:
        return ''
    # Keep leading zeros — strongs_primary stores padded form (H0430, not H430).
    # strongs_full_code() in helpers.php strips zeros when looking up the dictionary.
    return m.group(1) + m.group(2)


def main():
    # Project root is two levels up
    project_root = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(project_root / "scripts"))
    from _db import connect  # type: ignore[import-not-found]

    conn, cur, cfg = connect(project_root / 'config.ini')

    print('Fetching rows …', flush=True)
    cur.execute(
        'SELECT id, strongs FROM word '
        'WHERE strongs IS NOT NULL AND strongs != ""'
    )
    rows = cur.fetchall()
    total = len(rows)
    print(f'  {total:,} rows fetched', flush=True)

    # Compute corrected values
    updates = []
    for (wid, strongs) in rows:
        updates.append((compute_primary(strongs), wid))

    # Batch UPDATE in chunks of 10 000
    CHUNK = 10_000
    done  = 0
    print('Updating …', flush=True)
    for i in range(0, total, CHUNK):
        batch = updates[i : i + CHUNK]
        cur.executemany(
            'UPDATE word SET strongs_primary = %s WHERE id = %s',
            batch
        )
        conn.commit()
        done += len(batch)
        print(f'  {done:,} / {total:,}', flush=True)

    cur.close()
    conn.close()
    print('Done.', flush=True)


if __name__ == '__main__':
    main()
