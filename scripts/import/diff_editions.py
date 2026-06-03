#!/usr/bin/env python3
"""
diff_editions.py — position-aware variant emission.

For NA27 and TR (Scrivener), tokenize each edition's normalized text from
edition_verse_text and align against the canonical word list for each NT
verse. Emit variants with explicit `position` values:

  spelling   — same slot, Levenshtein <= 2.         position = canonical.position
  omission   — canonical present, edition lacks.    position = canonical.position, text=''
  addition   — edition has an extra token.          position = anchor.position + 0.25/0.50/0.75
  replace big-Lev — split into omission + addition at the same canonical slot.

Dedupe rule (the key simplification over previous versions): a proposed
variant is suppressed if an existing variant at (word_id, position) already
has the same normalized text -- regardless of kind. STEPBible's existing
'meaning' variants for substantive substitutions are honored; we don't
re-add the same reading under a different kind. When the reading matches
but the edition isn't tagged yet, we add the edition tag.

Idempotent: re-running after a successful run produces no changes.

Run:  python diff_editions.py               # writes
      python diff_editions.py --dry-run     # analyze only
      python diff_editions.py --limit N     # first N verses only (debug)
      python diff_editions.py --config /path/to/config.ini
"""

import re
import sys
import argparse
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

# Single source of truth for config + connection (scripts/_db, no 'stepbible' defaults)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # scripts/ when inside import/
from _db import load_config, get_connection  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# Normalization — mirrors normalize_for_diff in populate_verseunicode.py
# ---------------------------------------------------------------------------

_DIA_STRIP   = re.compile('[\u0300-\u0344\u0346-\u036F]')
_WHITESPACE  = re.compile(r'\s+')
_APOSTROPHES = 'ʼʹ\u1FBD\u1FBF\u1FFE\u0384\u0385'   # modifier-letter apostrophes + Greek koronis/psili/dasia/tonos
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
                and c not in _APOSTROPHES)
    t = _WHITESPACE.sub(' ', t).strip()
    return t

def strip_greek_parens(text):
    if not text: return ''
    return _PAREN_TAIL.sub('', text).strip()


def levenshtein(a, b):
    if a == b: return 0
    la, lb = len(a), len(b)
    if la == 0: return lb
    if lb == 0: return la
    if la < lb:
        a, b = b, a; la, lb = lb, la
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * lb
        for j, cb in enumerate(b, 1):
            cur[j] = min(cur[j-1] + 1, prev[j] + 1, prev[j-1] + (0 if ca == cb else 1))
        prev = cur
    return prev[-1]


# DB connection is now provided exclusively by import_bible.get_connection
# (the _db module guarantees no stepbible fallback can ever return).


# ---------------------------------------------------------------------------
# Bulk fetch — everything in 4 queries
# ---------------------------------------------------------------------------

def fetch_inputs(cur):
    print("[1] Fetching inputs ...")
    cur.execute("SELECT id, code FROM edition WHERE code IN ('NA27','TR')")
    ed_id = {code: int(eid) for eid, code in cur.fetchall()}
    print(f"    NA27={ed_id['NA27']}, TR={ed_id['TR']}")

    # Canonical NT words: (word_id, verse_id, position, text_original)
    cur.execute("""
        SELECT w.id, w.verse_id, w.position, w.text_original
          FROM word w JOIN book b ON b.id = w.book_id
         WHERE b.testament = 'NT'
         ORDER BY w.verse_id, w.position
    """)
    rows = cur.fetchall()
    canonical_by_verse = defaultdict(list)
    for wid, vid, pos, raw in rows:
        norm = normalize_for_diff(strip_greek_parens(raw or ''))
        canonical_by_verse[int(vid)].append((int(wid), float(pos), norm))
    print(f"    {len(rows):,} NT canonical words across {len(canonical_by_verse):,} verses")

    # Existing variants for NT, keyed by (word_id, position) -> list of (id, normalized text)
    # Also collect (variant_id, edition_id) pairs for the dedupe check.
    cur.execute("""
        SELECT v.id, v.word_id, v.position, v.text_original
          FROM variant v
          JOIN word w ON w.id = v.word_id
          JOIN book b ON b.id = w.book_id
         WHERE b.testament = 'NT'
    """)
    existing_by_slot = defaultdict(list)  # (word_id, position) -> [(vid, norm_text), ...]
    variant_ids = []
    for vid, wid, pos, txt in cur.fetchall():
        key = (int(wid), round(float(pos), 2))
        existing_by_slot[key].append((int(vid), normalize_for_diff(txt or '')))
        variant_ids.append(int(vid))
    print(f"    {sum(len(v) for v in existing_by_slot.values()):,} existing NT variants")

    # variant_edition pairs (to detect when only the edition tag is missing)
    cur.execute("""
        SELECT ve.variant_id, ve.edition_id
          FROM variant_edition ve
          JOIN variant v ON v.id = ve.variant_id
          JOIN word w ON w.id = v.word_id
          JOIN book b ON b.id = w.book_id
         WHERE b.testament = 'NT'
    """)
    existing_ve = set((int(vid), int(eid)) for vid, eid in cur.fetchall())
    print(f"    {len(existing_ve):,} existing variant_edition pairs")

    # Edition text from edition_verse_text (already normalized)
    cur.execute(f"""
        SELECT edition_id, verse_id, text_norm
          FROM edition_verse_text
         WHERE edition_id IN ({ed_id['NA27']}, {ed_id['TR']})
    """)
    edition_text = {}
    for eid, vid, txt in cur.fetchall():
        edition_text[(int(eid), int(vid))] = txt
    print(f"    {len(edition_text):,} edition_verse_text rows (NA27+TR)")

    return ed_id, canonical_by_verse, existing_by_slot, existing_ve, edition_text


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

class DiffResult:
    def __init__(self):
        # (word_id, kind, position, text_norm) -> set of edition_ids
        self.new_variants = defaultdict(set)
        # existing variant_id -> set of edition_ids to add
        self.add_editions = defaultdict(set)
        self.stats = defaultdict(int)


def propose(result, existing_by_slot, existing_ve, word_id, position, kind,
            text_norm, edition_id):
    """Propose a variant. If an existing variant at (word_id, position) has
    the same normalized text (regardless of kind), suppress and only add the
    edition tag if missing. Otherwise queue a new variant."""
    key = (word_id, round(position, 2))
    for vid, ex_text in existing_by_slot.get(key, []):
        if ex_text == text_norm:
            if (vid, edition_id) not in existing_ve:
                result.add_editions[vid].add(edition_id)
                result.stats['edition_tag_added'] += 1
            else:
                result.stats['exact_dup_skipped'] += 1
            return
    new_key = (word_id, kind, round(position, 2), text_norm)
    result.new_variants[new_key].add(edition_id)
    result.stats[f'new_{kind}'] += 1


# ---------------------------------------------------------------------------
# Per-verse diff
# ---------------------------------------------------------------------------

def fractional_offset(k):
    """Map insertion index 0,1,2,... -> 0.25, 0.50, 0.75, 0.90, 0.91, ..."""
    if k < 3: return 0.25 * (k + 1)
    return min(0.99, 0.85 + 0.01 * (k - 2))


def diff_verse(verse_id, canonical, edition_text, edition_id,
               existing_by_slot, existing_ve, result):
    can_toks = [c[2] for c in canonical]
    can_wids = [c[0] for c in canonical]
    can_pos  = [c[1] for c in canonical]
    ed_toks  = (edition_text or '').split()

    sm = SequenceMatcher(a=can_toks, b=ed_toks, autojunk=False)

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue

        if tag == 'replace':
            la, lb = i2 - i1, j2 - j1
            if la == lb:
                # 1-to-1 substitutions
                for k in range(la):
                    can = can_toks[i1 + k]
                    edt = ed_toks[j1 + k]
                    if can == edt: continue
                    wid = can_wids[i1 + k]
                    pos = can_pos[i1 + k]
                    if levenshtein(can, edt) <= 2:
                        propose(result, existing_by_slot, existing_ve,
                                wid, pos, 'spelling', edt, edition_id)
                    else:
                        # Treat as omission of canonical + addition of edition word
                        # at the SAME integer position (the canonical slot).
                        propose(result, existing_by_slot, existing_ve,
                                wid, pos, 'omission', '', edition_id)
                        propose(result, existing_by_slot, existing_ve,
                                wid, pos, 'addition', edt, edition_id)
            else:
                # Length mismatch: all canonical omitted, edition tokens
                # added at fractional positions after the first canonical slot.
                for k in range(i1, i2):
                    propose(result, existing_by_slot, existing_ve,
                            can_wids[k], can_pos[k], 'omission', '', edition_id)
                # Anchor for additions
                anchor_wid = can_wids[i1] if i1 < len(can_wids) else can_wids[-1]
                anchor_pos = can_pos[i1]  if i1 < len(can_pos)  else can_pos[-1]
                for k in range(j1, j2):
                    pos = anchor_pos + fractional_offset(k - j1)
                    propose(result, existing_by_slot, existing_ve,
                            anchor_wid, pos, 'addition', ed_toks[k], edition_id)

        elif tag == 'delete':
            for k in range(i1, i2):
                propose(result, existing_by_slot, existing_ve,
                        can_wids[k], can_pos[k], 'omission', '', edition_id)

        elif tag == 'insert':
            # Anchor: the canonical word BEFORE the insertion point
            if i1 == 0:
                if not can_wids: continue
                anchor_wid = can_wids[0]
                anchor_pos = 0.0      # insertion at start of verse
            else:
                anchor_wid = can_wids[i1 - 1]
                anchor_pos = can_pos[i1 - 1]
            for k in range(j1, j2):
                pos = anchor_pos + fractional_offset(k - j1)
                propose(result, existing_by_slot, existing_ve,
                        anchor_wid, pos, 'addition', ed_toks[k], edition_id)


# ---------------------------------------------------------------------------
# Write phase
# ---------------------------------------------------------------------------

def write_results(cur, conn, result, dry_run):
    print()
    if dry_run:
        print("[Dry run — no writes]")
        return
    inserted_v, inserted_ve = 0, 0
    for (wid, kind, position, text), ed_ids in result.new_variants.items():
        cur.execute("""
            INSERT INTO variant (word_id, kind, position, text_original)
            VALUES (%s, %s, %s, %s)
        """, (wid, kind, position, text))
        new_vid = cur.lastrowid
        inserted_v += 1
        for eid in ed_ids:
            cur.execute("INSERT INTO variant_edition (variant_id, edition_id) VALUES (%s, %s)",
                        (new_vid, eid))
            inserted_ve += 1
    conn.commit()
    print(f"  Inserted {inserted_v:,} new variants, {inserted_ve:,} variant_edition rows")

    add_ve = 0
    for vid, ed_ids in result.add_editions.items():
        for eid in ed_ids:
            cur.execute("INSERT IGNORE INTO variant_edition (variant_id, edition_id) VALUES (%s, %s)",
                        (vid, eid))
            if cur.rowcount: add_ve += 1
    conn.commit()
    print(f"  Added {add_ve:,} edition tags to existing variants")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    project_root = Path(__file__).resolve().parent.parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--config', default=str(project_root / 'config.ini'))
    args = ap.parse_args()

    cfg = load_config(args.config)
    print(f"Connecting to {cfg['user']}@{cfg['host']}:{cfg['port']}/{cfg['database']} ...")
    conn, driver = get_connection(cfg)
    cur = conn.cursor()

    ed_id, canonical_by_verse, existing_by_slot, existing_ve, edition_text = fetch_inputs(cur)

    print("\n[2] Diffing verses ...")
    result = DiffResult()
    verse_ids = sorted(canonical_by_verse.keys())
    if args.limit: verse_ids = verse_ids[:args.limit]
    targets = [('NA27', ed_id['NA27']), ('TR', ed_id['TR'])]

    processed = 0
    for vid in verse_ids:
        canonical = canonical_by_verse[vid]
        for _code, eid in targets:
            txt = edition_text.get((eid, vid))
            if txt is None: continue
            diff_verse(vid, canonical, txt, eid,
                       existing_by_slot, existing_ve, result)
        processed += 1
        if processed % 1000 == 0:
            print(f"    {processed:,} / {len(verse_ids):,} verses processed")

    print(f"\n[3] Diff stats:")
    for k, v in sorted(result.stats.items()):
        print(f"    {k:<32}  {v:,}")

    spelling_counts = defaultdict(int)
    for (wid, kind, pos, text), eds in result.new_variants.items():
        if kind == 'spelling':
            spelling_counts[text] += 1
    top = sorted(spelling_counts.items(), key=lambda kv: -kv[1])[:20]
    if top:
        print(f"\n[4] Top 20 spelling variants:")
        for tok, n in top:
            print(f"    {tok:<24}  {n:>5}")

    write_results(cur, conn, result, args.dry_run)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
