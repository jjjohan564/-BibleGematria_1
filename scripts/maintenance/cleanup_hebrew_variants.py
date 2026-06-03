#!/usr/bin/env python3
"""
cleanup_hebrew_variants.py — one-off cleanup of Hebrew OT variant rows.

Two problems to fix:

  (a) Many Hebrew variants only differ from their canonical word in vowel
      points or cantillation marks. Visually invisible in the interlinear,
      they clutter the variant indicator bars without conveying anything.
      The Ten Commandments (Exodus 20) is the textbook concentration --
      both ta'am elyon and ta'am tachton cantillation traditions are
      recorded.

  (b) STEPBible encodes manuscript-family annotations as a literal prefix
      embedded in variant.text_original (e.g. 'P= אָֽנֹכִי֙' for the
      Palestinian-tradition reading). When two families differ they get
      concatenated into one string ('B= ...   P= ...'). The prefix is
      redundant with variant_edition tagging and pollutes the UI.

What this script does:
  For every Hebrew variant (word.book in OT testament):
    1. Parse text_original into a list of readings (split on [A-Z]= prefix).
    2. For each reading, compute consonants_only (strip diacritics U+0591-
       U+05C7, morpheme separators / and \\, and the sof-passuq ׃).
    3. Compare each reading's consonants to the canonical word's consonants.
    4. Drop readings that match canonical (= pure vocalization noise).
    5. If nothing survives -> DELETE the variant (and its variant_edition).
    6. If readings survive -> UPDATE variant.text_original to the cleaned,
       prefix-free string (multiple readings joined by ' / ').

Idempotent: a second run finds nothing to change because the prefixes are
already gone. Dry-run first; commit only after you've eyeballed samples.

Run:  python cleanup_hebrew_variants.py --dry-run
      python cleanup_hebrew_variants.py
"""

import re
import argparse
import sys
from pathlib import Path
from collections import Counter

# Single source of truth for DB name/config (via scripts/_db)
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "scripts"))
from _db import connect  # type: ignore[import-not-found]


# Hebrew niqqud + cantillation marks + dagesh + rafe + meteg + sof passuq
# Stripping the full U+0591-U+05C7 range leaves only the consonantal
# letters (U+05D0-U+05EA) plus any non-Hebrew chars.
_HEB_MARKS = re.compile('[\u0591-\u05C7]')
_SEPARATORS = re.compile(r'[/\\]')   # STEPBible morpheme separators

def consonants_only(text):
    """Reduce a Hebrew string to its bare consonants for comparison."""
    if not text:
        return ''
    t = _HEB_MARKS.sub('', text)
    t = _SEPARATORS.sub('', t)
    return t.strip()


def parse_readings(text):
    """Parse 'B= xxx   P= yyy' or 'P= xxx' into ['xxx', 'yyy'] or ['xxx'].
    A string with no [A-Z]= prefix is returned as a single-element list."""
    if not text:
        return []
    # Split on optional whitespace + uppercase letter + '='
    parts = re.split(r'\s*[A-Z]=\s*', text)
    return [p.strip() for p in parts if p.strip()]


# Local connect removed — using _db for guaranteed single source of truth on database name.


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    conn, cur, cfg = connect()  # banner + live DB name verification from _db

    print("\n[1] Scanning Hebrew variants ...")
    cur.execute("""
        SELECT v.id, v.text_original AS variant_text,
               w.id AS word_id, w.text_original AS canonical_text
          FROM variant v
          JOIN word w ON w.id = v.word_id
          JOIN book b ON b.id = w.book_id
         WHERE b.testament = 'OT'
    """)
    rows = cur.fetchall()
    print(f"    {len(rows):,} Hebrew variants to evaluate")

    to_delete = []     # variant_ids
    to_update = []     # (variant_id, new_text)
    has_prefix = 0
    sample_delete = []
    sample_update = []

    for vid, vtext, wid, can_text in rows:
        readings = parse_readings(vtext or '')
        had_prefix = bool(re.search(r'^[A-Z]=', (vtext or '').lstrip())
                          or re.search(r'\s[A-Z]=', vtext or ''))
        if had_prefix:
            has_prefix += 1

        can_cons = consonants_only(can_text or '')
        # Keep only readings whose consonants differ from canonical
        substantive = [r for r in readings if consonants_only(r) != can_cons]

        if not substantive:
            to_delete.append(int(vid))
            if len(sample_delete) < 15:
                sample_delete.append((vid, can_text, vtext))
            continue

        # Rebuild text_original without the [A-Z]= prefixes.
        new_text = ' / '.join(substantive) if len(substantive) > 1 else substantive[0]
        if (new_text or '') != (vtext or ''):
            to_update.append((int(vid), new_text))
            if len(sample_update) < 15:
                sample_update.append((vid, vtext, new_text))

    print(f"    variants with [A-Z]= prefix annotation: {has_prefix:,}")
    print(f"    variants to DELETE (pure vocalization noise): {len(to_delete):,}")
    print(f"    variants to UPDATE (strip prefix, keep substantive readings): {len(to_update):,}")
    print(f"    variants unchanged: {len(rows) - len(to_delete) - len(to_update):,}")

    if sample_delete:
        print(f"\n[2] Sample of variants to DELETE:")
        print(f"    {'vid':>7}  {'canonical':<22}  variant text")
        for vid, can, var in sample_delete:
            print(f"    {vid:>7}  {(can or '')[:22]:<22}  {var}")

    if sample_update:
        print(f"\n[3] Sample of variants to UPDATE:")
        print(f"    {'vid':>7}  before -> after")
        for vid, before, after in sample_update:
            print(f"    {vid:>7}  {before!r}")
            print(f"            -> {after!r}")

    if args.dry_run:
        print("\n[Dry run -- no writes]")
        return

    if to_delete:
        print(f"\n[4] Deleting {len(to_delete):,} variants ...")
        chunk = 1000
        del_v = del_ve = 0
        for start in range(0, len(to_delete), chunk):
            batch = to_delete[start:start+chunk]
            marks = ','.join(['%s'] * len(batch))
            cur.execute(f"DELETE FROM variant_edition WHERE variant_id IN ({marks})", batch)
            del_ve += cur.rowcount
            cur.execute(f"DELETE FROM variant            WHERE id          IN ({marks})", batch)
            del_v += cur.rowcount
            conn.commit()
        print(f"    Deleted {del_v:,} variants and {del_ve:,} variant_edition rows")

    if to_update:
        print(f"\n[5] Updating {len(to_update):,} variants ...")
        upd = 0
        for vid, new_text in to_update:
            cur.execute("UPDATE variant SET text_original = %s WHERE id = %s",
                        (new_text, vid))
            upd += cur.rowcount
        conn.commit()
        print(f"    Updated {upd:,} variants")

    print("\nDone.")
    cur.close(); conn.close()


if __name__ == '__main__':
    main()
