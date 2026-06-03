#!/usr/bin/env python3
"""
compute_gematria.py
-------------------
Computes gematria values for every word and verse in the target database
(controlled exclusively by BIBLE_DB_NAME env var via scripts/_db)
and populates the gematria and gematria_verse tables.

Values computed
  standard       Hebrew: Mispar Hechrachi (Alef=1 … Tav=400, finals = base value)
                 Greek:  Isopsephy       (Alpha=1 … Omega=800)
  standard_sofit Hebrew: same but final forms use extended values (Kaf-sofit=500 … Tsadi-sofit=900)
                 Greek:  identical to standard (no sofit distinction)
  ordinal        Hebrew: Alef=1 … Tav=22 (finals = same ordinal as base)
                 Greek:  Alpha=1 … Omega=24
  reduced        Digital root of `standard` (sum digits repeatedly until single digit)

Run AFTER schema.sql + gematria_schema.sql have been applied and import_bible.py
has loaded all words.

Usage:
    python compute_gematria.py [--config config.ini]
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

# Shared DB (single source of truth). No more hacky import from import_bible.
_scripts_dir = Path(__file__).resolve().parent.parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))
from _db import load_config, get_connection, verify_db_name  # type: ignore[import-not-found]

try:
    import pymysql as _driver
    _PARAM = '%s'
except ImportError:
    try:
        import mariadb as _driver
        _PARAM = '?'
    except ImportError:
        print("ERROR: install pymysql or mariadb connector:  pip install pymysql")
        sys.exit(1)

# ---------------------------------------------------------------------------
# Letter-value maps
# ---------------------------------------------------------------------------

# Hebrew — values applied to bare consonants (after stripping vowel points,
# cantillation marks, and morpheme separators / \).

HEB_STANDARD = {
    'א': 1,   'ב': 2,   'ג': 3,   'ד': 4,   'ה': 5,   'ו': 6,   'ז': 7,
    'ח': 8,   'ט': 9,   'י': 10,  'כ': 20,  'ל': 30,  'מ': 40,  'נ': 50,
    'ס': 60,  'ע': 70,  'פ': 80,  'צ': 90,  'ק': 100, 'ר': 200, 'ש': 300,
    'ת': 400,
    # final forms — same value as base letter in standard
    'ך': 20,  'ם': 40,  'ן': 50,  'ף': 80,  'ץ': 90,
}

HEB_STANDARD_SOFIT = {
    **HEB_STANDARD,
    # override final forms with extended (sofit) values
    'ך': 500, 'ם': 600, 'ן': 700, 'ף': 800, 'ץ': 900,
}

HEB_ORDINAL = {
    'א': 1,   'ב': 2,   'ג': 3,   'ד': 4,   'ה': 5,   'ו': 6,   'ז': 7,
    'ח': 8,   'ט': 9,   'י': 10,  'כ': 11,  'ל': 12,  'מ': 13,  'נ': 14,
    'ס': 15,  'ע': 16,  'פ': 17,  'צ': 18,  'ק': 19,  'ר': 20,  'ש': 21,
    'ת': 22,
    # final forms — same ordinal position as their base letter
    'ך': 11,  'ם': 13,  'ן': 14,  'ף': 17,  'ץ': 18,
}

# Greek — values applied to bare base letters (after stripping diacritics and
# parenthetical romanisation).  Final sigma (ς) = sigma (σ).

GRK_STANDARD = {
    'α': 1,   'β': 2,   'γ': 3,   'δ': 4,   'ε': 5,   'ζ': 7,
    'η': 8,   'θ': 9,   'ι': 10,  'κ': 20,  'λ': 30,  'μ': 40,
    'ν': 50,  'ξ': 60,  'ο': 70,  'π': 80,  'ρ': 100, 'σ': 200,
    'ς': 200, 'τ': 300, 'υ': 400, 'φ': 500, 'χ': 600, 'ψ': 700,
    'ω': 800,
}

GRK_ORDINAL = {
    'α': 1,   'β': 2,   'γ': 3,   'δ': 4,   'ε': 5,   'ζ': 6,
    'η': 7,   'θ': 8,   'ι': 9,   'κ': 10,  'λ': 11,  'μ': 12,
    'ν': 13,  'ξ': 14,  'ο': 15,  'π': 16,  'ρ': 17,  'σ': 18,
    'ς': 18,  'τ': 19,  'υ': 20,  'φ': 21,  'χ': 22,  'ψ': 23,
    'ω': 24,
}

# ---------------------------------------------------------------------------
# Text-cleaning helpers
# ---------------------------------------------------------------------------

_HEB_NIQQUD      = re.compile(r'[֑-ׇ]')       # vowel points + cantillation
_SECTION_MARKERS = re.compile(r'\\[פס]')       # Petuhah \פ and Setumah \ס paragraph markers
_SEPARATORS      = re.compile(r'[/\\]')         # STEPBible morpheme separators
_GRK_PARENS      = re.compile(r'\s*\([^)]+\)')  # parenthetical romanisation
# Iota subscript (U+0345, COMBINING GREEK YPOGEGRAMMENI) appears under ᾳ ῃ ῳ.
# It was historically a full iota and counts as iota (value 10) in isopsephy.
# We must convert it to plain iota BEFORE stripping other combining marks.
_IOTA_SUBSCRIPT  = 'ͅ'


def clean_hebrew(text: str) -> str:
    """Strip section markers, vowel points, cantillation marks, and morpheme
    separators, leaving only the bare Hebrew consonants."""
    text = _SECTION_MARKERS.sub('', text)   # must come before _SEPARATORS strip
    text = _HEB_NIQQUD.sub('', text)
    text = _SEPARATORS.sub('', text)
    return text


def clean_greek(text: str) -> str:
    """Strip parenthetical romanisation and diacritics; return lowercase
    base Greek letters only.  Iota subscript is converted to plain iota
    before diacritics are removed so it retains its gematria value."""
    text = _GRK_PARENS.sub('', text)
    # NFD decomposition separates base letters from combining diacritics
    text = unicodedata.normalize('NFD', text)
    # Preserve iota subscript as a countable iota before stripping all Mn chars
    text = text.replace(_IOTA_SUBSCRIPT, 'ι')
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    return text.lower()


# ---------------------------------------------------------------------------
# Calculation helpers
# ---------------------------------------------------------------------------

def digital_root(n: int) -> int:
    """Return the digital root (iterated digit sum) of n.  0 → 0, else 1-9."""
    if n == 0:
        return 0
    return 1 + (n - 1) % 9


def score(text: str, value_map: dict) -> int:
    return sum(value_map.get(ch, 0) for ch in text)


def word_gematria(language: str, text_original: str | None) -> dict:
    """Return all four gematria values for a single word."""
    if not text_original:
        return {'standard': 0, 'standard_sofit': 0, 'ordinal': 0, 'reduced': 0}

    if language == 'Hebrew':
        cleaned = clean_hebrew(text_original)
        std   = score(cleaned, HEB_STANDARD)
        soft  = score(cleaned, HEB_STANDARD_SOFIT)
        ordin = score(cleaned, HEB_ORDINAL)
    else:   # Greek
        cleaned = clean_greek(text_original)
        std   = score(cleaned, GRK_STANDARD)
        soft  = std   # Greek has no sofit distinction
        ordin = score(cleaned, GRK_ORDINAL)

    return {
        'standard':       std,
        'standard_sofit': soft,
        'ordinal':        ordin,
        'reduced':        digital_root(std),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description='Populate gematria tables.')
    project_root = Path(__file__).resolve().parent.parent.parent
    ap.add_argument('--config', default=str(project_root / 'config.ini'), help='Path to config.ini')
    args = ap.parse_args()

    cfg = load_config(Path(args.config))

    conn, driver = get_connection(cfg)
    cur = conn.cursor()
    print(f"  connected via '{driver}'.")

    # Live verification (single source of truth)
    print()
    verify_db_name(cur, cfg["database"])
    print()

    # ------------------------------------------------------------------
    # Fetch every word with its language
    # ------------------------------------------------------------------
    print('Fetching words …')
    cur.execute("""
        SELECT w.id, w.language, w.text_original, w.verse_id
        FROM   word w
        ORDER  BY w.id
    """)
    rows = cur.fetchall()
    print(f'  {len(rows):,} words loaded.')

    # ------------------------------------------------------------------
    # Compute per-word values; accumulate per-verse totals in one pass
    # ------------------------------------------------------------------
    word_rows  = []                 # list of 5-tuples for gematria INSERT
    verse_sums = {}                 # verse_id -> [std, soft, ord]

    for word_id, language, text_original, verse_id in rows:
        g = word_gematria(language, text_original)
        word_rows.append((
            word_id,
            g['standard'],
            g['standard_sofit'],
            g['ordinal'],
            g['reduced'],
        ))
        if verse_id not in verse_sums:
            verse_sums[verse_id] = [0, 0, 0]
        verse_sums[verse_id][0] += g['standard']
        verse_sums[verse_id][1] += g['standard_sofit']
        verse_sums[verse_id][2] += g['ordinal']

    verse_rows = [
        (vid, s[0], s[1], s[2], digital_root(s[0]))
        for vid, s in verse_sums.items()
    ]

    # ------------------------------------------------------------------
    # Write to database
    # ------------------------------------------------------------------
    print('Clearing existing gematria data …')
    cur.execute('DELETE FROM gematria_verse')
    cur.execute('DELETE FROM gematria_word')
    conn.commit()

    print(f'Inserting {len(word_rows):,} word rows …')
    cur.executemany(
        f"""INSERT INTO gematria_word
               (word_id, standard, standard_sofit, ordinal, reduced)
            VALUES ({_PARAM},{_PARAM},{_PARAM},{_PARAM},{_PARAM})""",
        word_rows,
    )
    conn.commit()

    print(f'Inserting {len(verse_rows):,} verse rows …')
    cur.executemany(
        f"""INSERT INTO gematria_verse
               (verse_id, standard, standard_sofit, ordinal, reduced)
            VALUES ({_PARAM},{_PARAM},{_PARAM},{_PARAM},{_PARAM})""",
        verse_rows,
    )
    conn.commit()

    cur.close()
    conn.close()
    print('Done.')


if __name__ == '__main__':
    main()
