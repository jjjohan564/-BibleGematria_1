#!/usr/bin/env python3
"""
build_edition_verse_text.py -- Phase 2 of the textual-variation pipeline.

Populates a new table:

    edition_verse_text (
      edition_id TINYINT UNSIGNED,
      verse_id   INT UNSIGNED,
      text_norm  VARCHAR(500),
      PRIMARY KEY (edition_id, verse_id)
    )

with one row per (NT edition, verse).  For each edition we walk the word
table in position order, filtering by word_edition.  If a word has a
variant whose variant_edition matches the target edition, that variant's
text_original is substituted in place of the base word's.

After the STEPBible-derived build, two rows are OVERWRITTEN per verse
using the authoritative external sources:

    edition='NA27'  <-  bible_na27.verseunicode
    edition='TR'    <-  bible_scr.verseunicode

(The user's design call: bible_scr is Scrivener's TR and should win when
it disagrees with STEPBible's TR-tagged words.)

The script is idempotent: it TRUNCATEs edition_verse_text on each run.

Run:  python build_edition_verse_text.py
      python build_edition_verse_text.py --config /path/to/config.ini
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path
from collections import defaultdict

# Single source of truth for config + connection (scripts/_db, no 'stepbible' defaults possible)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _db import load_config, get_connection  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# normalize_for_diff -- same logic as populate_verseunicode.py.  Duplicated
# here so this script stands alone without a shared module.
# ---------------------------------------------------------------------------

_DIA_STRIP  = re.compile('[\u0300-\u0344\u0346-\u036F]')
_WHITESPACE = re.compile(r'\s+')
_APOSTROPHES = 'ʼʹ'

def normalize_for_diff(text):
    """Strip diacritics (keep U+0345 iota subscript), strip punctuation,
    lowercase, collapse whitespace."""
    if not text:
        return ''
    t = (text.replace('Î', '').replace('Ð', '').replace('�', ''))
    t = unicodedata.normalize('NFD', t)
    t = _DIA_STRIP.sub('', t)
    t = unicodedata.normalize('NFC', t)
    t = t.lower()
    t = ''.join(c for c in t
                if not unicodedata.category(c).startswith('P')
                and c not in _APOSTROPHES)
    t = _WHITESPACE.sub(' ', t).strip()
    return t


# Strip "(Romanisation)" suffix from a Greek word stored as e.g.
# "Βίβλος (Biblos)".  Mirrors split_greek_word() in helpers.php.
_PAREN_TAIL = re.compile(r'\s*\([^)]*\)\s*$')

def strip_greek_parens(text):
    if not text:
        return ''
    return _PAREN_TAIL.sub('', text).strip()


# DB connection is delegated to import_bible.get_connection (the single source of truth).
# All connection logic is in scripts/_db (local connect + any stepbible default long gone).


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def ensure_schema(cur, conn):
    print("[1] Ensuring edition_verse_text table exists ...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS edition_verse_text (
            edition_id TINYINT UNSIGNED NOT NULL,
            verse_id   INT UNSIGNED     NOT NULL,
            text_norm  VARCHAR(500)     NOT NULL,
            PRIMARY KEY (edition_id, verse_id),
            KEY idx_verse (verse_id),
            CONSTRAINT fk_evt_edition FOREIGN KEY (edition_id) REFERENCES edition(id),
            CONSTRAINT fk_evt_verse   FOREIGN KEY (verse_id)   REFERENCES verse(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    conn.commit()
    cur.execute("TRUNCATE TABLE edition_verse_text")
    conn.commit()
    print("    Table ready (truncated).")


# ---------------------------------------------------------------------------
# Bulk fetch + build
# ---------------------------------------------------------------------------

def fetch_nt_data(cur):
    """One bulk fetch per data type for all NT verses.  Returns dicts indexed
    in a way that makes the per-verse assembly cheap."""
    print("\n[2] Bulk-fetching NT data ...")

    # NT editions (Greek language, edition code != Hebrew tags).
    cur.execute("""
        SELECT id, code, name
          FROM edition
         WHERE language='Greek'
         ORDER BY edition_order
    """)
    editions = cur.fetchall()
    ed_id_by_code = {r[1]: r[0] for r in editions}
    print(f"    {len(editions)} Greek editions: {[r[1] for r in editions]}")

    # All NT words.  book.testament='NT' filters to NT.
    cur.execute("""
        SELECT w.id, w.verse_id, w.position, w.text_original
          FROM word w
          JOIN book b ON b.id = w.book_id
         WHERE b.testament = 'NT'
         ORDER BY w.verse_id, w.position
    """)
    words = cur.fetchall()    # (word_id, verse_id, position, text_original)
    print(f"    {len(words):,} NT words")

    # Group words by verse_id, preserving position order.
    words_by_verse = defaultdict(list)
    for wid, vid, pos, txt in words:
        words_by_verse[vid].append((wid, pos, txt))

    # word_edition for NT words.
    cur.execute("""
        SELECT we.word_id, we.edition_id
          FROM word_edition we
          JOIN word w ON w.id = we.word_id
          JOIN book b ON b.id = w.book_id
         WHERE b.testament = 'NT'
    """)
    eds_by_word = defaultdict(set)
    for wid, eid in cur.fetchall():
        eds_by_word[wid].add(eid)
    print(f"    {sum(len(s) for s in eds_by_word.values()):,} word_edition pairs (NT)")

    # variants for NT words, plus their supporting editions.
    cur.execute("""
        SELECT v.id, v.word_id, v.text_original, v.kind
          FROM variant v
          JOIN word w ON w.id = v.word_id
          JOIN book b ON b.id = w.book_id
         WHERE b.testament = 'NT'
    """)
    variants = cur.fetchall()
    variant_text = {r[0]: r[2] for r in variants}
    variant_kind = {r[0]: r[3] for r in variants}
    variants_by_word = defaultdict(list)
    for vid, wid, _, _ in variants:
        variants_by_word[wid].append(vid)

    cur.execute("""
        SELECT ve.variant_id, ve.edition_id
          FROM variant_edition ve
          JOIN variant v ON v.id = ve.variant_id
          JOIN word    w ON w.id = v.word_id
          JOIN book    b ON b.id = w.book_id
         WHERE b.testament = 'NT'
    """)
    eds_by_variant = defaultdict(set)
    for vid, eid in cur.fetchall():
        eds_by_variant[vid].add(eid)
    print(f"    {len(variants):,} NT variants, "
          f"{sum(len(s) for s in eds_by_variant.values()):,} variant_edition pairs")

    return (editions, ed_id_by_code, words_by_verse,
            eds_by_word, variants_by_word, variant_text, variant_kind, eds_by_variant)


def assemble_per_edition(words_by_verse, eds_by_word, variants_by_word,
                         variant_text, variant_kind, eds_by_variant,
                         edition_id):
    """For ONE edition, yield (verse_id, text_norm) for every NT verse that
    has at least one word in that edition."""
    for verse_id, wlist in words_by_verse.items():
        pieces = []
        for wid, pos, base_text in wlist:
            # Skip words not in this edition.
            if edition_id not in eds_by_word.get(wid, ()):
                continue
            # Variant substitution: prefer a variant whose editions include
            # the target.  Skip 'omission' variants (those signal that
            # specific editions REMOVE the word, not replace it).
            chosen_text = base_text
            for vid in variants_by_word.get(wid, ()):
                if edition_id in eds_by_variant.get(vid, ()):
                    if variant_kind.get(vid) == 'omission':
                        chosen_text = None    # word omitted in this edition
                        break
                    if variant_text.get(vid):
                        chosen_text = variant_text[vid]
                        break
            if chosen_text is None:
                continue
            pieces.append(strip_greek_parens(chosen_text))
        if pieces:
            yield verse_id, normalize_for_diff(' '.join(pieces))


# ---------------------------------------------------------------------------
# External source overrides: bible_na27 -> NA27, bible_scr -> TR
# ---------------------------------------------------------------------------

def fetch_book_id_by_bw_book(cur):
    """bible_na27/bible_scr's Book column uses BW numbering 40-66 which
    equals book.book_order, not book.id.  Build the mapping."""
    cur.execute("SELECT book_order, id FROM book WHERE testament='NT'")
    return {int(bo): int(bid) for bo, bid in cur.fetchall()}


def fetch_verse_id_lookup(cur, book_ids):
    """Map (book_id, chapter, verse) -> verse_id for NT only."""
    cur.execute("""
        SELECT book_id, chapter, verse, id
          FROM verse
         WHERE book_id IN (%s)
    """ % ','.join(str(b) for b in book_ids))
    out = {}
    for bid, ch, vs, vid in cur.fetchall():
        out[(bid, ch, vs)] = vid
    return out


def overwrite_from_bw_table(cur, conn, bw_table, target_edition_id, label):
    print(f"\n[5] Overwriting {label} rows from {bw_table}.verseunicode ...")
    book_id_by_bw = fetch_book_id_by_bw_book(cur)
    verse_id_by_ref = fetch_verse_id_lookup(cur, list(book_id_by_bw.values()))

    cur.execute(f"""
        SELECT Book, Chapter, Verse, verseunicode
          FROM `{bw_table}`
         WHERE verseunicode IS NOT NULL AND verseunicode <> ''
    """)
    rows = cur.fetchall()

    batch = []
    skipped_book = 0
    skipped_verse = 0
    for bw_bk, ch, vs, txt in rows:
        bid = book_id_by_bw.get(int(bw_bk))
        if bid is None:
            skipped_book += 1
            continue
        verse_id = verse_id_by_ref.get((bid, int(ch), int(vs)))
        if verse_id is None:
            skipped_verse += 1
            continue
        batch.append((target_edition_id, verse_id, txt))

    cur.executemany("""
        REPLACE INTO edition_verse_text (edition_id, verse_id, text_norm)
        VALUES (%s, %s, %s)
    """, batch)
    conn.commit()
    print(f"    Wrote {len(batch):,} rows ({skipped_book} unknown books, "
          f"{skipped_verse} unmapped verses)")


# ---------------------------------------------------------------------------
# Spot checks
# ---------------------------------------------------------------------------

CHECKS = [
    ('John', 1, 1),     # classic
    ('John', 3, 16),    # popular
    ('Matt', 1, 1),
    ('Matt', 22, 32),   # has the U+FFFD bracket case in NA27
    ('Heb',  4, 12),    # has TR-only "absent" word te
    ('Rev', 22, 21),    # last NT verse
]

def run_checks(cur):
    print("\n[6] Spot-check ----------------------------------------------------")
    cur.execute("SELECT id, code FROM edition WHERE language='Greek' ORDER BY edition_order")
    ed_rows = cur.fetchall()
    ed_codes = [(r[0], r[1]) for r in ed_rows]

    for osis, ch, vs in CHECKS:
        cur.execute("""
            SELECT v.id FROM verse v JOIN book b ON b.id=v.book_id
             WHERE b.osis_code=%s AND v.chapter=%s AND v.verse=%s
        """, (osis, ch, vs))
        row = cur.fetchone()
        if not row:
            print(f"  {osis} {ch}:{vs}  (verse not found)")
            continue
        vid = row[0]
        print(f"  {osis} {ch}:{vs}  (verse_id={vid})")
        for eid, ecode in ed_codes:
            cur.execute("""
                SELECT text_norm FROM edition_verse_text
                 WHERE edition_id=%s AND verse_id=%s
            """, (eid, vid))
            r2 = cur.fetchone()
            txt = (r2[0] if r2 else '(no row)')
            print(f"    {ecode:<6}  {txt[:75]}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    project_root = Path(__file__).resolve().parent.parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default=str(project_root / 'config.ini'))
    args = ap.parse_args()
    cfg = load_config(args.config)
    print(f"Connecting to {cfg['user']}@{cfg['host']}:{cfg['port']}/{cfg['database']} ...")
    conn, driver = get_connection(cfg)
    cur = conn.cursor()

    ensure_schema(cur, conn)

    (editions, ed_id_by_code, words_by_verse,
     eds_by_word, variants_by_word, variant_text, variant_kind,
     eds_by_variant) = fetch_nt_data(cur)

    print("\n[3] Building per-edition normalized verse text ...")
    insert_sql = """
        REPLACE INTO edition_verse_text (edition_id, verse_id, text_norm)
        VALUES (%s, %s, %s)
    """
    for eid, ecode, ename in editions:
        batch = []
        for verse_id, text_norm in assemble_per_edition(
                words_by_verse, eds_by_word, variants_by_word,
                variant_text, variant_kind, eds_by_variant, eid):
            batch.append((eid, verse_id, text_norm))
        # Bulk insert in chunks
        if batch:
            chunk = 1000
            for start in range(0, len(batch), chunk):
                cur.executemany(insert_sql, batch[start:start+chunk])
            conn.commit()
        print(f"    {ecode:<6}  {len(batch):,} verses")

    # External-source overrides
    if 'NA27' in ed_id_by_code:
        overwrite_from_bw_table(cur, conn, 'bible_na27',
                                ed_id_by_code['NA27'], 'NA27')
    if 'TR' in ed_id_by_code:
        overwrite_from_bw_table(cur, conn, 'bible_scr',
                                ed_id_by_code['TR'], 'TR')

    run_checks(cur)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
