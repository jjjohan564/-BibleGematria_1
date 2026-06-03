#!/usr/bin/env python3
"""
import_bible.py  (v2 — fully normalized variants/editions)
=========================================================

Parses the six STEPBible.org tagged Bible files (TAGNT Greek NT + TAHOT
Hebrew OT) and bulk-loads them into a MariaDB / MySQL database using
the v2 schema (schema.sql).

What the v2 loader produces:
    book                – 66 canonical books
    edition             – 9 Greek + 15 Hebrew named sources
    verse               – assembled per-verse rows + 'has significant variant' flag
    verse_summary       – verbatim '#_Translation' / '#_Word=Grammar' /
                          '#_Significant variant' blocks from source
    word                – canonical printed form of each word
    word_edition        – editions containing the base form of each word
    word_alt_strong     – alt Strong's tagging cross-refs
    word_morpheme       – Hebrew prefix/root/suffix breakdown
    word_link           – grammatical conjoin arrows between words
    variant             – textual variant readings
    variant_edition     – editions supporting each variant

Usage:
    pip install mariadb        # or:  pip install pymysql
    cp config.ini.sample config.ini   # then edit (database name has no default fallback)

    # Set target database (single source of truth - no editing config files)
    $env:BIBLE_DB_NAME = "stepbible"

    # Easiest / out-of-the-box way to create a completely fresh DB
    # (core tables + gematria tables). If the DB already has data it will
    # warn: "Selected database has data. It will be erased and replaced.
    # Continue? (Y/N)" before doing so. No extra parameters required.
    python import_bible.py

    # Or create tables manually first (then let the loader populate):
    mysql -u root -p YOUR_DB < sql/schema/schema.sql
    python import_bible.py

    # Advanced / debugging options (not needed for normal "create the stepbible DB" use):
    #   --dry-run, --limit-verses N, --truncate, --files-dir PATH

The database name has a strict single source of truth:
it MUST come from the BIBLE_DB_NAME environment variable
(BIBLE_DATABASE is accepted as an alias too).
It is never read from config.ini. After connecting, the script runs
"SELECT DATABASE()" to prove what the server is actually using.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

# ---------------------------------------------------------------------
# Use the shared single-source-of-truth DB helpers (scripts/_db.py).
# We insert scripts/ into sys.path so "import _db" works whether the
# script is run from the project root or directly from scripts/import/.
# ---------------------------------------------------------------------
_scripts_dir = Path(__file__).resolve().parent.parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))
from _db import load_config, get_connection, verify_db_name  # type: ignore[import-not-found]


# =====================================================================
# Static reference data
# =====================================================================

BOOKS: List[Tuple[int, str, str, str, str]] = [
    # (id, osis_code, name, testament, language)
    ( 1, "Gen",  "Genesis",         "OT", "Hebrew"),
    ( 2, "Exo",  "Exodus",          "OT", "Hebrew"),
    ( 3, "Lev",  "Leviticus",       "OT", "Hebrew"),
    ( 4, "Num",  "Numbers",         "OT", "Hebrew"),
    ( 5, "Deu",  "Deuteronomy",     "OT", "Hebrew"),
    ( 6, "Jos",  "Joshua",          "OT", "Hebrew"),
    ( 7, "Jdg",  "Judges",          "OT", "Hebrew"),
    ( 8, "Rut",  "Ruth",            "OT", "Hebrew"),
    ( 9, "1Sa",  "1 Samuel",        "OT", "Hebrew"),
    (10, "2Sa",  "2 Samuel",        "OT", "Hebrew"),
    (11, "1Ki",  "1 Kings",         "OT", "Hebrew"),
    (12, "2Ki",  "2 Kings",         "OT", "Hebrew"),
    (13, "1Ch",  "1 Chronicles",    "OT", "Hebrew"),
    (14, "2Ch",  "2 Chronicles",    "OT", "Hebrew"),
    (15, "Ezr",  "Ezra",            "OT", "Hebrew"),
    (16, "Neh",  "Nehemiah",        "OT", "Hebrew"),
    (17, "Est",  "Esther",          "OT", "Hebrew"),
    (18, "Job",  "Job",             "OT", "Hebrew"),
    (19, "Psa",  "Psalms",          "OT", "Hebrew"),
    (20, "Pro",  "Proverbs",        "OT", "Hebrew"),
    (21, "Ecc",  "Ecclesiastes",    "OT", "Hebrew"),
    (22, "Sng",  "Song of Solomon", "OT", "Hebrew"),
    (23, "Isa",  "Isaiah",          "OT", "Hebrew"),
    (24, "Jer",  "Jeremiah",        "OT", "Hebrew"),
    (25, "Lam",  "Lamentations",    "OT", "Hebrew"),
    (26, "Ezk",  "Ezekiel",         "OT", "Hebrew"),
    (27, "Dan",  "Daniel",          "OT", "Hebrew"),
    (28, "Hos",  "Hosea",           "OT", "Hebrew"),
    (29, "Jol",  "Joel",            "OT", "Hebrew"),
    (30, "Amo",  "Amos",            "OT", "Hebrew"),
    (31, "Oba",  "Obadiah",         "OT", "Hebrew"),
    (32, "Jon",  "Jonah",           "OT", "Hebrew"),
    (33, "Mic",  "Micah",           "OT", "Hebrew"),
    (34, "Nam",  "Nahum",           "OT", "Hebrew"),
    (35, "Hab",  "Habakkuk",        "OT", "Hebrew"),
    (36, "Zep",  "Zephaniah",       "OT", "Hebrew"),
    (37, "Hag",  "Haggai",          "OT", "Hebrew"),
    (38, "Zec",  "Zechariah",       "OT", "Hebrew"),
    (39, "Mal",  "Malachi",         "OT", "Hebrew"),
    (40, "Mat",  "Matthew",         "NT", "Greek"),
    (41, "Mrk",  "Mark",            "NT", "Greek"),
    (42, "Luk",  "Luke",            "NT", "Greek"),
    (43, "Jhn",  "John",            "NT", "Greek"),
    (44, "Act",  "Acts",            "NT", "Greek"),
    (45, "Rom",  "Romans",          "NT", "Greek"),
    (46, "1Co",  "1 Corinthians",   "NT", "Greek"),
    (47, "2Co",  "2 Corinthians",   "NT", "Greek"),
    (48, "Gal",  "Galatians",       "NT", "Greek"),
    (49, "Eph",  "Ephesians",       "NT", "Greek"),
    (50, "Php",  "Philippians",     "NT", "Greek"),
    (51, "Col",  "Colossians",      "NT", "Greek"),
    (52, "1Th",  "1 Thessalonians", "NT", "Greek"),
    (53, "2Th",  "2 Thessalonians", "NT", "Greek"),
    (54, "1Ti",  "1 Timothy",       "NT", "Greek"),
    (55, "2Ti",  "2 Timothy",       "NT", "Greek"),
    (56, "Tit",  "Titus",           "NT", "Greek"),
    (57, "Phm",  "Philemon",        "NT", "Greek"),
    (58, "Heb",  "Hebrews",         "NT", "Greek"),
    (59, "Jas",  "James",           "NT", "Greek"),
    (60, "1Pe",  "1 Peter",         "NT", "Greek"),
    (61, "2Pe",  "2 Peter",         "NT", "Greek"),
    (62, "1Jn",  "1 John",          "NT", "Greek"),
    (63, "2Jn",  "2 John",          "NT", "Greek"),
    (64, "3Jn",  "3 John",          "NT", "Greek"),
    (65, "Jud",  "Jude",            "NT", "Greek"),
    (66, "Rev",  "Revelation",      "NT", "Greek"),
]
OSIS_TO_BOOK_ID = {osis: bid for bid, osis, *_ in BOOKS}
OSIS_BY_ID      = {bid: osis for bid, osis, *_ in BOOKS}

# Edition table seed data. (code, name, language, description, edition_order)
EDITIONS: List[Tuple[str, str, str, str, int]] = [
    ("NA28", "Nestle-Aland 28th edition (2012)",       "Greek",  "Modern critical Greek NT used by most translators",                  1),
    ("NA27", "Nestle-Aland 27th edition",              "Greek",  "Predecessor of NA28",                                                2),
    ("Tyn",  "Tyndale House GNT (2017)",               "Greek",  "Tyndale House Greek New Testament",                                  3),
    ("SBL",  "SBL GNT (Holmes 2010)",                  "Greek",  "Society of Biblical Literature Greek NT",                            4),
    ("WH",   "Westcott + Hort (1881)",                 "Greek",  "Critical text by Westcott and Hort",                                 5),
    ("Treg", "Tregelles (1879) / Jongkind (2009)",     "Greek",  "Tregelles' Greek NT, modern edition by Jongkind",                    6),
    ("TR",   "Textus Receptus (Scrivener 1894)",       "Greek",  "Underlying Greek text of the KJV (Scrivener's edition)",             7),
    ("Byz",  "Byzantine (Robinson-Pierpont 2005)",     "Greek",  "Majority/Byzantine Text of the Greek-speaking Orthodox tradition",   8),
    ("KJV",  "King James Version (1611)",              "Greek",  "Underlying Greek text of the King James Bible",                      9),

    ("L",    "Leningrad codex",                        "Hebrew", "The base Hebrew manuscript (Westminster Leningrad Codex)",          10),
    ("Q",    "Qere",                                   "Hebrew", "Scribal 'spoken' marginal correction",                              11),
    ("K",    "Ketiv",                                  "Hebrew", "Original 'written' text being corrected by Qere",                   12),
    ("R",    "Restored",                               "Hebrew", "Text restored from parallels (Jos.21.36-37, Neh.7.67b)",            13),
    ("X",    "LXX-derived",                            "Hebrew", "Hebrew reconstructed from the Septuagint (BHS / BHK apparatus)",    14),
    ("A",    "Aleppo manuscript",                      "Hebrew", "Aleppo Codex",                                                      15),
    ("B",    "Biblia Hebraica Stuttgartensia",         "Hebrew", "BHS edition where it deviates from the Masoretic Text",             16),
    ("C",    "Cairensis manuscript",                   "Hebrew", "Cairo Codex of the Prophets",                                       17),
    ("D",    "Dead Sea / Judean Desert manuscript",    "Hebrew", "Dead Sea Scrolls and other Judean Desert finds",                    18),
    ("E",    "Editorial emendation",                   "Hebrew", "Scholarly emendation when the Hebrew is corrupt",                   19),
    ("F",    "Formatting variant",                     "Hebrew", "Pointing or word-division variant only",                            20),
    ("H",    "Ben Chaim edition",                      "Hebrew", "Second Rabbinic Bible (Ben Chaim)",                                 21),
    ("P",    "Alternate punctuation",                  "Hebrew", "Different punctuation as marked in major manuscripts",              22),
    ("S",    "Scribal traditions",                     "Hebrew", "Itture/Tiqqune Sopherim, Masora etc.",                              23),
    ("V",    "Other Hebrew manuscript variant",        "Hebrew", "Variant in another Hebrew manuscript",                              24),
]

# Maps edition code → (greek_id, hebrew_id) — set after seeding.
EDITION_ID_BY_CODE_LANG: Dict[Tuple[str, str], int] = {}

# A line is a real word-data row when it starts with:
#   BookCode.Chapter.Verse[<bracketed alt>]#WordNum=Type<TAB>...
WORD_LINE_RE = re.compile(
    r"""^
        (?P<book>[1-9]?[A-Z][a-z]+)
        \.
        (?P<chap>\d+)
        \.
        (?P<verse>\d+)
        (?P<alt>[\(\[\{][^\)\]\}]*[\)\]\}])?
        \#
        (?P<wordnum>\d+)
        =
        (?P<srctype>[^\t]+)
        \t
    """,
    re.VERBOSE,
)
STRONGS_PRIMARY_RE = re.compile(r"([HG])(\d{3,5})")


def _extract_primary_strongs(s: Optional[str]) -> Optional[str]:
    """Return the canonical/lexical Strong's code from a (possibly compound) raw value.

    Handles STEPBible dStrongs forms for Hebrew prefixed words:
      'H9003/{H7225G}'  → 'H7225'   (the lexical form inside braces is primary for this slot)
      '{H0430G}'        → 'H0430'
      'H9003/H7225G'    → 'H7225'   (fallback to last match)
      'H1234'           → 'H1234'
    The G (and other trailing letters) are stripped by the digit capture.
    This ensures gematria search results (and strongs_primary index) show the
    main content word rather than a preposition/prefix tag.
    """
    if not s:
        return None
    # Prefer the code inside the first {...} when present (the "significant" / lexical tag).
    m = re.search(r'\{([HG])(\d{3,5})', s)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    # Fallback: LAST match in the raw. This picks the rightmost in prefix chains
    # like H9003/H7225G or H9002/H9009/H0776G (the lexical/content word), while
    # plain tags are unaffected. (Braced forms are the common compound in practice.)
    matches = STRONGS_PRIMARY_RE.findall(s)
    if matches:
        h, num = matches[-1]
        return f"{h}{num}"
    return None

# A summary block leader: '# Ref\t...' or '#_Ref\t...' but NOT
# '#_Translation' / '#_Word=Grammar' / '#_Word+Grammar' / '#_Significant variant'
SUMMARY_HEAD_RE = re.compile(
    r"""^
        \#
        (?:[ _])
        (?P<book>[1-9]?[A-Z][a-z]+)
        \.
        (?P<chap>\d+)
        \.
        (?P<verse>\d+)
        (?:[\(\[\{][^\)\]\}]*[\)\]\}])?
        \t
    """,
    re.VERBOSE,
)


# =====================================================================
# Edition-list parsing helpers
# =====================================================================

# Map a single Greek edition token (possibly with displacement suffix)
# into (code, is_minor). We discard displacement (»1, «2) per user choice.
GREEK_DISPLACEMENT_RE = re.compile(r"[»«]\d+$")
GREEK_EDITION_TOKENS = {"NA28", "NA27", "Tyn", "SBL", "WH", "Treg", "TR", "Byz", "KJV"}


def parse_greek_editions(s: Optional[str]) -> List[Tuple[str, bool]]:
    """Parse a Greek 'editions' string like 'NA28+NA27+Tyn+TR»1+Byz»1'
    into a list of (edition_code, is_minor) tuples. is_minor is always
    False here because the Greek 'editions' column lists exact agreement.
    """
    if not s:
        return []
    out = []
    for token in s.split("+"):
        token = token.strip()
        if not token:
            continue
        # strip displacement suffix
        token = GREEK_DISPLACEMENT_RE.sub("", token)
        if token in GREEK_EDITION_TOKENS:
            out.append((token, False))
    return out


# Hebrew source-type letters → edition codes.
HEBREW_LETTER_TO_CODE = {
    "L": "L", "Q": "Q", "K": "K", "R": "R", "X": "X",
    "A": "A", "B": "B", "C": "C", "D": "D", "E": "E",
    "F": "F", "H": "H", "P": "P", "S": "S", "V": "V",
}


def parse_hebrew_source_type(src: str) -> Tuple[List[Tuple[str, bool]], List[Tuple[str, bool]]]:
    """Parse a Hebrew source_type marker like 'LA(bh)' or 'Q(K)' into:
        ( base_editions, variant_editions )
    each a list of (code, is_minor). 'base' = letters before any '(';
    'variant' = letters inside '(...)'. is_minor reflects letter case
    (lowercase = insignificant difference per the source docs).

    Source types may use '+' to separate multiple variant groups, e.g.
        'Q(K+B)' = base Q; variant K and variant B
        'L(b+p)' = base L; minor variants B and P
    """
    base: List[Tuple[str, bool]] = []
    var:  List[Tuple[str, bool]] = []

    # Pull out variant groups in parens (there can be multiple after '+').
    paren_text = ""
    head = src
    if "(" in src:
        head, _, rest = src.partition("(")
        # rest may be 'K)' or 'K+B)' or 'bh)+something'
        # We just iterate characters between balanced parens.
        depth = 0
        for ch in src[len(head):]:
            if ch == "(":
                depth += 1
                continue
            if ch == ")":
                depth -= 1
                continue
            if depth >= 1:
                paren_text += ch

    for ch in head:
        if ch in HEBREW_LETTER_TO_CODE:
            base.append((HEBREW_LETTER_TO_CODE[ch], False))
        elif ch.upper() in HEBREW_LETTER_TO_CODE and ch.islower():
            base.append((HEBREW_LETTER_TO_CODE[ch.upper()], True))
        # other characters (digits, '+') are ignored

    for ch in paren_text:
        if ch == "+" or ch == " ":
            continue
        if ch in HEBREW_LETTER_TO_CODE:
            var.append((HEBREW_LETTER_TO_CODE[ch], False))   # uppercase = significant
        elif ch.upper() in HEBREW_LETTER_TO_CODE and ch.islower():
            var.append((HEBREW_LETTER_TO_CODE[ch.upper()], True))

    # Deduplicate (keep first occurrence).
    def _dedup(seq):
        seen = set()
        out  = []
        for code, minor in seq:
            if code in seen:
                continue
            seen.add(code)
            out.append((code, minor))
        return out

    return _dedup(base), _dedup(var)


# =====================================================================
# Variant-string parsers
# =====================================================================

# Greek meaning variant: 'βληθῇ (T=blēthēa) may be cast - G0906=V-APS-3S in: TR«3+Byz«3'
# Hebrew meaning variant: 'K= 'o.ho.Lo/h (אָהֳלֹ/ה) "tent/ his" (H0168G/H9023=HNcbsc/Sp3ms)'
# Multiple variants are separated by ';' (rare).

GREEK_MEANING_RE = re.compile(
    r"""^
        \s*
        (?P<text>\S+(?:\s+\S+)*?)               # variant Greek text (possibly with diacritics / punctuation)
        \s*
        \(
          (?P<src>[A-Za-z][A-Za-z]?)            # 't' or 'O' or 'T' etc. — source code (case marks significance)
          =
          (?P<translit>[^)]+)
        \)
        \s*
        (?P<translation>.+?)
        \s*-\s*
        (?P<strongs>[A-Za-z0-9]+)
        =
        (?P<grammar>[A-Za-z0-9\-]+)
        \s*
        in:\s*
        (?P<editions>.+?)\s*$
    """,
    re.VERBOSE,
)


def parse_greek_meaning_variant(s: str) -> List[dict]:
    """Parse Greek col-7 'meaning variants' field. Returns list of dicts."""
    if not s:
        return []
    out = []
    # Multiple variants are separated by ';' but ';' may also appear within a translation.
    # Heuristic: split on '; ' that is followed by a Unicode Greek-looking token.
    # In practice, multi-variant rows are rare; try a single-pass parse first.
    parts = [s] if " in: " not in s or s.count(" in: ") <= 1 else _split_top_level(s, ";")
    for part in parts:
        part = part.strip().rstrip(";").strip()
        if not part:
            continue
        m = GREEK_MEANING_RE.match(part)
        if m:
            out.append({
                "kind":            "meaning",
                "text_original":   m.group("text").strip(),
                "transliteration": m.group("translit").strip(),
                "translation":     m.group("translation").strip(),
                "strongs":         m.group("strongs").strip(),
                "grammar":         m.group("grammar").strip(),
                "src_letter":      m.group("src"),
                "edition_string":  m.group("editions"),
                "raw":             part,
            })
        else:
            # Fallback: keep the raw text as a note-only variant with no parsed fields.
            out.append({
                "kind":           "meaning",
                "text_original":  None,
                "transliteration":None,
                "translation":    None,
                "strongs":        None,
                "grammar":        None,
                "src_letter":     None,
                "edition_string": None,
                "raw":            part,
            })
    return out


# Hebrew meaning variant pattern.
HEB_MEANING_RE = re.compile(
    r"""^
        \s*
        (?P<src>[A-Z]+)\s*=\s*
        (?P<translit>\S+)\s+
        \(
          (?P<hebrew>[^)]+)
        \)\s+
        "
          (?P<translation>[^"]+)
        "\s*
        \(
          (?P<strongs>[^=]+)=(?P<grammar>[^)]+)
        \)
        \s*$
    """,
    re.VERBOSE,
)


def parse_hebrew_meaning_variant(s: str) -> List[dict]:
    if not s:
        return []
    out = []
    for part in _split_top_level(s, ";"):
        part = part.strip()
        if not part:
            continue
        m = HEB_MEANING_RE.match(part)
        if m:
            out.append({
                "kind":            "meaning",
                "text_original":   m.group("hebrew").strip(),
                "transliteration": m.group("translit").strip(),
                "translation":     m.group("translation").strip(),
                "strongs":         m.group("strongs").strip(),
                "grammar":         m.group("grammar").strip(),
                "src_letter":      m.group("src"),
                "edition_string":  m.group("src"),     # single-letter source acts as edition
                "raw":             part,
            })
        else:
            out.append({
                "kind": "meaning", "text_original": None, "transliteration": None,
                "translation": None, "strongs": None, "grammar": None,
                "src_letter": None, "edition_string": None, "raw": part,
            })
    return out


# Spelling variants (both languages), e.g.
#   Greek:  'Treg: Βοὸς ; +Byz+TR: Βοὸζ ;'
#   Hebrew: 'L= הַוְצֵ֣א ¦ ;K= הוֹצֵא'
#           'B= עֹֽשֶׂה'
SPELLING_GROUP_RE_GREEK = re.compile(
    r"^\s*(?P<eds>[A-Za-z0-9+]+)\s*:\s*(?P<text>.+?)\s*$"
)
SPELLING_GROUP_RE_HEB = re.compile(
    r"^\s*(?P<src>[A-Z]+)\s*=\s*(?P<text>.+?)\s*$"
)


def parse_spelling_variants(s: str, language: str) -> List[dict]:
    if not s:
        return []
    out = []
    for raw in _split_top_level(s, ";"):
        raw = raw.strip().lstrip("+").strip()
        # Hebrew sometimes uses '¦' as a separator inside the value; strip it.
        raw = raw.replace("¦", " ").strip()
        if not raw:
            continue
        if language == "Greek":
            m = SPELLING_GROUP_RE_GREEK.match(raw)
            if m:
                out.append({
                    "kind":            "spelling",
                    "text_original":   m.group("text").strip(),
                    "transliteration": None,
                    "translation":     None,
                    "strongs":         None,
                    "grammar":         None,
                    "src_letter":      None,
                    "edition_string":  m.group("eds"),
                    "raw":             raw,
                })
            else:
                out.append({"kind": "spelling", "text_original": None, "transliteration": None,
                            "translation": None, "strongs": None, "grammar": None,
                            "src_letter": None, "edition_string": None, "raw": raw})
        else:   # Hebrew
            m = SPELLING_GROUP_RE_HEB.match(raw)
            if m:
                out.append({
                    "kind":            "spelling",
                    "text_original":   m.group("text").strip(),
                    "transliteration": None,
                    "translation":     None,
                    "strongs":         None,
                    "grammar":         None,
                    "src_letter":      m.group("src"),
                    "edition_string":  m.group("src"),
                    "raw":             raw,
                })
            else:
                out.append({"kind": "spelling", "text_original": None, "transliteration": None,
                            "translation": None, "strongs": None, "grammar": None,
                            "src_letter": None, "edition_string": None, "raw": raw})
    return out


def _split_top_level(s: str, delim: str) -> List[str]:
    """Split string on `delim` that occurs at the top paren depth."""
    parts: List[str] = []
    cur = []
    depth = 0
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        if depth == 0 and ch == delim:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return parts


def parse_edition_string(s: str, language: str) -> List[Tuple[str, bool]]:
    """Parse an edition list (the 'in: TR+Byz' portion of a variant). Returns
    list of (edition_code, is_minor)."""
    if not s:
        return []
    out: List[Tuple[str, bool]] = []
    if language == "Greek":
        for token in s.replace(" ", "").split("+"):
            if not token:
                continue
            token = GREEK_DISPLACEMENT_RE.sub("", token)
            if token in GREEK_EDITION_TOKENS:
                out.append((token, False))
    else:
        for ch in s:
            if ch in HEBREW_LETTER_TO_CODE:
                out.append((HEBREW_LETTER_TO_CODE[ch], False))
            elif ch.upper() in HEBREW_LETTER_TO_CODE and ch.islower():
                out.append((HEBREW_LETTER_TO_CODE[ch.upper()], True))
    # dedupe
    seen = set()
    dedup = []
    for code, minor in out:
        if code in seen:
            continue
        seen.add(code)
        dedup.append((code, minor))
    return dedup


# =====================================================================
# Variant-notes parser (Greek col 14)
# =====================================================================
# Examples:
#   'v βληθῇ (<i>blēthēa</i>) "may be cast" occurs in traditional manuscripts (TR+Byz) instead of ...'
#   '^ αὐτῆς τὸν πρωτότοκον, (<i>autēs ton prōtotokon</i>) "of her..." is only in traditional manuscripts (TR+Byz)'
#   '^ ' (empty marker)
NOTE_OMIT_RE = re.compile(r"^\^(?:\s|$)")
NOTE_VAR_RE  = re.compile(r"^v(?:\s|$)")


def classify_note(note: Optional[str]) -> Optional[str]:
    if not note:
        return None
    if NOTE_OMIT_RE.match(note):
        return "omission"      # '^' = a word added/missing (treat as omission)
    if NOTE_VAR_RE.match(note):
        return "meaning"       # 'v' = a word substitution affecting translation
    return None


# =====================================================================
# Hebrew expanded-tag parser  (col 12)
# =====================================================================
# Format: morphemes separated by '/' (and '\' for punctuation morphemes).
# Each morpheme: 'STRONG=hebrew=gloss' optionally followed by '»submeaning'
# and/or ':submeaning2'. Roots are wrapped in '{...}'.
#
# Examples:
#   'H9009=ה=the/{H8064=שָׁמַיִם=heaven}'
#   'H9001=ו=&/{H6213H=עָשָׂה=: make(OBJECT)»to make:1_make(OBJECT)}'
#   '{H3605=כֹּל=all}\H9014=־=link'

EXPANDED_TOKEN_RE = re.compile(
    r"""(?P<brace>\{)?
        (?P<strong>H\d{3,5}[A-Za-z]?|G\d{3,5}[A-Za-z]?)
        =
        (?P<hebrew>[^=]*?)
        =
        (?P<gloss>[^/\\}]*)
        (?P<endbrace>\})?
    """,
    re.VERBOSE,
)


def parse_expanded_tags(s: str) -> List[dict]:
    """Parse the Hebrew 'Expanded Strong tags' column into a list of
    morpheme dicts (preserving order)."""
    if not s:
        return []
    out = []
    # Walk the string left-to-right, splitting on '/' and '\' while tracking
    # whether we're inside '{...}' (root).
    pos = 0
    morphemes: List[Tuple[str, str]] = []   # (token, separator_before)
    sep = ""
    cur = []
    in_brace = False
    for ch in s:
        if ch == "{":
            in_brace = True
            cur.append(ch)
        elif ch == "}":
            in_brace = False
            cur.append(ch)
        elif (ch == "/" or ch == "\\") and not in_brace:
            morphemes.append((sep, "".join(cur)))
            sep = ch
            cur = []
        else:
            cur.append(ch)
    morphemes.append((sep, "".join(cur)))

    for sep_before, token in morphemes:
        token = token.strip()
        if not token:
            continue
        is_root = token.startswith("{") and token.endswith("}")
        body = token.strip("{}")
        # Each token has form: STRONG=hebrew=gloss[then-sub][:sub2]
        # Forgiving manual split because the gloss may contain extra '='.
        eq1 = body.find("=")
        eq2 = body.find("=", eq1 + 1) if eq1 >= 0 else -1
        if eq1 < 0 or eq2 < 0:
            continue
        strong = body[:eq1].strip()
        hebrew = body[eq1 + 1:eq2].strip()
        rest   = body[eq2 + 1:].strip()
        sub = None
        gloss = rest
        if "»" in rest:
            gloss, _, sub = rest.partition("»")
        elif rest.startswith(":"):
            gloss = rest.lstrip(": ").strip()
            sub = None
        gloss = gloss.strip(": ").strip()
        if is_root:
            role = "root"
        elif sep_before == "\\":
            role = "punctuation"
        else:
            role = "prefix"
        out.append({
            "role":       role,
            "strong":     strong,
            "hebrew":     hebrew or None,
            "gloss":      gloss or None,
            "submeaning": sub.strip() if sub else None,
        })

    seen_root = False
    for m in out:
        if m["role"] == "root":
            seen_root = True
            continue
        if seen_root and m["role"] == "prefix":
            m["role"] = "suffix"
    return out


# =====================================================================
# Conjoin-link parser
# =====================================================================
CONJOIN_RE = re.compile(
    r"""^
        \#(?P<src>\d+)
        (?:
            (?P<dir>[»«])
            (?P<tgt>\d+)
            (?::
                (?P<strong>[HG]\d{3,5}[A-Za-z]?)
            )?
        )?
        $
    """,
    re.VERBOSE,
)


def parse_conjoin(s):
    if not s:
        return None
    m = CONJOIN_RE.match(s.strip())
    if not m or not m.group("dir"):
        return None
    return {
        "target_word_num": int(m.group("tgt")),
        "direction":       "forward" if m.group("dir") == "»" else "backward",
        "target_strong":   m.group("strong"),
    }


# =====================================================================
# Parsed row containers
# =====================================================================

@dataclass
class WordRow:
    book_id:           int
    chapter:           int
    verse:             int
    word_num:          int                 # original #NN from source (may repeat across chunks in 15 Hebrew verses)
    source_type:       str
    is_variant_marked: bool
    language:          str
    text_original:     Optional[str]
    transliteration:   Optional[str]
    translation:       Optional[str]
    strongs:           Optional[str]
    strongs_primary:   Optional[str]
    grammar:           Optional[str]
    dictionary_form:   Optional[str]
    submeaning:        Optional[str]
    sstrong_instance:  Optional[str]
    raw_ref:           str
    # Filled in by the verse accumulator after all words are collected:
    position:          int                 = 0    # 1..N sequential in verse, used as the unique-key column
    chunk_num:         int                 = 1    # which source-block within the verse the word belongs to
    base_editions:     List[Tuple[str, bool]] = field(default_factory=list)
    alt_strongs:       List[str]              = field(default_factory=list)
    morphemes:         List[dict]             = field(default_factory=list)
    conjoin:           Optional[dict]         = None
    variants:          List[dict]             = field(default_factory=list)
    variant_notes_raw: Optional[str]          = None


@dataclass
class SummaryBlock:
    block_num:     int
    original_line: str
    translation:   str
    grammar:       str
    sig_variant:   Optional[str]


@dataclass
class VerseAccumulator:
    book_id:    int
    chapter:    int
    verse:      int
    raw_ref:    str
    osis_ref:   str
    originals:  List[str]
    englishes:  List[str]
    word_count: int
    words:      List[WordRow]
    summaries:  List[SummaryBlock]


# =====================================================================
# File-level parsing
# =====================================================================

SIG_VAR_HAS_CONTENT_RE = re.compile(r"^#_Significant variant\t.*\S")


def _assign_position_and_chunk(words):
    """Assign sequential `position` (1..N) and `chunk_num` to every word in
    a verse. A new chunk starts whenever the source `word_num` does not
    increase from the previous word -- this handles the 15 Hebrew verses
    where two source blocks share an English ref and each restarts at #01.
    """
    chunk = 1
    last_num = 0
    for i, w in enumerate(words, start=1):
        if i > 1 and w.word_num <= last_num:
            chunk += 1
        w.chunk_num = chunk
        w.position  = i
        last_num    = w.word_num


def parse_word_line(line, language):
    m = WORD_LINE_RE.match(line)
    if not m:
        return None
    book_code = m.group("book")
    book_id = OSIS_TO_BOOK_ID.get(book_code)
    if book_id is None:
        return None

    cols = line.rstrip("\n").split("\t")
    while len(cols) < 17:
        cols.append("")

    raw_ref     = cols[0]
    source_type = m.group("srctype").strip()
    is_var      = bool(re.search(r"[\(\[][A-Z]", source_type))
    chap        = int(m.group("chap"))
    verse_num   = int(m.group("verse"))
    word_num    = int(m.group("wordnum"))

    editions_raw = None
    if language == "Hebrew":
        text_original   = _e(cols[1])
        transliteration = _e(cols[2])
        translation     = _e(cols[3])
        strongs         = _e(cols[4])
        grammar         = _e(cols[5])
        meaning_var_raw = _e(cols[6])
        spelling_var_raw= _e(cols[7])
        root_strong     = _e(cols[8])
        alt_strong_raw  = _e(cols[9])
        conjoin_raw     = _e(cols[10])
        expanded_raw    = _e(cols[11])
        dictionary_form = None
        submeaning      = None
        notes_raw       = None
        sstrong_instance= root_strong
    else:
        text_original   = _e(cols[1])
        transliteration = None
        translation     = _e(cols[2])
        strongs_grammar = _e(cols[3])
        if strongs_grammar and "=" in strongs_grammar:
            strongs, _, grammar = strongs_grammar.partition("=")
            strongs = strongs.strip() or None
            grammar = grammar.strip() or None
        else:
            strongs = strongs_grammar
            grammar = None
        dictionary_form = _e(cols[4])
        editions_raw    = _e(cols[5])
        meaning_var_raw = _e(cols[6])
        spelling_var_raw= _e(cols[7])
        submeaning      = _e(cols[9])
        conjoin_raw     = _e(cols[10])
        sstrong_instance= _e(cols[11])
        alt_strong_raw  = _e(cols[12])
        notes_raw       = _e(cols[13])
        expanded_raw    = None

    strongs_primary = _extract_primary_strongs(strongs)

    if language == "Greek":
        base_editions = parse_greek_editions(editions_raw)
    else:
        base_h, _ = parse_hebrew_source_type(source_type)
        base_editions = base_h

    alt_strongs = []
    if alt_strong_raw:
        for tok in alt_strong_raw.split(","):
            tok = tok.strip()
            if tok and re.match(r"^[HG]\d{3,5}[A-Za-z]?$", tok):
                alt_strongs.append(tok)

    conjoin   = parse_conjoin(conjoin_raw)
    morphemes = parse_expanded_tags(expanded_raw) if expanded_raw else []

    variants = []
    if language == "Greek":
        variants.extend(parse_greek_meaning_variant(meaning_var_raw or ""))
    else:
        variants.extend(parse_hebrew_meaning_variant(meaning_var_raw or ""))
    variants.extend(parse_spelling_variants(spelling_var_raw or "", language))

    if notes_raw:
        kind = classify_note(notes_raw)
        if not variants and kind:
            variants.append({
                "kind":            kind,
                "text_original":   None,
                "transliteration": None,
                "translation":     None,
                "strongs":         None,
                "grammar":         None,
                "src_letter":      None,
                "edition_string":  None,
                "raw":             notes_raw,
            })
        else:
            for v in variants:
                if not v.get("note_attached"):
                    v["raw"] = (v["raw"] or "") + " || " + notes_raw if v.get("raw") else notes_raw
                    v["note_attached"] = True
                    break

    return WordRow(
        book_id=book_id, chapter=chap, verse=verse_num, word_num=word_num,
        source_type=source_type, is_variant_marked=is_var, language=language,
        text_original=text_original, transliteration=transliteration,
        translation=translation, strongs=strongs, strongs_primary=strongs_primary,
        grammar=grammar, dictionary_form=dictionary_form, submeaning=submeaning,
        sstrong_instance=sstrong_instance, raw_ref=raw_ref,
        base_editions=base_editions, alt_strongs=alt_strongs, morphemes=morphemes,
        conjoin=conjoin, variants=variants, variant_notes_raw=notes_raw,
    )


def _e(s):
    if s is None:
        return None
    s = s.strip()
    return s if s else None


def iter_verses_from_file(path, language):
    current = None
    pending_block = None

    def finalize_pending(into):
        if not pending_block:
            return
        head = pending_block[0] if len(pending_block) >= 1 else ""
        tr   = pending_block[1] if len(pending_block) >= 2 else ""
        gr   = pending_block[2] if len(pending_block) >= 3 else ""
        sv   = pending_block[3] if len(pending_block) >= 4 else ""
        sv_text = sv if SIG_VAR_HAS_CONTENT_RE.match(sv or "") else None
        into.summaries.append(SummaryBlock(
            block_num     = len(into.summaries) + 1,
            original_line = head.rstrip("\n"),
            translation   = tr.rstrip("\n"),
            grammar       = gr.rstrip("\n"),
            sig_variant   = sv_text.rstrip("\n") if sv_text else None,
        ))

    with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
        for raw in fh:
            if raw.startswith("#"):
                m = SUMMARY_HEAD_RE.match(raw)
                if m:
                    book_code = m.group("book")
                    book_id   = OSIS_TO_BOOK_ID.get(book_code)
                    chap      = int(m.group("chap"))
                    verse_num = int(m.group("verse"))
                    if book_id is None:
                        continue
                    key = (book_id, chap, verse_num)
                    if current and pending_block:
                        finalize_pending(current)
                        pending_block = None
                    if current is None or (current.book_id, current.chapter, current.verse) != key:
                        if current is not None:
                            _assign_position_and_chunk(current.words)
                            yield current
                        ref_field = raw.split("\t", 1)[0].lstrip("# _")
                        osis_ref  = f"{book_code}.{chap}.{verse_num}"
                        current = VerseAccumulator(
                            book_id=book_id, chapter=chap, verse=verse_num,
                            raw_ref=ref_field, osis_ref=osis_ref,
                            originals=[], englishes=[], word_count=0,
                            words=[], summaries=[],
                        )
                    pending_block = [raw]
                    continue

                if raw.startswith("#_Translation\t") or \
                   raw.startswith("#_Word=Grammar\t") or \
                   raw.startswith("#_Word+Grammar\t") or \
                   raw.startswith("#_Significant variant\t") or \
                   raw.startswith("#_Significant variant"):
                    if pending_block is not None:
                        pending_block.append(raw)
                    continue
                continue

            row = parse_word_line(raw, language)
            if row is None:
                continue
            key = (row.book_id, row.chapter, row.verse)
            if current is None or (current.book_id, current.chapter, current.verse) != key:
                if current and pending_block:
                    finalize_pending(current)
                    pending_block = None
                if current is not None:
                    _assign_position_and_chunk(current.words)
                    yield current
                osis_ref = f"{OSIS_BY_ID[row.book_id]}.{row.chapter}.{row.verse}"
                current = VerseAccumulator(
                    book_id=row.book_id, chapter=row.chapter, verse=row.verse,
                    raw_ref=row.raw_ref.split("#", 1)[0], osis_ref=osis_ref,
                    originals=[], englishes=[], word_count=0,
                    words=[], summaries=[],
                )

            if pending_block is not None:
                finalize_pending(current)
                pending_block = None

            if row.text_original:
                current.originals.append(row.text_original)
            if row.translation:
                current.englishes.append(row.translation)
            current.word_count += 1
            current.words.append(row)

    if current and pending_block:
        finalize_pending(current)
    if current is not None:
        _assign_position_and_chunk(current.words)
        yield current


# =====================================================================
# Local SQL helpers (schema application only — connection logic is in _db)
# =====================================================================

def _strip_sql_comments(sql: str) -> str:
    """Remove -- single-line and /* */ multi-line comments from SQL."""
    # Remove single-line comments (--)
    sql = re.sub(r'--.*?(?:\n|$)', '\n', sql)
    # Remove multi-line comments (/* ... */)
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    return sql


def ensure_core_tables(cur, project_root: Path, db_name: str, create: bool = False) -> bool:
    """Check whether the core tables exist. Create them from schema.sql if requested (create=True).

    The main import_bible.py script (whose purpose is to create the full stepbible DB
    from the STEPBible source files) always calls with create=True. This triggers
    the full DROP+CREATE from schema.sql (plus gematria drops) so the result is
    always a clean, complete DB. A safety prompt is shown if the DB already has data.
    The schema.sql is designed to be fully re-runnable.
    """
    schema_path = project_root / "sql" / "schema" / "schema.sql"

    if create:
        if not schema_path.exists():
            print(f"ERROR: Schema file not found: {schema_path}")
            return False

        # Safety for "out of the box" use by others to create the stepbible DB.
        # If the target DB (from BIBLE_DB_NAME) already contains imported data,
        # warn and ask for confirmation before the schema drops erase everything.
        # This replaces the need for extra debug parameters like --truncate for normal use.
        has_existing_data = False
        existing_count = 0
        try:
            cur.execute("SELECT COUNT(*) FROM verse")
            existing_count = cur.fetchone()[0] or 0
            if existing_count > 0:
                has_existing_data = True
        except Exception:
            # No verse table (or other error) means this is a fresh/empty DB.
            pass

        if has_existing_data:
            print(f"\nSelected database '{db_name}' has data.")
            print("It will be erased and replaced.")
            if os.environ.get("BIBLE_PIPELINE_FORCE") == "1":
                print("  (BIBLE_PIPELINE_FORCE=1 — auto-confirming, no prompt)")
            else:
                try:
                    ans = input("Continue? (Y/N) ").strip().upper()
                except (EOFError, KeyboardInterrupt):
                    ans = "N"
                if not ans.startswith("Y"):
                    print("Aborted by user.")
                    return False

        print(f"Creating core tables from {schema_path} into database '{db_name}' ...")
        with open(schema_path, encoding="utf-8") as f:
            sql_script = f.read()

        # Remove hard-coded CREATE DATABASE / USE statements (they target 'stepbible'
        # and would switch us away from the DB we actually connected to).
        sql_script = re.sub(
            r'(?im)^\s*(CREATE\s+DATABASE|USE)\s+[^;]+;', 
            '', 
            sql_script
        )

        # Strip comments so that explanatory -- comments don't get turned into
        # bogus SQL statements when we later split on ';'.
        sql_script = _strip_sql_comments(sql_script)

        # Execute the schema in a driver-agnostic way (no reliance on multi=True).
        # We temporarily disable FK checks because:
        #   - The schema.sql contains DROP TABLE statements.
        #   - Other tables (gematria_*, etc.) may already exist and have FKs
        #     pointing at word/verse/etc.
        cur.execute("SET FOREIGN_KEY_CHECKS=0;")

        # Explicitly drop gematria tables (if present) so we get a clean slate
        # (gematria tables will be (re)created as part of the full DB creation).
        cur.execute("DROP TABLE IF EXISTS gematria_verse;")
        cur.execute("DROP TABLE IF EXISTS gematria_word;")

        statements = [s.strip() for s in sql_script.split(';') if s.strip()]
        for stmt in statements:
            cur.execute(stmt)

        cur.execute("SET FOREIGN_KEY_CHECKS=1;")
        cur.connection.commit()
        print("  Schema created successfully.")
        return True

    # Not forcing create: just check for existence (normal run against pre-created schema)
    try:
        cur.execute("SHOW TABLES LIKE 'book'")
        if cur.fetchone():
            return True
    except Exception:
        pass

    print("\nERROR: Required tables do not exist in the target database.")
    print(f"       Target DB: {db_name}")
    print(f"       Expected schema file: {schema_path}")
    print("       Run one of:")
    print(f"           mysql -u root -p {db_name} < {schema_path}")
    print("           python import_bible.py   # script always ensures core + gematria schemas")
    print()
    return False


# =====================================================================
# Main loader
# =====================================================================

SOURCE_FILES = [
    ("TAHOT Gen-Deu*.txt", "Hebrew"),
    ("TAHOT Jos-Est*.txt", "Hebrew"),
    ("TAHOT Job-Sng*.txt", "Hebrew"),
    ("TAHOT Isa-Mal*.txt", "Hebrew"),
    ("TAGNT Mat-Jhn*.txt", "Greek"),
    ("TAGNT Act-Rev*.txt", "Greek"),
]

SQL = {
    "insert_book": (
        "INSERT INTO book (id, osis_code, name, testament, language, book_order) "
        "VALUES (%s,%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE osis_code=VALUES(osis_code), name=VALUES(name), "
        "testament=VALUES(testament), language=VALUES(language), book_order=VALUES(book_order)"
    ),
    "insert_edition": (
        "INSERT INTO edition (code, name, language, description, edition_order) "
        "VALUES (%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE name=VALUES(name), description=VALUES(description), "
        "edition_order=VALUES(edition_order)"
    ),
    "insert_verse": (
        "INSERT INTO verse (book_id, chapter, verse, osis_ref, raw_ref, "
        "text_original, text_english, word_count, has_significant_variant) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
    ),
    "insert_verse_summary": (
        "INSERT INTO verse_summary (verse_id, block_num, original_line, "
        "translation, grammar, sig_variant) VALUES (%s,%s,%s,%s,%s,%s)"
    ),
    "insert_word": (
        "INSERT INTO word (verse_id, book_id, chapter, verse, position, word_num, chunk_num, "
        "source_type, is_variant_marked, language, text_original, "
        "transliteration, translation, strongs, strongs_primary, grammar, "
        "dictionary_form, submeaning, sstrong_instance) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s,%s)"
    ),
    "insert_word_edition": (
        "INSERT IGNORE INTO word_edition (word_id, edition_id, is_minor) "
        "VALUES (%s,%s,%s)"
    ),
    "insert_word_alt_strong": (
        "INSERT INTO word_alt_strong (word_id, alt_strong) VALUES (%s,%s)"
    ),
    "insert_word_morpheme": (
        "INSERT INTO word_morpheme (word_id, morpheme_num, role, strong_code, "
        "hebrew, gloss, submeaning) VALUES (%s,%s,%s,%s,%s,%s,%s)"
    ),
    "insert_word_link": (
        "INSERT INTO word_link (word_id, target_word_id, target_word_num, "
        "target_strong, direction) VALUES (%s,%s,%s,%s,%s)"
    ),
    "insert_variant": (
        "INSERT INTO variant (word_id, kind, text_original, transliteration, "
        "translation, strongs, strongs_primary, grammar, note) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
    ),
    "insert_variant_edition": (
        "INSERT IGNORE INTO variant_edition (variant_id, edition_id, is_minor) "
        "VALUES (%s,%s,%s)"
    ),
}


def main(argv=None):
    # Project root is two levels up from this script (scripts/import/ -> scripts/ -> root)
    project_root = Path(__file__).resolve().parent.parent.parent
    default_files_dir = project_root / "data" / "raw"
    default_config    = project_root / "config.ini"

    p = argparse.ArgumentParser(description="Import STEPBible files into MariaDB (v2 schema).")
    p.add_argument("--files-dir", default=str(default_files_dir))
    p.add_argument("--config",    default=str(default_config))
    p.add_argument("--dry-run",   action="store_true", help="(debug only)")
    p.add_argument("--truncate",  action="store_true", help="(advanced: wipe data for re-load without dropping tables)")
    p.add_argument("--limit-verses", type=int, default=0, help="(debug/testing only)")
    args = p.parse_args(argv)

    files_dir = Path(args.files_dir)
    if not files_dir.is_dir():
        print(f"ERROR: --files-dir not found: {files_dir}")
        return 2

    sources = []
    for pattern, language in SOURCE_FILES:
        for m in sorted(files_dir.glob(pattern)):
            sources.append((m, language))
    if not sources:
        print("ERROR: no STEPBible files found.")
        return 2

    print(f"Found {len(sources)} source files.")
    for path, lang in sources:
        print(f"  [{lang:6s}] {path.name}")

    conn = None
    cur  = None
    if not args.dry_run:
        cfg = load_config(Path(args.config))

        # Figure out where the database name actually came from for clear messaging
        print(f"\nConnecting using single-source-of-truth config:")
        print(f"  host={cfg['host']}  port={cfg['port']}  user={cfg['user']}  database={cfg['database']}")
        print(f"  (database name comes EXCLUSIVELY from BIBLE_DB_NAME (or BIBLE_DATABASE) env var)")
        print("  → A live verification query (SELECT DATABASE()) will confirm we are on the correct DB.")
        conn, driver = get_connection(cfg)
        cur = conn.cursor()
        print(f"  connected via '{driver}'.")

        # === Live verification that we are talking to the expected database ===
        # This is the authoritative test — ask the server "what DB is this connection using right now?"
        print()
        verify_db_name(cur, cfg["database"])
        print()

        # The script's purpose is to create (or fully rebuild) the complete stepbible DB,
        # so we always ensure core schema + gematria tables (with safety prompt if data present).
        if not ensure_core_tables(cur, project_root, db_name=cfg["database"], create=True):
            return 2

        # Always apply gematria schema (we know we want the gematria tables for a full stepbible DB).
        gematria_path = project_root / "sql" / "schema" / "gematria_schema.sql"
        if gematria_path.exists():
            print(f"Applying gematria schema from {gematria_path} ...")
            with open(gematria_path, encoding="utf-8") as f:
                gem_script = f.read()
            gem_script = _strip_sql_comments(gem_script)
            # gematria_schema uses CREATE TABLE IF NOT EXISTS + FKs,
            # so we still want FK checks off during application for safety.
            cur.execute("SET FOREIGN_KEY_CHECKS=0;")
            for stmt in [s.strip() for s in gem_script.split(';') if s.strip()]:
                cur.execute(stmt)
            cur.execute("SET FOREIGN_KEY_CHECKS=1;")
            conn.commit()
            print("  Gematria tables created/verified.")
        else:
            print(f"WARNING: {gematria_path} not found — skipping gematria tables.")

        if args.truncate:
            print(f"Truncating tables in database '{cfg['database']}' ...")
            cur.execute("SET FOREIGN_KEY_CHECKS=0;")
            for t in ("variant_edition", "variant", "word_link", "word_morpheme",
                      "word_alt_strong", "word_edition", "word",
                      "verse_summary", "verse",
                      "gematria_verse", "gematria_word"):
                try:
                    cur.execute(f"TRUNCATE TABLE {t};")
                except Exception:
                    # table may not exist yet (e.g. after partial runs or if gematria schema not present)
                    pass
            cur.execute("SET FOREIGN_KEY_CHECKS=1;")
            conn.commit()

        print("Populating book + edition tables...")
        cur.executemany(SQL["insert_book"],
            [(bid, osis, name, t, lang, bid) for bid, osis, name, t, lang in BOOKS])
        cur.executemany(SQL["insert_edition"],
            [(code, name, lang, desc, order) for code, name, lang, desc, order in EDITIONS])
        conn.commit()

        cur.execute("SELECT id, code, language FROM edition")
        for row in cur.fetchall():
            EDITION_ID_BY_CODE_LANG[(row[1], row[2])] = row[0]

    started = time.time()
    totals = dict(verses=0, words=0, variants=0, morphemes=0, links=0, alt_strongs=0)

    for path, language in sources:
        print(f"\n--- {path.name} ({language}) ---", flush=True)
        per_file = dict(verses=0, words=0, variants=0, morphemes=0, links=0, alt_strongs=0)
        file_started = time.time()

        for verse in iter_verses_from_file(path, language):
            if args.limit_verses and per_file["verses"] >= args.limit_verses:
                break
            per_file["verses"] += 1
            per_file["words"]  += len(verse.words)

            # Heartbeat every 2,000 verses so the user sees activity during
            # the multi-minute parse+load (some files have 23k verses).
            if per_file["verses"] % 2000 == 0:
                rate = per_file["verses"] / max(0.001, time.time() - file_started)
                print(f"    ... {per_file['verses']:>6} verses, "
                      f"{per_file['words']:>7} words  "
                      f"({rate:0.0f} verses/sec)", flush=True)

            has_sig = any(s.sig_variant for s in verse.summaries) or \
                      any(w.is_variant_marked for w in verse.words)
            verse_text_original = " ".join(verse.originals).strip()
            verse_text_english  = " ".join(verse.englishes).strip()

            verse_id = None
            if not args.dry_run:
                cur.execute(SQL["insert_verse"], (
                    verse.book_id, verse.chapter, verse.verse,
                    verse.osis_ref, verse.raw_ref,
                    verse_text_original, verse_text_english,
                    verse.word_count, has_sig,
                ))
                verse_id = cur.lastrowid
                if verse.summaries:
                    cur.executemany(SQL["insert_verse_summary"], [
                        (verse_id, s.block_num, s.original_line, s.translation,
                         s.grammar, s.sig_variant) for s in verse.summaries
                    ])

            word_id_by_num = {}
            for w in verse.words:
                if not args.dry_run:
                    cur.execute(SQL["insert_word"], (
                        verse_id, w.book_id, w.chapter, w.verse,
                        w.position, w.word_num, w.chunk_num,
                        w.source_type, w.is_variant_marked, w.language,
                        w.text_original, w.transliteration, w.translation,
                        w.strongs, w.strongs_primary, w.grammar,
                        w.dictionary_form, w.submeaning, w.sstrong_instance,
                    ))
                    wid = cur.lastrowid
                    # Key by (chunk_num, source word_num) so duplicate word_nums
                    # across chunks resolve correctly for conjoin link lookup.
                    word_id_by_num[(w.chunk_num, w.word_num)] = wid

                    for code, minor in w.base_editions:
                        eid = EDITION_ID_BY_CODE_LANG.get((code, w.language))
                        if eid:
                            cur.execute(SQL["insert_word_edition"], (wid, eid, minor))

                    for alt in w.alt_strongs:
                        cur.execute(SQL["insert_word_alt_strong"], (wid, alt))
                        per_file["alt_strongs"] += 1

                    for i, mo in enumerate(w.morphemes, start=1):
                        cur.execute(SQL["insert_word_morpheme"], (
                            wid, i, mo["role"], mo["strong"], mo["hebrew"],
                            mo["gloss"], mo["submeaning"],
                        ))
                        per_file["morphemes"] += 1

                    for vinfo in w.variants:
                        sp = _extract_primary_strongs(vinfo.get("strongs"))
                        cur.execute(SQL["insert_variant"], (
                            wid, vinfo["kind"],
                            vinfo.get("text_original"),
                            vinfo.get("transliteration"),
                            vinfo.get("translation"),
                            vinfo.get("strongs"),
                            sp,
                            vinfo.get("grammar"),
                            vinfo.get("raw"),
                        ))
                        var_id = cur.lastrowid
                        per_file["variants"] += 1
                        eds = parse_edition_string(vinfo.get("edition_string") or "", w.language)
                        for code, minor in eds:
                            eid = EDITION_ID_BY_CODE_LANG.get((code, w.language))
                            if eid:
                                cur.execute(SQL["insert_variant_edition"], (var_id, eid, minor))
                else:
                    per_file["alt_strongs"] += len(w.alt_strongs)
                    per_file["morphemes"]   += len(w.morphemes)
                    per_file["variants"]    += len(w.variants)

            for w in verse.words:
                if not w.conjoin:
                    continue
                tgt_num = w.conjoin["target_word_num"]
                if not args.dry_run:
                    src_id = word_id_by_num.get((w.chunk_num, w.word_num))
                    # Conjoin targets reference a position within the same
                    # source block, so look up within the same chunk.
                    tgt_id = word_id_by_num.get((w.chunk_num, tgt_num))
                    if src_id is None:
                        continue
                    cur.execute(SQL["insert_word_link"], (
                        src_id, tgt_id, tgt_num,
                        w.conjoin.get("target_strong"),
                        w.conjoin["direction"],
                    ))
                per_file["links"] += 1

            if (not args.dry_run) and per_file["verses"] % 200 == 0:
                conn.commit()

        if not args.dry_run:
            conn.commit()

        for k, v in per_file.items():
            totals[k] = totals.get(k, 0) + v
        print(f"  -> verses={per_file['verses']:>6}  words={per_file['words']:>7}"
              f"  variants={per_file['variants']:>5}  morphemes={per_file['morphemes']:>6}"
              f"  links={per_file['links']:>6}  alt_strongs={per_file['alt_strongs']:>5}")

    # Backfill variant.position from word.position so the position-aware
    # rendering in db.php / diff_editions.py works correctly. STEPBible-
    # sourced variants all live at their canonical word's slot. Phase 3
    # additions (diff_editions.py) populate position themselves.
    # Safe to re-run: only touches rows whose position is still the DEFAULT.
    if not args.dry_run:
        print("\nBackfilling variant.position from word.position ...")
        cur.execute(
            "UPDATE variant v JOIN word w ON w.id = v.word_id "
            "   SET v.position = w.position "
            " WHERE v.position = 0"
        )
        conn.commit()
        print(f"  -> updated {cur.rowcount} variant row(s).")

    elapsed = time.time() - started
    print("\n=========================================")
    for k in ("verses", "words", "variants", "morphemes", "links", "alt_strongs"):
        print(f"  total {k:<11} {totals.get(k, 0)}")
    print(f"  elapsed: {elapsed:0.1f}s")
    if args.dry_run:
        print("  (dry-run -- no rows written)")
    print("=========================================")

    if conn:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
