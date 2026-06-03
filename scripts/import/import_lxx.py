#!/usr/bin/env python3
"""
import_lxx.py
=============

Loads the Rahlfs-1935 LXX from `eliranwong/LXX-Rahlfs-1935` into the
LXX-specific tables (book_lxx, verse_lxx, word_lxx). DB name comes exclusively from
lxx_schema.sql), verse_lxx, and word_lxx.

The shared book / verse / word tables are NEVER touched.

Source layout (relative to the LXX repo root):
    01_wordlist_unicode/text_accented.csv                 — accented Greek (per word)
    01_wordlist_unicode/alignment_with_OSSP/E-verse.csv   — verse boundary markers
    02_lexemes/OSSP_lexemes.csv                           — lemma
    03b_descriptions_on_morphology_codes/morphology_623693_with_description.csv
    04_SBL_transliteration/final_transliteration_SBL.csv
    05_pronunciation/final_pronunciation_modern_Greek.csv
    06_English_gloss/beta.csv
    07_StrongNumber/final_Strongs.csv

All seven per-word files are line-aligned (623,693 rows each) — row N
across all files refers to the same Greek word. The verse boundary
file (30,637 rows) marks the row index where each verse begins.

Idempotent: each run does `DELETE FROM word_lxx; DELETE FROM verse_lxx`
before loading. book_lxx is seeded by lxx_schema.sql and not touched here.

Usage:
    mysql -u root -p stepbible < lxx_schema.sql
    pip install mariadb        # or pymysql
    python import_lxx.py [--lxx-root PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

# Shared DB (single source of truth). Insert scripts/ dir for direct runs.
_scripts_dir = Path(__file__).resolve().parent.parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))
from _db import load_config, get_connection, connect  # type: ignore[import-not-found]

# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------

# Map from Rahlfs book code (as it appears in E-verse.csv) to book_lxx
# osis_code (seeded in lxx_schema.sql).
RAHLFS_TO_OSIS: Dict[str, str] = {
    "Gen":     "LxxGen",
    "Exod":    "LxxExod",
    "Lev":     "LxxLev",
    "Num":     "LxxNum",
    "Deut":    "LxxDeut",
    "JoshB":   "LxxJoshB",
    "JoshA":   "LxxJoshA",
    "JudgB":   "LxxJudgB",
    "JudgA":   "LxxJudgA",
    "Ruth":    "LxxRuth",
    "1Sam/K":  "Lxx1Kdm",
    "2Sam/K":  "Lxx2Kdm",
    "1/3Kgs":  "Lxx3Kdm",
    "2/4Kgs":  "Lxx4Kdm",
    "1Chr":    "Lxx1Chr",
    "2Chr":    "Lxx2Chr",
    "2Esdr":   "Lxx2Esd",
    "Esth":    "LxxEsth",
    "Job":     "LxxJob",
    "Ps":      "LxxPs",
    "Prov":    "LxxProv",
    "Qoh":     "LxxQoh",
    "Cant":    "LxxCant",
    "Isa":     "LxxIsa",
    "Jer":     "LxxJer",
    "Lam":     "LxxLam",
    "Ezek":    "LxxEzek",
    "Dan":     "LxxDan",
    "DanTh":   "LxxDanTh",
    "Hos":     "LxxHos",
    "Joel":    "LxxJoel",
    "Amos":    "LxxAmos",
    "Obad":    "LxxObad",
    "Jonah":   "LxxJonah",
    "Mic":     "LxxMic",
    "Nah":     "LxxNah",
    "Hab":     "LxxHab",
    "Zeph":    "LxxZeph",
    "Hag":     "LxxHag",
    "Zech":    "LxxZech",
    "Mal":     "LxxMal",
    "TobBA":   "LxxTobBA",
    "TobS":    "LxxTobS",
    "Jdt":     "LxxJdt",
    "1Esdr":   "Lxx1Esd",
    "1Mac":    "Lxx1Mac",
    "2Mac":    "Lxx2Mac",
    "3Mac":    "Lxx3Mac",
    "4Mac":    "Lxx4Mac",
    "Wis":     "LxxWis",
    "Sir":     "LxxSir",
    "Bar":     "LxxBar",
    "EpJer":   "LxxEpJer",
    "Od":      "LxxOdes",
    "PsSol":   "LxxPsSol",
    "Sus":     "LxxSus",
    "SusTh":   "LxxSusTh",
    "Bel":     "LxxBel",
    "BelTh":   "LxxBelTh",
}

# Regex for the verse ref part of E-verse.csv (the third column).
# Examples:  「Gen 1:1」   「Ps 9:1」   「Esth 1:1a」   「Od 」
VERSE_RE = re.compile(
    r"""^「
        (?P<book>[0-9A-Za-z][0-9A-Za-z/]*)\s*
        (?:(?P<chap>\d+):(?P<verse>\d+)(?P<sub>[a-z]?))?
        」$""",
    re.VERBOSE,
)


# ---------------------------------------------------------------------
# File readers
# ---------------------------------------------------------------------

def read_tsv_col2(path: Path) -> List[str]:
    """Read a 2-column TSV (`<row_num>\\t<value>`) and return the value
    column as a list, 0-indexed."""
    out: List[str] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            if not line:
                out.append("")
                continue
            parts = line.split("\t")
            out.append(parts[1] if len(parts) >= 2 else "")
    return out


def read_tsv_col3(path: Path) -> List[str]:
    """Read a 3-column TSV (`<row_num>\\t<row_num>\\t<value>`) and return
    the value column as a list, 0-indexed."""
    out: List[str] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            if not line:
                out.append("")
                continue
            parts = line.split("\t")
            out.append(parts[2] if len(parts) >= 3 else "")
    return out


def read_morph_with_description(path: Path) -> Tuple[List[str], List[str]]:
    """Read morphology_623693_with_description.csv
    (`<row>\\t<code>\\t<pos>\\t<parse>`) and return (codes, descriptions).
    Description = "pos, parse" or just "pos" if parse is empty."""
    codes: List[str] = []
    descs: List[str] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            if not line:
                codes.append("")
                descs.append("")
                continue
            parts = line.split("\t")
            code = parts[1] if len(parts) >= 2 else ""
            pos = parts[2] if len(parts) >= 3 else ""
            parse = parts[3] if len(parts) >= 4 else ""
            codes.append(code)
            if parse:
                descs.append(f"{pos}, {parse}".strip().rstrip(","))
            else:
                descs.append(pos)
    return codes, descs


def read_verse_boundaries(path: Path) -> List[Tuple[int, str]]:
    """Read E-verse.csv. Returns list of (start_row_1based, raw_ref_string)
    tuples sorted by row."""
    out: List[Tuple[int, str]] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            try:
                row = int(parts[0])
            except ValueError:
                continue
            ref = parts[2].strip()
            out.append((row, ref))
    out.sort(key=lambda t: t[0])
    return out


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def parse_ref(raw: str) -> Optional[Tuple[str, int, int, str]]:
    """Parse a 「Book Chap:Verse[sub]」 string into (book_code, chap, verse, sub).
    Returns None for malformed refs (e.g. bare "「Od 」")."""
    m = VERSE_RE.match(raw)
    if not m:
        return None
    book = m.group("book")
    chap = m.group("chap")
    verse = m.group("verse")
    sub = m.group("sub") or ""
    if chap is None or verse is None:
        return None
    return (book, int(chap), int(verse), sub)


def normalize_gloss(g: str) -> str:
    """Source glosses use `;<br>` to separate senses. Convert to ' / ' for
    display, strip extra whitespace, cap length."""
    if not g:
        return ""
    out = g.replace(";<br>", " / ").replace("<br>", " / ")
    out = re.sub(r"\s+", " ", out).strip()
    return out[:250]


def strongs_primary(s: str) -> Optional[str]:
    """Pick the first G####-style token from a Strong's field."""
    if not s:
        return None
    m = re.search(r"G\d{1,5}", s)
    return m.group(0) if m else None


def chunk(iterable, n: int) -> Iterator[list]:
    buf: list = []
    for x in iterable:
        buf.append(x)
        if len(buf) >= n:
            yield buf
            buf = []
    if buf:
        yield buf


# ---------------------------------------------------------------------
# Main load
# ---------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lxx-root", default=None,
                    help="Path to cloned LXX-Rahlfs-1935 repo (required for this script)")

    project_root = Path(__file__).resolve().parent.parent.parent
    ap.add_argument("--config", default=str(project_root / "config.ini"))
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse and validate; do not write to DB.")
    args = ap.parse_args()

    root = Path(args.lxx_root)
    if not root.is_dir():
        print(f"ERROR: --lxx-root not found: {root}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading LXX data from: {root}")
    t0 = time.time()

    accented = read_tsv_col3(root / "01_wordlist_unicode" / "text_accented.csv")
    lemma    = read_tsv_col2(root / "02_lexemes" / "OSSP_lexemes.csv")
    morph_codes, morph_descs = read_morph_with_description(
        root / "03b_descriptions_on_morphology_codes" / "morphology_623693_with_description.csv"
    )
    translit = read_tsv_col2(root / "04_SBL_transliteration" / "final_transliteration_SBL.csv")
    pron     = read_tsv_col2(root / "05_pronunciation" / "final_pronunciation_modern_Greek.csv")
    gloss    = read_tsv_col2(root / "06_English_gloss" / "beta.csv")
    strongs  = read_tsv_col2(root / "07_StrongNumber" / "final_Strongs.csv")
    boundaries = read_verse_boundaries(
        root / "01_wordlist_unicode" / "alignment_with_OSSP" / "E-verse.csv"
    )

    n = len(accented)
    print(f"  accented:    {len(accented):>7d} words")
    print(f"  lemma:       {len(lemma):>7d}")
    print(f"  morph:       {len(morph_codes):>7d}")
    print(f"  translit:    {len(translit):>7d}")
    print(f"  pronunc:     {len(pron):>7d}")
    print(f"  gloss:       {len(gloss):>7d}")
    print(f"  strongs:     {len(strongs):>7d}")
    print(f"  boundaries:  {len(boundaries):>7d} verses")
    assert all(len(x) == n for x in (lemma, morph_codes, morph_descs,
                                      translit, pron, gloss, strongs)), \
        "Per-word file row counts disagree — won't proceed."

    # Build verse ranges:  (start_row_1based, end_row_1based, book_code, chap, verse, sub, raw_ref)
    ranges = []
    skipped_titles = 0
    for i, (start, raw) in enumerate(boundaries):
        end = (boundaries[i + 1][0] - 1) if i + 1 < len(boundaries) else n
        parsed = parse_ref(raw)
        if parsed is None:
            # Malformed header (e.g. "「Od 」"). Merge into previous verse.
            skipped_titles += 1
            if ranges:
                prev = ranges[-1]
                ranges[-1] = (prev[0], end, prev[2], prev[3], prev[4], prev[5], prev[6])
            continue
        book, chap, verse, sub = parsed
        ranges.append((start, end, book, chap, verse, sub, raw.strip("「」")))

    if skipped_titles:
        print(f"  (merged {skipped_titles} title rows into adjacent verses)")
    print(f"  ranges:      {len(ranges):>7d} verses")
    print(f"Files read in {time.time() - t0:.1f}s")

    # Check for unknown book codes
    by_book: Dict[str, int] = {}
    for r in ranges:
        by_book[r[2]] = by_book.get(r[2], 0) + 1
    unknown = sorted(k for k in by_book if k not in RAHLFS_TO_OSIS)
    if unknown:
        print(f"WARNING: unknown Rahlfs codes: {unknown}")

    if args.dry_run:
        print("\n-- Dry-run summary --")
        for code in sorted(by_book.keys()):
            osis = RAHLFS_TO_OSIS.get(code, "??")
            print(f"  {code:8s} -> {osis:10s}  {by_book[code]:>5d} verses")
        return

    # DB connect (uses shared _db.connect for banner + live SELECT DATABASE() verification)
    cfg_path = Path(args.config) if args.config else None
    if cfg_path and not cfg_path.is_absolute():
        cfg_path = Path(__file__).parent / cfg_path
    conn, cur, cfg = connect(cfg_path)  # also prints + verifies DB name

    # Resolve book ids from book_lxx (seeded by lxx_schema.sql)
    cur.execute("SELECT id, osis_code FROM book_lxx")
    book_id_by_osis: Dict[str, int] = {r[1]: int(r[0]) for r in cur.fetchall()}
    missing = [v for v in RAHLFS_TO_OSIS.values() if v not in book_id_by_osis]
    if missing:
        print(f"ERROR: book_lxx rows missing: {missing}", file=sys.stderr)
        print("       Run lxx_schema.sql first.", file=sys.stderr)
        sys.exit(2)
    print(f"  {len(book_id_by_osis)} LXX books in book_lxx")

    # Purge previous LXX data so re-runs are clean.
    print("Purging existing verse_lxx / word_lxx ...")
    cur.execute("DELETE FROM word_lxx")
    del_w = cur.rowcount
    cur.execute("DELETE FROM verse_lxx")
    del_v = cur.rowcount
    cur.execute("ALTER TABLE verse_lxx AUTO_INCREMENT = 1")
    cur.execute("ALTER TABLE word_lxx  AUTO_INCREMENT = 1")
    conn.commit()
    print(f"  deleted {del_w} words, {del_v} verses")

    # Load verses
    print("\nInserting verses ...")
    t1 = time.time()
    inserted_verses = 0

    INSERT_VERSE = """
        INSERT INTO verse_lxx
            (book_id, chapter, verse, subverse,
             osis_ref, raw_ref,
             text_original, text_english, word_count)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    for batch in chunk(ranges, 1000):
        params = []
        for (start, end, book, chap, verse, sub, raw_ref) in batch:
            osis = RAHLFS_TO_OSIS[book]
            bid = book_id_by_osis[osis]
            words_text  = [accented[i - 1] for i in range(start, end + 1)]
            words_gloss = [normalize_gloss(gloss[i - 1]) for i in range(start, end + 1)]
            text_original = " ".join(w for w in words_text if w)
            text_english  = " ".join(w for w in words_gloss if w)
            word_count = end - start + 1
            osis_ref = f"{osis}.{chap}.{verse}" + (sub if sub else "")
            params.append((
                bid, chap, verse, sub, osis_ref, raw_ref,
                text_original[:65000], text_english[:65000], word_count,
            ))
        cur.executemany(INSERT_VERSE, params)
        inserted_verses += len(params)

    conn.commit()
    print(f"  inserted {inserted_verses} verses in {time.time() - t1:.1f}s")

    # Pull back verse ids so we can attach words.
    print("Pulling back verse ids ...")
    cur.execute("SELECT id, book_id, chapter, verse, subverse FROM verse_lxx")
    verse_id_lookup: Dict[Tuple[int, int, int, str], int] = {}
    for r in cur.fetchall():
        verse_id_lookup[(int(r[1]), int(r[2]), int(r[3]), r[4] or "")] = int(r[0])
    print(f"  {len(verse_id_lookup)} verse rows")

    # Load words
    print("Inserting words ...")
    t2 = time.time()

    INSERT_WORD = """
        INSERT INTO word_lxx
            (verse_id, book_id, chapter, verse, position,
             text_original, transliteration, translation,
             strongs, strongs_primary,
             grammar, grammar_desc, lemma, dictionary_form, pronunciation)
        VALUES (%s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s, %s)
    """

    inserted_words = 0
    for (start, end, book, chap, verse, sub, raw_ref) in ranges:
        osis = RAHLFS_TO_OSIS[book]
        bid = book_id_by_osis[osis]
        vid = verse_id_lookup.get((bid, chap, verse, sub))
        if vid is None:
            print(f"  WARN: verse not found for {raw_ref}; skipping {end - start + 1} words")
            continue
        params = []
        for pos_idx, src_row in enumerate(range(start, end + 1), start=1):
            r = src_row - 1  # 0-based
            text = accented[r]
            translit_s = translit[r]
            gloss_s = normalize_gloss(gloss[r])
            strongs_s = strongs[r]
            sp = strongs_primary(strongs_s)
            morph_c = morph_codes[r]
            morph_d = morph_descs[r]
            lemma_s = lemma[r]
            pron_s = pron[r]
            dict_form = f"{lemma_s}={gloss_s}" if lemma_s else (gloss_s or "")
            params.append((
                vid, bid, chap, verse, pos_idx,
                text[:250] if text else None,
                translit_s[:250] if translit_s else None,
                gloss_s[:250] if gloss_s else None,
                strongs_s[:30] if strongs_s else None,
                sp,
                morph_c[:60] if morph_c else None,
                morph_d[:125] if morph_d else None,
                lemma_s[:125] if lemma_s else None,
                dict_form[:250] if dict_form else None,
                pron_s[:125] if pron_s else None,
            ))
        cur.executemany(INSERT_WORD, params)
        inserted_words += len(params)

        if inserted_words % 50000 < 1000:
            elapsed = time.time() - t2
            rate = inserted_words / elapsed if elapsed > 0 else 0
            print(f"  {inserted_words:>7d} words in {elapsed:5.1f}s "
                  f"({rate:,.0f} w/s)")

    conn.commit()
    print(f"  inserted {inserted_words} words in {time.time() - t2:.1f}s")

    cur.close()
    conn.close()

    print(f"\nTotal elapsed: {time.time() - t0:.1f}s")
    print("LXX import complete.")


if __name__ == "__main__":
    main()
