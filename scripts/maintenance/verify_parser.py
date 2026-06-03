"""verify_parser.py (v2) -- stand-alone smoke test, no DB required."""
import sys
from collections import Counter
from pathlib import Path

# Add the import scripts directory to sys.path so we can import import_bible
# even when running this script directly from the maintenance folder.
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "scripts" / "import"))

import import_bible as ib


def collect_all(path, language):
    return list(ib.iter_verses_from_file(path, language))


def find_verse(verses, book_osis, chapter, verse):
    bid = ib.OSIS_TO_BOOK_ID[book_osis]
    for v in verses:
        if v.book_id == bid and v.chapter == chapter and v.verse == verse:
            return v
    return None


def show_word(w, indent="    "):
    print(f"{indent}#{w.word_num:02d}  src={w.source_type:<10}  orig={w.text_original!r}")
    print(f"{indent}     trans={w.translation!r}  strongs={w.strongs!r}  grammar={w.grammar!r}")
    if w.base_editions:
        print(f"{indent}     base_editions: {[c for c, _ in w.base_editions]}")
    if w.alt_strongs:
        print(f"{indent}     alt_strongs:   {w.alt_strongs}")
    if w.conjoin:
        print(f"{indent}     conjoin -> #{w.conjoin['target_word_num']:02d} "
              f"({w.conjoin['direction']}, target_strong={w.conjoin['target_strong']})")
    if w.morphemes:
        print(f"{indent}     morphemes ({len(w.morphemes)}):")
        for i, m in enumerate(w.morphemes, 1):
            extra = f"  sub={m['submeaning']!r}" if m["submeaning"] else ""
            print(f"{indent}       {i}. {m['role']:<11} {m['strong']:<8} "
                  f"hebrew={m['hebrew']!r}  gloss={m['gloss']!r}{extra}")
    if w.variants:
        print(f"{indent}     variants ({len(w.variants)}):")
        for v in w.variants:
            print(f"{indent}       - kind={v['kind']:<8} text={v.get('text_original')!r} "
                  f"trans={v.get('translation')!r}")
            print(f"{indent}         strongs={v.get('strongs')!r} grammar={v.get('grammar')!r} "
                  f"editions={v.get('edition_string')!r}")
            raw = v.get('raw') or ""
            print(f"{indent}         raw: {raw[:140]!r}")


def show_verse(verses, book, chap, verse, label, words_filter=None):
    v = find_verse(verses, book, chap, verse)
    print(f"\n========== {label}  ({book} {chap}:{verse}) ==========")
    if v is None:
        print("  (not found)")
        return
    print(f"  raw_ref          : {v.raw_ref}")
    print(f"  word_count       : {v.word_count}")
    print(f"  text_original    : {' '.join(v.originals)[:200]}")
    print(f"  text_english     : {' '.join(v.englishes)[:200]}")
    print(f"  summary blocks   : {len(v.summaries)}")
    sig_blocks = [s for s in v.summaries if s.sig_variant]
    print(f"  has sig variant  : {bool(sig_blocks)}")
    for s in sig_blocks:
        sigtxt = s.sig_variant or ""
        print(f"      block#{s.block_num} sig: {sigtxt[:160]}")
    selected = v.words if not words_filter else [w for w in v.words if w.word_num in words_filter]
    print(f"  selected words   : {[w.word_num for w in selected]}")
    for w in selected:
        show_word(w)


def main():
    # Project root is two levels up from this script (scripts/maintenance/ -> scripts/ -> root)
    project_root = Path(__file__).resolve().parent.parent.parent
    raw_dir = project_root / "data" / "raw"

    print("Loading TAHOT Gen-Deu ...")
    heb_gen = collect_all(next(iter(raw_dir.glob("TAHOT Gen-Deu*.txt"))), "Hebrew")
    print(f"  -> {len(heb_gen)} verses")
    print("Loading TAGNT Mat-Jhn ...")
    grk_mat = collect_all(next(iter(raw_dir.glob("TAGNT Mat-Jhn*.txt"))), "Greek")
    print(f"  -> {len(grk_mat)} verses")

    var_kinds = Counter()
    ed_usage  = Counter()
    morph_roles = Counter()
    has_sig_count = 0
    sig_marked_words = 0
    for src in (heb_gen, grk_mat):
        for v in src:
            sig_in_summary = any(s.sig_variant for s in v.summaries)
            sig_in_words = any(w.is_variant_marked for w in v.words)
            if sig_in_summary or sig_in_words:
                has_sig_count += 1
            for w in v.words:
                if w.is_variant_marked:
                    sig_marked_words += 1
                for code, _ in w.base_editions:
                    ed_usage[code] += 1
                for var in w.variants:
                    var_kinds[var["kind"]] += 1
                for m in w.morphemes:
                    morph_roles[m["role"]] += 1

    print("\n----- Aggregate stats (Gen-Deu + Mat-Jhn) -----")
    print(f"  verses with significant variant: {has_sig_count}")
    print(f"  words with uppercase-bracket variant marker: {sig_marked_words}")
    print(f"  variant kinds: {dict(var_kinds)}")
    print(f"  morpheme roles: {dict(morph_roles)}")
    print(f"  top edition usages: {ed_usage.most_common(12)}")

    show_verse(heb_gen, "Gen", 1, 1,  "Genesis 1:1")
    show_verse(heb_gen, "Deu", 6, 4,  "Shema (Deuteronomy 6:4)")
    show_verse(heb_gen, "Gen", 9, 21, "Gen 9:21 (Q(K) variant @ #07)", words_filter={7})
    show_verse(heb_gen, "Gen", 14, 17, "Gen 14:17 LBH(A) variant @ #09", words_filter={9})
    show_verse(grk_mat, "Mat", 1, 1,  "Mat 1:1")
    show_verse(grk_mat, "Jhn", 1, 1,  "John 1:1")
    show_verse(grk_mat, "Jhn", 3, 16, "John 3:16")
    show_verse(grk_mat, "Mat", 5, 32, "Mat 5:32 (meaning variant @ #17)", words_filter={17})
    show_verse(grk_mat, "Mat", 1, 5,  "Mat 1:5 (spelling variant @ #5)", words_filter={5, 13, 17})
    show_verse(grk_mat, "Mat", 1, 25, "Mat 1:25 (omission variant @ #10-#12)", words_filter={10, 11, 12})


if __name__ == "__main__":
    main()
