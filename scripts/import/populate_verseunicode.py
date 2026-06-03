#!/usr/bin/env python3
"""
populate_verseunicode.py — Decode BibleWorks Greek transliteration and
write a NORMALIZED, diff-friendly Unicode form to the verseunicode column
in bible_na27 and bible_scr.

Both tables use Verse_Text (the unpointed BW stream) as the source. The
output is intentionally STRIPPED so that two editions can be compared
word-for-word without diacritic / punctuation noise:

  * decode BibleWorks -> Greek Unicode
  * NFD normalize, strip combining diacritics U+0300-U+036F
    EXCEPT U+0345 (iota subscript -- semantically a letter, not a mark)
  * NFC normalize back (re-composes pre-composed iota-subscript vowels)
  * strip all Unicode-category-P punctuation and the BW criticism
    markers U+00CE / U+00D0
  * lowercase; collapse runs of whitespace to single spaces; trim

Result: a verse like
    "En arch=| h)=n o( lo,goj, kai. o( lo,goj h)=n pro.j to.n qeo,n."
comes out (after decode + normalize) as
    "en archh|... " collapsed to lowercase Greek with iota subscript
preserved on words like archh| -> archē with U+0345 still attached.

Run:  python populate_verseunicode.py
Safe to re-run -- UPDATE is idempotent.
"""

import os
import re
import sys
import argparse
import unicodedata
from pathlib import Path

# Shared DB helpers (single source of truth for DB name via BIBLE_DB_NAME only)
_scripts_dir = Path(__file__).resolve().parent.parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))
from _db import load_config, get_connection, connect  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# BibleWorks Greek transliteration -> Unicode decoder.
# (Self-contained — these tables decode the BW transliteration that lives
#  in bible_na27.Verse_Text / bible_scr.Verse_Text after the SQL dumps are
#  loaded by run_pipeline.py.)
# ---------------------------------------------------------------------------

_BASE = {
    'a':'α','b':'β','g':'γ','d':'δ','e':'ε','z':'ζ',
    'h':'η','q':'θ','i':'ι','k':'κ','l':'λ','m':'μ',
    'n':'ν','x':'ξ','o':'ο','p':'π','r':'ρ','s':'σ',
    'j':'ς','t':'τ','u':'υ','f':'φ','c':'χ','y':'ψ','w':'ω',
    '~':'ϛ',  # stigma
}
_BASE_UC = {
    'A':'Α','B':'Β','G':'Γ','D':'Δ','E':'Ε','Z':'Ζ',
    'H':'Η','Q':'Θ','I':'Ι','K':'Κ','L':'Λ','M':'Μ',
    'N':'Ν','X':'Ξ','O':'Ο','P':'Π','R':'Ρ','S':'Σ',
    'J':'Σ','T':'Τ','U':'Υ','F':'Φ','C':'Χ','Y':'Ψ','W':'Ω',
}
_VOWELS_LC = set('aehiouw')
_VOWELS_UC = set('AEHIOUW')

_SMOOTH = '̓'
_ROUGH  = '̔'
_ACUTE  = '́'
_GRAVE  = '̀'
_CIRCUM = '͂'
_IOSUB  = 'ͅ'

_DIACRIT = {
    'v': _SMOOTH,
    '`': _ROUGH,
    ',': _ACUTE,
    '.': _GRAVE,
    '=': _CIRCUM,
    '/': _CIRCUM,
    '|': _IOSUB,
    '-': _ROUGH + _CIRCUM,
    '[': _ROUGH + _ACUTE,
    ']': _ROUGH + _GRAVE,
    ';': _SMOOTH + _ACUTE,
}


def _compose(base, dc):
    return unicodedata.normalize('NFC', base + dc) if dc else base


def decode_pointed(text):
    """Decode Verse_Text_Pointed (NA27 pointed) -> NFC Unicode Greek."""
    text = (text or '').replace('Î', '').replace('Ð', '')
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch == 'V':
            i += 1
            if i < n and text[i] in _VOWELS_UC:
                base = _BASE_UC[text[i]]; i += 1
                dc = _SMOOTH
                while i < n and text[i] in _DIACRIT:
                    dc += _DIACRIT[text[i]]; i += 1
                out.append(_compose(base, dc))
            else:
                out.append('ʼ')
            continue
        if ch in _VOWELS_UC:
            base = _BASE_UC[ch]; i += 1
            dc = ''
            while i < n and text[i] in _DIACRIT:
                dc += _DIACRIT[text[i]]; i += 1
            out.append(_compose(base, dc)); continue
        if ch in _BASE_UC:
            out.append(_BASE_UC[ch]); i += 1; continue
        if ch in _VOWELS_LC:
            base = _BASE[ch]; i += 1
            dc = ''
            while i < n and text[i] in _DIACRIT:
                dc += _DIACRIT[text[i]]; i += 1
            out.append(_compose(base, dc)); continue
        if ch in _BASE:
            out.append(_BASE[ch]); i += 1; continue
        out.append(',' if ch == '(' else ch)
        i += 1
    return ''.join(out).replace('�', '')


def decode_unpointed(text):
    """Decode Verse_Text (unpointed) -> Unicode Greek.
    Only the iota subscript marker '|' after a vowel is retained."""
    text = (text or '').replace('Î', '').replace('Ð', '')
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]; i += 1
        if ch in _VOWELS_UC:
            base = _BASE_UC[ch]
            if i < n and text[i] == '|':
                out.append(_compose(base, _IOSUB)); i += 1
            else:
                out.append(base)
            continue
        if ch in _BASE_UC:
            out.append(_BASE_UC[ch]); continue
        if ch in _VOWELS_LC:
            base = _BASE[ch]
            if i < n and text[i] == '|':
                out.append(_compose(base, _IOSUB)); i += 1
            else:
                out.append(base)
            continue
        if ch in _BASE:
            out.append(_BASE[ch]); continue
        if ch != '|':
            out.append(ch)
    return ''.join(out)


# ---------------------------------------------------------------------------
# Diff-friendly normalization.
# Applied AFTER decode_*. Pre-composed iota-subscript vowels survive
# because NFD splits them into base + U+0345, the strip below preserves
# U+0345, and NFC re-composes them.
# ---------------------------------------------------------------------------

# Combining-marks block U+0300-U+0344 and U+0346-U+036F (skipping U+0345).
_DIA_STRIP = re.compile('[\u0300-\u0344\u0346-\u036F]')
_WHITESPACE = re.compile(r'\s+')


def normalize_for_diff(text):
    """Strip diacritics (keep U+0345 iota subscript), strip punctuation,
    lowercase, collapse whitespace. Input must already be Unicode Greek."""
    if not text:
        return ''
    # Strip BW criticism markers and the U+FFFD replacement char that NA27's
    # editorial-bracket bytes turn into after a bad transcode.  decode_pointed
    # already drops U+FFFD on its last line; this catches both decode paths.
    t = (text
         .replace('Î', '')
         .replace('Ð', '')
         .replace('�', ''))
    t = unicodedata.normalize('NFD', t)
    t = _DIA_STRIP.sub('', t)
    t = unicodedata.normalize('NFC', t)
    t = t.lower()
    # Strip Unicode-P punctuation AND modifier-letter apostrophes used for
    # elision (U+02BC, U+02B9) -- these are category Lm so the P filter misses
    # them, but for diff purposes ἀλλʼ and αλλ must normalize identically.
    _APOSTROPHES = 'ʼʹ\u1FBD\u1FBF\u1FFE\u0384\u0385'   # modifier-letter apostrophes + Greek koronis/psili/dasia/tonos
    t = ''.join(c for c in t
                if not unicodedata.category(c).startswith('P')
                and c not in _APOSTROPHES)
    t = _WHITESPACE.sub(' ', t).strip()
    return t


# ---------------------------------------------------------------------------
# DB helpers (local col_exists only; connect logic moved to _db)
# ---------------------------------------------------------------------------

def col_exists(cur, db, table, column):
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s
    """, (db, table, column))
    return cur.fetchone()[0] > 0


# ---------------------------------------------------------------------------
# Per-table processing
# ---------------------------------------------------------------------------

def process_table(cur, conn, db, table, src_col, decode_fn):
    print(f"\n-- {table}  (source col: {src_col}) -------------------------")

    if not col_exists(cur, db, table, src_col):
        print(f"  ERROR: column {src_col} not found in {table}. Skipping.")
        return 0, 0
    if not col_exists(cur, db, table, 'verseunicode'):
        print(f"  ERROR: column verseunicode not found in {table}.")
        print(f"  Add it first:  ALTER TABLE {table} ADD COLUMN verseunicode VARCHAR(500);")
        return 0, 0

    cur.execute(f"SELECT Verse_Order, {src_col} FROM `{table}` ORDER BY Verse_Order")
    rows = cur.fetchall()
    print(f"  {len(rows):,} rows to process")

    batch, errors = [], 0
    for vo, raw in rows:
        try:
            uni = decode_fn(raw or '')
            uni = normalize_for_diff(uni)
        except Exception as e:
            print(f"  DECODE ERROR Verse_Order={vo}: {e}")
            uni = ''
            errors += 1
        batch.append((uni, vo))

    chunk = 1000
    for start in range(0, len(batch), chunk):
        cur.executemany(
            f"UPDATE `{table}` SET verseunicode=%s WHERE Verse_Order=%s",
            batch[start:start + chunk]
        )
        conn.commit()

    updated = len(batch) - errors
    print(f"  Updated {updated:,}  ({errors} errors)")
    return updated, errors


# ---------------------------------------------------------------------------
# Sanity checks
#
# expected_start matches the NORMALIZED output: lowercase, no diacritics,
# iota subscript preserved (alpha + U+0345 = the NFC char U+1FB3 etc.).
# None = no strict check.
# ---------------------------------------------------------------------------

CHECKS = [
    # John 1:1 -- classic opener; alpha-rho-chi + iota sub should survive on archh|
    (43,  1,  1, 'εν αρχῃ',
     'John 1:1  (en arxh-iotasub)'),
    # John 3:16
    (43,  3, 16, 'ουτως',
     'John 3:16 (outws)'),
    (40,  1,  1, None, 'Matt 1:1'),
    (45,  8, 28, None, 'Rom 8:28'),
    (66, 22, 21, None, 'Rev 22:21'),
    (40,  6, 13, None, 'Matt 6:13 (iota-sub stress)'),
]


def run_checks(cur, db):
    print("\n-- Sanity checks ------------------------------------------------------")
    print(f"  {'Table':<12} {'Ref':<28} {'verseunicode (first 60 chars)'}")
    print(f"  {'-'*12} {'-'*28} {'-'*60}")
    for table in ('bible_na27', 'bible_scr'):
        if not col_exists(cur, db, table, 'verseunicode'):
            continue
        for book, ch, vs, expected_start, label in CHECKS:
            cur.execute(f"""
                SELECT verseunicode FROM `{table}`
                 WHERE Book=%s AND Chapter=%s AND Verse=%s
            """, (book, ch, vs))
            row = cur.fetchone()
            if not row:
                uni, flag = '(not found)', ' [missing]'
            else:
                uni = (row[0] or '')
                if expected_start and not uni.startswith(expected_start):
                    flag = ' [check]'
                else:
                    flag = ''
            print(f"  {table:<12} {label:<28} {uni[:60]}{flag}")
        print()
    print("Notes:")
    print("  Both tables now write a NORMALIZED form (Verse_Text -> diff-friendly):")
    print("    * lowercase, no diacritics EXCEPT iota subscript (U+0345)")
    print("    * no punctuation, single-space-separated words")
    print("    * pre-composed iota-subscript vowels survive (NFC-recomposed)")
    print("  This output feeds Phase 2 (edition_verse_text) and Phase 3 (diff_editions).")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default=None)
    args = ap.parse_args()
    # Use the high-level helper (prints banner + does live DB name verification).
    # We still need the raw cfg for the 'db' name passed to helper functions.
    conn, cur, cfg = connect(args.config)
    db = cfg["database"]

    total_updated = 0
    total_errors  = 0

    upd, err = process_table(cur, conn, db, 'bible_na27',
                             'Verse_Text', decode_unpointed)
    total_updated += upd; total_errors += err

    upd, err = process_table(cur, conn, db, 'bible_scr',
                             'Verse_Text', decode_unpointed)
    total_updated += upd; total_errors += err

    run_checks(cur, db)

    print(f"\nDone.  Total updated: {total_updated:,}   errors: {total_errors}")
    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
