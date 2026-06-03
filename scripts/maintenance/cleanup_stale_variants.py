#!/usr/bin/env python3
"""
cleanup_stale_variants.py — one-off: identify and delete Phase 3 variants
whose canonical word, under the NEW normalize_for_diff (with Greek
koronis/psili/dasia/tonos stripped), would have been considered identical
to the variant's text — meaning the variant should never have been written.

Only touches variants with id > 12088 (Phase 3 batch). STEPBible's original
variants (id <= 12088) are left alone — their `meaning`/`spelling`
information was hand-curated and we don't second-guess it.

Run:  python cleanup_stale_variants.py --dry-run
      python cleanup_stale_variants.py
"""

import re
import argparse
import sys
import unicodedata
from pathlib import Path

# Single source of truth — import from scripts/_db (no more per-script boilerplate)
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "scripts"))
from _db import connect  # type: ignore[import-not-found]


# Mirror the FIXED normalize_for_diff from diff_editions.py / populate_verseunicode.py
_DIA_STRIP   = re.compile('[\u0300-\u0344\u0346-\u036F]')
_WHITESPACE  = re.compile(r'\s+')
_STRIP_MARKS = 'ʼʹ᾽᾿῾΄΅'
_PAREN_TAIL  = re.compile(r'\s*\([^)]*\)\s*$')

def normalize_for_diff(text):
    if not text: return ''
    t = (text.replace('Î','').replace('Ð','').replace('�',''))
    t = unicodedata.normalize('NFD', t)
    t = _DIA_STRIP.sub('', t)
    t = unicodedata.normalize('NFC', t)
    t = t.lower()
    t = ''.join(c for c in t
                if not unicodedata.category(c).startswith('P')
                and c not in _STRIP_MARKS)
    t = _WHITESPACE.sub(' ', t).strip()
    return t

def strip_greek_parens(text):
    if not text: return ''
    return _PAREN_TAIL.sub('', text).strip()


# Local connect removed — _db provides load_config / get_connection (single source of truth)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    conn, cur, cfg = connect()  # banner + live DB name verification from _db

    # Pull every Phase 3 spelling variant alongside its anchor canonical word
    print("\n[1] Scanning Phase 3 spelling variants ...")
    cur.execute("""
        SELECT v.id, v.kind, v.text_original AS variant_text,
               w.id  AS word_id, w.text_original AS canonical_text
          FROM variant v
          JOIN word w ON w.id = v.word_id
         WHERE v.id > 12088
           AND v.kind = 'spelling'
    """)
    rows = cur.fetchall()
    print(f"    {len(rows):,} Phase 3 spelling variants to evaluate")

    stale_ids = []
    samples = []
    for vid, kind, vtext, wid, can_text in rows:
        can_norm = normalize_for_diff(strip_greek_parens(can_text or ''))
        var_norm = normalize_for_diff(vtext or '')
        if can_norm == var_norm:
            stale_ids.append(int(vid))
            if len(samples) < 15:
                samples.append((vid, wid, can_text, vtext, can_norm))

    print(f"    {len(stale_ids):,} stale variants identified (canonical now matches under new normalize)")
    if samples:
        print(f"\n[2] Sample of stale variants:")
        print(f"    {'vid':>7}  {'wid':>7}  {'canonical':<25}  {'variant':<20}  {'normalized':<20}")
        for vid, wid, can, var, norm in samples:
            print(f"    {vid:>7}  {wid:>7}  {(can or ''):<25}  {(var or ''):<20}  {(norm or ''):<20}")

    if not stale_ids:
        print("\nNothing to delete. Done.")
        return

    if args.dry_run:
        print("\n[Dry run -- no writes]")
        return

    print(f"\n[3] Deleting {len(stale_ids):,} stale variants ...")
    chunk = 1000
    deleted_ve = deleted_v = 0
    for start in range(0, len(stale_ids), chunk):
        batch = stale_ids[start:start+chunk]
        marks = ','.join(['%s'] * len(batch))
        cur.execute(f"DELETE FROM variant_edition WHERE variant_id IN ({marks})", batch)
        deleted_ve += cur.rowcount
        cur.execute(f"DELETE FROM variant WHERE id IN ({marks})", batch)
        deleted_v += cur.rowcount
        conn.commit()
    print(f"    Deleted {deleted_v:,} variants and {deleted_ve:,} variant_edition rows")
    print("\nDone.")
    cur.close(); conn.close()


if __name__ == '__main__':
    main()
