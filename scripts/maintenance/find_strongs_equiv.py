#!/usr/bin/env python3
"""
find_strongs_equiv.py  — Cross-reference KJV Strong's tags with TAGNT/TAHOT codes.

For each verse that has KJV tagged text (bible_kjv table), compares the
Strong's codes embedded in the raw KJV text against the TAGNT/TAHOT
strongs_primary + word_alt_strong codes stored in the word tables.

A KJV code is "orphaned" when it appears in the KJV for a verse but
has no matching strongs_primary or alt_strong anywhere in that verse's
word rows.  When an orphaned KJV code consistently co-occurs with the
same TAGNT-only code across many verses, that pair is a candidate for
the STRONG_EQUIV synonym map in strongs-tooltip.js.

Usage:
    python find_strongs_equiv.py [--config config.ini] [--min-count N] [--min-pct P]

Options:
    --config     Path to config.ini  (default: config.ini)
    --min-count  Minimum co-occurrence count to report  (default: 3)
    --min-pct    Minimum confidence percentage to report  (default: 50)
    --show-all   Also show candidates below the thresholds (verbose)
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict, Counter
from pathlib import Path

# Shared single-source _db (scripts/_db.py). Works from any CWD.
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "scripts"))

from _db import connect  # type: ignore[import-not-found]

KJV_TAG_RE = re.compile(r'<(\d+)>')
# Regex to strip leading zeros from a stored strongs_primary code like 'H0430' or 'G0032'
_STRONGS_NORM_RE = re.compile(r'^([HG])0*(\d+[A-Za-z]?)$')


def normalize_code(prefix: str, num_str: str) -> str:
    """Strip leading zeros and add testament prefix: '01254' -> 'H1254', '0430' -> 'H430'."""
    n = num_str.lstrip('0') or '0'
    return f"{prefix}{n}"


def normalize_stored(code: str) -> str:
    """Strip leading zeros from a stored strongs_primary like 'H0430' -> 'H430', 'G0032' -> 'G32'."""
    m = _STRONGS_NORM_RE.match(code)
    if m:
        return f"{m.group(1)}{m.group(2).lstrip('0') or '0'}"
    return code


def is_stepbible_extension(code: str) -> bool:
    """H9001-H9999 are STEPBible-only function-word codes never found in KJV tagging."""
    m = _STRONGS_NORM_RE.match(code)
    if m and m.group(1) == 'H':
        try:
            n = int(m.group(2))
            return 9001 <= n <= 9999
        except ValueError:
            pass
    return False


# connect() from scripts/_db (single source of truth, no drift).


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Find potential Strong's code equivalences between KJV and TAGNT/TAHOT."
    )
    project_root = Path(__file__).resolve().parent.parent.parent
    ap.add_argument("--config", default=str(project_root / "config.ini"),
                    help="Path to config.ini (default: config.ini in project root)")
    ap.add_argument("--min-count", type=int, default=3,
                    help="Minimum co-occurrence count to report (default: 3)")
    ap.add_argument("--min-pct", type=float, default=50.0,
                    help="Minimum confidence %% to report (default: 50.0)")
    ap.add_argument("--show-all", action="store_true",
                    help="Also print low-confidence candidates (verbose)")
    args = ap.parse_args()

    conn, cur, cfg = connect(args.config)

    # ------------------------------------------------------------------
    # Step 1: load all KJV verses with their testament prefix
    # ------------------------------------------------------------------
    print("Loading KJV verses...", flush=True)
    cur.execute("""
        SELECT v.id, bk.Verse_Text, b.testament
        FROM bible_kjv bk
        JOIN book b  ON b.id = bk.Book
        JOIN verse v ON v.book_id = bk.Book
                    AND v.chapter = bk.Chapter
                    AND v.verse   = bk.Verse
        WHERE bk.Verse_Text IS NOT NULL AND bk.Verse_Text != ''
        ORDER BY v.id
    """)
    kjv_rows = cur.fetchall()
    print(f"  {len(kjv_rows):,} verses loaded.", flush=True)

    # ------------------------------------------------------------------
    # Step 2: load all TAGNT/TAHOT strongs_primary codes keyed by verse_id
    # ------------------------------------------------------------------
    print("Loading TAGNT/TAHOT primary Strong's codes...", flush=True)
    cur.execute("""
        SELECT verse_id, strongs_primary
        FROM word
        WHERE strongs_primary IS NOT NULL AND strongs_primary != ''
    """)
    tagnt_primary_by_verse: dict[int, set[str]] = defaultdict(set)
    for verse_id, sp in cur.fetchall():
        tagnt_primary_by_verse[verse_id].add(normalize_stored(sp))
    print(f"  {sum(len(v) for v in tagnt_primary_by_verse.values()):,} word codes loaded.",
          flush=True)

    # ------------------------------------------------------------------
    # Step 3: load all alt_strong codes keyed by verse_id
    # ------------------------------------------------------------------
    print("Loading alt Strong's codes...", flush=True)
    cur.execute("""
        SELECT w.verse_id, wa.alt_strong
        FROM word_alt_strong wa
        JOIN word w ON wa.word_id = w.id
        WHERE wa.alt_strong IS NOT NULL AND wa.alt_strong != ''
    """)
    tagnt_alt_by_verse: dict[int, set[str]] = defaultdict(set)
    for verse_id, alt in cur.fetchall():
        tagnt_alt_by_verse[verse_id].add(normalize_stored(alt))
    print(f"  {sum(len(v) for v in tagnt_alt_by_verse.values()):,} alt codes loaded.",
          flush=True)

    cur.close()
    conn.close()

    # ------------------------------------------------------------------
    # Step 4: co-occurrence analysis
    #
    # For every verse:
    #   kjv_codes    = all Strong's codes found in the KJV tagged text
    #   tagnt_all    = primary + alt codes from the word table
    #   orphan_kjv   = kjv_codes that are NOT in tagnt_all
    #   tagnt_only   = tagnt_primary codes NOT covered by any kjv_code
    #
    # For each orphaned KJV code X and each uncovered TAGNT primary Y
    # in the same verse, record that (X, Y) co-occurred.
    # ------------------------------------------------------------------
    print("\nAnalysing verse-level mismatches...", flush=True)

    # equiv_cooccur[kjv_code][tagnt_code] = # verses where both appear as mismatches
    equiv_cooccur: dict[str, Counter] = defaultdict(Counter)
    # total_orphan[kjv_code] = # verses where it was orphaned
    total_orphan: Counter = Counter()
    # total_kjv[kjv_code] = # verses where it appeared at all
    total_kjv: Counter = Counter()

    for verse_id, kjv_text, testament in kjv_rows:
        prefix = 'G' if testament == 'NT' else 'H'

        # Extract and normalize KJV codes
        kjv_codes: set[str] = set()
        for num in KJV_TAG_RE.findall(kjv_text):
            kjv_codes.add(normalize_code(prefix, num))
        if not kjv_codes:
            continue

        for c in kjv_codes:
            total_kjv[c] += 1

        tagnt_primary = tagnt_primary_by_verse.get(verse_id, set())
        tagnt_alt     = tagnt_alt_by_verse.get(verse_id, set())
        tagnt_all     = tagnt_primary | tagnt_alt

        orphan_kjv  = kjv_codes - tagnt_all
        # Exclude H9xxx STEPBible-only function-word codes — they are never in KJV
        tagnt_only  = {c for c in tagnt_primary - kjv_codes if not is_stepbible_extension(c)}

        if not orphan_kjv or not tagnt_only:
            continue

        for kc in orphan_kjv:
            total_orphan[kc] += 1
            for tc in tagnt_only:
                equiv_cooccur[kc][tc] += 1

    # ------------------------------------------------------------------
    # Step 5: report
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("POTENTIAL STRONG'S CODE EQUIVALENCES")
    print("=" * 70)
    print(f"Thresholds: min_count={args.min_count}, min_pct={args.min_pct:.0f}%")
    print("Confidence = (verses where X is orphaned AND Y is unmatched) / (verses where X is orphaned)")
    print()

    # Sort by code so G-codes come before H-codes, numeric within
    def sort_key(code: str):
        m = re.match(r'^([GH])(\d+)', code)
        return (m.group(1), int(m.group(2))) if m else (code, 0)

    found_any = False
    for kjv_code in sorted(equiv_cooccur.keys(), key=sort_key):
        orphan_count = total_orphan[kjv_code]
        all_count    = total_kjv[kjv_code]
        candidates   = equiv_cooccur[kjv_code].most_common(5)

        good = [
            (tc, cnt, cnt / orphan_count * 100)
            for tc, cnt in candidates
            if (args.show_all
                or (cnt >= args.min_count and cnt / orphan_count * 100 >= args.min_pct))
        ]
        if not good:
            continue

        found_any = True
        print(f"KJV {kjv_code}  (orphaned in {orphan_count}/{all_count} verses it appears in)")
        for tc, cnt, pct in good:
            marker = "" if (cnt >= args.min_count and pct >= args.min_pct) else "  [below threshold]"
            print(f"    -> TAGNT  {tc:<12s}  {cnt:4d}/{orphan_count:<4d}  ({pct:5.1f}%){marker}")
        print()

    if not found_any:
        print("No candidates found with current thresholds.")
        print("Try: --min-count 1 --min-pct 0 --show-all")


if __name__ == "__main__":
    main()
