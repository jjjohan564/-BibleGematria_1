#!/usr/bin/env python3
"""
fix_kjv_versification.py
========================

Build/refresh the `verse_kjv_alt` table — a small mapping from STEPBible
(NA28-style) verse references to KJV verse references for the handful of
NT verses where the two traditions disagree on numbering.

Why this exists
---------------
STEPBible's TAGNT files use NA28 versification. A few NT verses don't
line up with the KJV's older versification:

    Rev.12.18  →  KJV 13.1     (NA28 splits 13:1 into 12:18 + 13:1)
    Php.1.16   →  KJV 1.17     (the two verses are swapped)
    Php.1.17   →  KJV 1.16

When the web UI tries to display the KJV English line for one of these,
the direct lookup against `bible_kjv` returns nothing (Rev 12:18 simply
doesn't exist in KJV; Php 1:16/1:17 return the wrong verse).

STEPBible already annotates these in the source — every summary header
that needs a remap reads `# Ref [KJV X.Y]` (e.g. `# Rev.12.18 [KJV 13.1a]`).
This script scans the TAGNT files for those annotations, filters down to
the cases where the KJV ref actually differs from the NA28 ref, and
populates `verse_kjv_alt`. The web UI's KJV lookup checks this table when
the direct hit returns null.

Auto-discovery means we don't hard-code anything. If a future STEPBible
revision adds or removes anomalies, re-running picks them up. The `a`/`b`
suffixes on the KJV refs (which mark *partial* verses that don't actually
break lookup) are stripped — only chapter+verse-number differences are
stored.

Idempotent — drops and re-CREATEs the table on each run, then re-inserts.

Usage:
    python scripts/maintenance/fix_kjv_versification.py
    python scripts/maintenance/fix_kjv_versification.py --dry-run
    python scripts/maintenance/fix_kjv_versification.py --files-dir data/raw

Requires BIBLE_DB_NAME env var set (single source of truth — see _db.py).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


# Summary-header pattern: e.g.
#   "# Rev.12.18 [KJV 13.1a]"
#   "#_Php.1.16 [KJV 1.17]"
# Either leading "# " or "#_" precedes the ref. The KJV verse may carry a
# trailing 'a'/'b' suffix marking a partial verse — we keep just the digits.
HEADER_RE = re.compile(
    r"""^
        \#[ _]                            # '# ' or '#_'
        (?P<book>[1-9]?[A-Z][a-z]+)       # OSIS book code (e.g. Rev, Php, 1Co)
        \.
        (?P<na28_ch>\d+)
        \.
        (?P<na28_vs>\d+)
        \s+
        \[KJV\s+
            (?P<kjv_ch>\d+)
            \.
            (?P<kjv_vs>\d+)
            [a-z]?                        # discard 'a'/'b' partial marker
        \]
    """,
    re.VERBOSE,
)


def parse_annotations(files: List[Path]) -> List[Tuple[str, int, int, int, int]]:
    """Scan TAGNT source files for `# Ref [KJV X.Y]` headers.

    Returns a list of (book_osis, na28_chapter, na28_verse, kjv_chapter,
    kjv_verse) tuples covering every annotation found, before any filtering.
    """
    found = []
    for path in files:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = HEADER_RE.match(line)
                if not m:
                    continue
                found.append((
                    m.group("book"),
                    int(m.group("na28_ch")),
                    int(m.group("na28_vs")),
                    int(m.group("kjv_ch")),
                    int(m.group("kjv_vs")),
                ))
    # De-duplicate (multiple summary blocks may repeat the same header).
    return sorted(set(found))


def filter_mismatches(
    annotations: List[Tuple[str, int, int, int, int]],
) -> List[Tuple[str, int, int, int, int]]:
    """Keep only the rows where the NA28 ref doesn't equal the KJV ref.

    The `a`/`b` suffix cases like `# Mat.17.14 [KJV 17.14a]` parse to
    identical (ch, vs) tuples on both sides — direct KJV lookup already
    works for them, so they don't need a mapping row.
    """
    return [
        row for row in annotations
        if (row[1], row[2]) != (row[3], row[4])
    ]


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS verse_kjv_alt (
    book_id      TINYINT  UNSIGNED NOT NULL,
    na28_chapter SMALLINT UNSIGNED NOT NULL,
    na28_verse   SMALLINT UNSIGNED NOT NULL,
    kjv_chapter  SMALLINT UNSIGNED NOT NULL,
    kjv_verse    SMALLINT UNSIGNED NOT NULL,
    PRIMARY KEY (book_id, na28_chapter, na28_verse),
    CONSTRAINT fk_verse_kjv_alt_book FOREIGN KEY (book_id)
        REFERENCES book(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='STEPBible NA28 -> KJV verse-numbering remap for cross-tradition lookups';
"""


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(project_root / "scripts"))
    from _db import connect  # type: ignore[import-not-found]

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(project_root / "config.ini"),
                    help="Path to config.ini (default: project root)")
    ap.add_argument("--files-dir", default=str(project_root / "data" / "raw"),
                    help="Directory containing TAGNT source files "
                         "(default: data/raw under project root)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be inserted; touch nothing in the DB.")
    args = ap.parse_args()

    files_dir = Path(args.files_dir)
    tagnt_files = sorted(files_dir.glob("TAGNT *.txt"))
    if not tagnt_files:
        print(f"ERROR: no TAGNT source files found in {files_dir}", file=sys.stderr)
        return 1
    print(f"Scanning {len(tagnt_files)} TAGNT file(s) for [KJV X.Y] annotations...")
    for p in tagnt_files:
        print(f"  - {p.name}")

    annotations = parse_annotations(tagnt_files)
    mismatches  = filter_mismatches(annotations)

    print(f"\nFound {len(annotations)} total [KJV X.Y] annotation(s);"
          f" {len(mismatches)} have a ch/vs mismatch worth remapping.\n")

    if not mismatches:
        print("Nothing to insert. Exiting.")
        return 0

    # Print the planned rows for visibility, in book/verse order.
    for book, nc, nv, kc, kv in mismatches:
        print(f"  {book:>4} {nc:>3}:{nv:<3}  ->  KJV {kc}:{kv}")
    print()

    if args.dry_run:
        print("--dry-run: no DB changes made.")
        return 0

    conn, cur, _ = connect(args.config)

    # Resolve book OSIS -> id (we only need NT books, but fetch all).
    cur.execute("SELECT id, osis_code FROM book")
    osis_to_id: Dict[str, int] = {row[1]: int(row[0]) for row in cur.fetchall()}

    missing = sorted({b for (b, *_rest) in mismatches if b not in osis_to_id})
    if missing:
        print(f"ERROR: source annotation(s) reference unknown OSIS book code(s):"
              f" {', '.join(missing)}", file=sys.stderr)
        print("Aborting before any write.", file=sys.stderr)
        return 1

    # (Re)create the table. Drop + create = guaranteed clean state, no
    # stale rows from a prior buggy run.
    print("Recreating `verse_kjv_alt` table...")
    cur.execute("DROP TABLE IF EXISTS verse_kjv_alt")
    cur.execute(CREATE_TABLE_SQL)

    print(f"Inserting {len(mismatches)} mapping(s)...")
    cur.executemany(
        "INSERT INTO verse_kjv_alt "
        "(book_id, na28_chapter, na28_verse, kjv_chapter, kjv_verse) "
        "VALUES (%s, %s, %s, %s, %s)",
        [(osis_to_id[b], nc, nv, kc, kv) for (b, nc, nv, kc, kv) in mismatches],
    )
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM verse_kjv_alt")
    print(f"\nDone. verse_kjv_alt now has {cur.fetchone()[0]} row(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
