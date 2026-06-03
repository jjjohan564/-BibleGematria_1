# Project handoff — Bible Database

**Read this first** if you're a Claude (or human) picking up this project mid-stream.
Everything in this file captures decisions, rationale, conventions, and pending
work that isn't already obvious from the code itself.

---

## 1. What this project is

Richard is building a local searchable Bible database from the **STEPBible.org**
tagged Hebrew OT + Greek NT files (CC BY 4.0), augmented with the **BibleWorks**
NA27 and Scrivener (TR) Greek NT texts. Data is loaded into a local **MariaDB**
instance and rendered through a **PHP web interface** in `web/`. Windows 11 +
local web server at `http://localhost/stepbible/`. Database name: **`stepbible`**.

The web UI is an interlinear browser with an **Edition dropdown** (currently
NA28 and TR) that lets the user view any NT verse as it reads in either
textual tradition.

---

## 2. File map

```
Bible Database/
├── HANDOFF.md                    ← THIS file. Always update when conventions change.
├── README.md                     ← user-facing setup docs for the import side
├── schema.sql                    ← v2 DDL (re-runnable; 11 tables + view)
├── gematria_schema.sql           ← adds gematria_word + gematria_verse tables
├── import_bible.py               ← TAHOT/TAGNT parser + bulk loader
├── compute_gematria.py           ← computes & loads gematria values
├── import_bw_bibles.py           ← imports NA27 & Scrivener from BibleWorks DB
├── verify_parser.py              ← stand-alone smoke test (no DB)
├── populate_verseunicode.py      ← Phase 1: BW transliteration → normalized Greek
├── build_edition_verse_text.py   ← Phase 2: builds edition_verse_text workbench
├── diff_editions.py              ← Phase 3: position-aware variant emission
├── cleanup_stale_variants.py     ← one-off: removes elision-noise variants
├── add_text_search.py            ← FULLTEXT helper (older work)
├── add_verse_search.py           ← FULLTEXT helper (older work)
├── find_strongs_equiv.py         ← diagnostic: compares KJV <NNNN> tags with TAGNT strongs_primary/alt to find systematic code discrepancies (see § 14 session 4)
├── strongs_equiv_report.txt      ← saved output of find_strongs_equiv.py (not in repo; regenerate with: python find_strongs_equiv.py)
├── config.ini                    ← user's local DB creds (NOT in repo)
├── config.ini.example            ← template
├── TAHOT *.txt  (×4)             ← Hebrew OT source files
├── TAGNT *.txt  (×2)             ← Greek NT source files
└── web/
    ├── README.md
    ├── index.php                 ← main page — PHP routing, data fetch, HTML template
    ├── helpers.php               ← PHP helper functions
    ├── db.php                    ← PDO + position-merge query logic
    ├── style.css                 ← biblehub-style CSS + custom properties
    ├── config.php                ← user's web-side DB creds (NOT in repo)
    ├── config.sample.php         ← template
    └── js/
        ├── options.js            ← gear button, display checkboxes, font-size controls
        ├── gematria.js           ← gematria panel (sum, prime factorization)
        ├── word-selection.js     ← click/shift-mousemove word cell selection
        ├── variant-switcher.js   ← variant cycling + page-load gematria sync
        ├── dropdowns.js          ← chained book/chapter/verse + auto-submit edition
        ├── search-trigger.js     ← search UI hook (verse-ref nav, strongs, phrase, gematria)
        ├── strongs-tooltip.js    ← Strong's hover tooltip + click-to-search for word cells
        ├── verse-tooltip.js      ← KJV verse-preview on hover of search-result verse links
        └── grammar-tooltip.js    ← grammar tag expansion tooltip (Greek + Hebrew)
```

### Why the JS is split

`index.php` grew past 900 lines and the Edit tool became unreliable at that
size. Each JS file is now small enough to edit safely. **Do not inline these
back into index.php.** If any file approaches 400-500 lines, split it again.

---

## 3. Database schema — what changed in this session

The original v2 schema is in `schema.sql`. **One column was added during this
session** (already in the live DB; not in `schema.sql`):

```sql
ALTER TABLE variant ADD COLUMN position DECIMAL(6,2) NOT NULL DEFAULT 0;
CREATE INDEX idx_variant_position ON variant(word_id, position);
```

### Tables

| Table             | One row per…                                           |
|-------------------|--------------------------------------------------------|
| `book`            | canonical book (66 rows, OT 1-39 + NT 40-66)           |
| `edition`         | named manuscript edition / source (24 rows)            |
| `verse`           | Bible verse, with assembled original + English text    |
| `verse_summary`   | verbatim `#_Translation` / `#_Word=Grammar` block      |
| `word`            | canonical printed word (position is SMALLINT)          |
| `word_edition`    | (word, edition) pair                                   |
| `variant`         | textual variant — **now has `position DECIMAL(6,2)`** |
| `variant_edition` | (variant, edition) pair                                |
| `word_morpheme`   | Hebrew prefix / root / suffix / punctuation morpheme   |
| `word_link`       | grammatical "conjoin" arrow between two words          |
| `word_alt_strong` | alternate Strong's tag                                 |
| `gematria_word`   | precomputed std/sofit/ordinal/reduced for each word    |
| `gematria_verse`  | precomputed totals per verse                           |
| `bible_na27`      | NA27 from BibleWorks (Verse_Text + verseunicode)       |
| `bible_scr`       | Scrivener TR from BibleWorks                           |
| `bible_kjv`       | KJV English with inline `<NNNN>` Strong's tags (§ 13)  |
| `edition_verse_text` | normalized per-edition verse text — **TO BE DROPPED** (Phase 3 workbench) |

### The variant.position convention (KEY MENTAL MODEL)

Every variant carries an explicit `position` value. This is the **single most
important thing to internalize**:

- **Substitutions** (`spelling`, `meaning`) → `variant.position = canonical_word.position` (an integer like 5.00). The variant replaces the canonical at that slot.
- **Omissions** (`omission`) → `variant.position = canonical_word.position`, `text_original=''`. The slot is dropped.
- **Additions** (`addition`) → `variant.position = anchor_word.position + offset` where offset is 0.25 / 0.50 / 0.75 (multiple inserts allowed in the same gap). The variant inserts as its own slot.

Approximate row counts after the full pipeline:
```
verses:           31,219
words:           447,748
word_edition  : ~3M
variants      :  ~23,455   (12,088 STEPBible-original + ~11,367 Phase 3)
morphemes     :  540,467
links         :   41,049
alt_strongs   :   23,646
```

---

## 4. Edition-aware rendering architecture (web/db.php)

This is the heart of the UI. Spend two minutes here before touching `db.php`.

### The flow

1. **`bible_verse_full($osis, $chapter, $verse, $edition_code)`** loads a verse + book row, picks an edition_id if the verse is Greek (Hebrew ignores edition), then calls `bible_assemble_words()`.
2. **`bible_assemble_words()`** does the position-merge:
   - SELECT canonical words for the verse where `word_edition` includes the chosen edition.
   - SELECT variants for the verse where `variant_edition` includes the chosen edition.
   - Build a **position-keyed slot map** with `sprintf('%.2f', $position)` as the key (this is critical — `word.position` is SMALLINT and `variant.position` is DECIMAL(6,2); raw casts produce mismatching keys like `'5'` vs `'5.00'`).
   - Per slot:
     - Both canonical word and variant present → variant substitutes (text/translit/translation/strongs/grammar layered onto the canonical row). The canonical fields are preserved as `$w['canonical_text_original']`, `$w['canonical_transliteration']`, etc. so the JS payload can cycle back to base.
     - Only canonical → render canonical.
     - Only variant (canonical exists but isn't tagged for this edition, e.g. John 1:18 θεός case where canonical θεός is NA-only and variant υἱός is tagged for TR) → render the variant as a word-shaped row via `bible_variant_as_word_row()`. This row has `id = -variant_id` to mark it synthetic.
     - `'omission'` kind → skip the slot entirely.
   - Result is sorted ascending by numeric position.
3. **`bible_attach_per_word_data()`** attaches `editions`, `alts`, `morphemes`, `links`, `variants`, and gematria to each row. Synthetic rows (negative id) get empty attached arrays.

### Variant cycling (variant-switcher.js)

The variant-indicator bar on each cell lets the user cycle between the canonical reading and any variant attached to that word. After edition substitution:

- `data-active-variant` on the cell tells JS which variant index is *currently displayed* — or `'base'` if the canonical is shown. The PHP template computes this by matching `$w['source_variant_id']` against the variant index in `$w['variants']`.
- Clicking the bar advances `current → next` (base → 0 → 1 → … → base), using the canonical fields from the JS payload's `d.original` for the 'base' state.
- All three gematria values (Standard, Ordinal, Reduced) are recomputed from the displayed text on cycle.

### Gematria-on-load (variant-switcher.js → `syncGematriaOnLoad`)

The precomputed `gematria_word` columns are correct for canonical text; when an edition substitutes the slot, the precomputed values are stale. On page load, `syncGematriaOnLoad()` walks every word cell and **always** recomputes `data-gem-std/ord/red` from the displayed text. Calls both `_updateGematria()` (per-cell display) and `_gemRebuild()` (verse total panel).

Gematria maps live in `variant-switcher.js`:
- `HEB_STD/ORD/RED` — Hebrew (sofit treated as base value for standard; ordinal gives finals 23-27)
- `GRK_STD` — Greek isopsephy (ζ=7, σ/ς both 200)
- `GRK_ORD` — Modern 24-letter ordinal (ζ=6, σ/ς both 18)
- **Iota subscript (U+0345) is counted as iota** (ι=10 for standard, 9 for ordinal). The regex in `grkClean()` strips `[U+0300-U+0344, U+0346-U+036F]` — note the deliberate gap that keeps U+0345.

---

## 5. STEPBible's tagging conventions (DISCOVERED THE HARD WAY)

These conventions weren't documented anywhere obvious. Internalize them:

### word_edition tags only editions where THAT EXACT word appears

A word like John 1:18 `θεός` (the "monogenes theos" reading) is tagged in `word_edition` ONLY for the editions that print θεός verbatim: NA28, NA27, SBL, WH, Treg. It's **not** tagged for TR/Byz/Tyn even though those editions have *something* at that position. TR's reading (`υἱός`) lives as a separate `variant` row of kind `'meaning'` tagged for TR/Byz/Tyn.

**Implication for rendering**: a `variant` row matching the chosen edition asserts that the position is filled in that edition — even when the canonical word at that position isn't tagged for the edition. `bible_assemble_words` handles this via the "only variant present" branch.

### source_type encoding (mostly informational)

The `word.source_type` column uses codes like `NKO`, `N(K)O`, `ko`:
- Upper case letter = strongly attested in that family (N = Nestle/critical, K = Byzantine/TR, O = other)
- Lower case = present but in a subset (e.g. `ko` = TR/Byz only)
- Parentheses = textually disputed (bracketed in NA28)

Don't rely on `source_type` for rendering decisions — use `word_edition` / `variant_edition` instead. `source_type` is metadata; the edition tables are the source of truth.

### Notes field distinguishes STEPBible-original from Phase 3

STEPBible always populates `variant.note` with prose like "ναί ('yes') is only in traditional manuscripts (TR+Byz)". The Phase 3 import (`diff_editions.py`) leaves `note` empty. **This is how to identify which variants came from where**: `WHERE note IS NULL` finds Phase 3 entries.

### The 12088 boundary

`variant.id <= 12088` are STEPBible-original. `id > 12088` are Phase 3. Useful for any future cleanup that needs to distinguish them.

---

## 6. The pipeline — full run order

```
mysql stepbible < schema.sql
mysql stepbible < gematria_schema.sql

python import_bible.py             # TAHOT/TAGNT → word + variant + etc.
python compute_gematria.py         # populate gematria_word, gematria_verse
python import_bw_bibles.py         # Verse_Text from bw_bible → bible_na27, bible_scr
python populate_verseunicode.py    # BW → normalized Greek into verseunicode columns

# variant.position column (already added; this is for fresh setups)
mysql stepbible -e "ALTER TABLE variant ADD COLUMN position DECIMAL(6,2) NOT NULL DEFAULT 0;
                    CREATE INDEX idx_variant_position ON variant(word_id, position);
                    UPDATE variant v JOIN word w ON w.id = v.word_id SET v.position = w.position;"

python build_edition_verse_text.py # Phase 2: per-edition normalized verse text
python diff_editions.py            # Phase 3: position-aware variant emission
python cleanup_stale_variants.py   # remove elision-noise variants
```

`populate_verseunicode.py`, `build_edition_verse_text.py`, `diff_editions.py`,
and `cleanup_stale_variants.py` are all **idempotent** — safe to re-run.

### Normalization rules (normalize_for_diff, in populate_verseunicode.py and diff_editions.py)

The two scripts share the same `normalize_for_diff` function. Mirrored in JS as `grkClean()`. Rules:

- Decode BW transliteration → Greek Unicode (BW scripts only)
- NFD-decompose
- Strip combining diacritics in `[U+0300-U+0344, U+0346-U+036F]` — keeps U+0345 iota subscript
- NFC-recompose
- Lowercase
- Strip Unicode-category-P punctuation
- Strip modifier-letter apostrophes and Greek elision/accent marks: `ʼʹ᾽᾿῾΄΅` (U+02BC, U+02B9, U+1FBD, U+1FBF, U+1FFE, U+0384, U+0385)
- Collapse whitespace

**The Greek elision koronis (U+1FBD) is critical** — without stripping it, `δι᾽` (NA28 elision) vs `δι` (TR) appear as different tokens and produce thousands of spurious variants. We hit this bug; the fix is the `᾽` etc. in the strip set. If you ever re-add the function, include these.

---

## 7. Known data quirks

### 7.1 The 15 Hebrew verses with chunked word numbers

When importing, the loader hit a `Duplicate entry 'verse_id-1' for key 'word.uq_word_pos'` error. **15 Hebrew verses** map to two source blocks each starting word numbering at `#01`. The `word` table has `position` (sequential 1..N — the UNIQUE key) and `word_num` (the original `#NN`, may repeat) plus `chunk_num` to disambiguate. Conjoin links resolve target_word_num within the same chunk_num.

List: `Num.26.1, Deu.30.16, Jdg.16.14, 1Sa.20.42, 2Sa.23.33, 1Ki.18.33, 1Ki.20.2, 1Ki.22.22, 1Ki.22.43, 2Ki.25.3, 1Ch.12.4, Psa.51.0, Psa.52.0, Psa.54.0, Psa.60.0`.

### 7.2 Rev 12:18 / Rev 13:1

Two legitimate NRSV verses (NA28 splits them; KJV merges into 13:1). Manually fixed in the database — don't try to "correct" or merge them.

### 7.3 Rom 16:25-27 etc.

Verses some manuscripts omit are tagged with bracketed alt-refs like `Rom.16.25{14.24}`. They parse correctly.

### 7.4 Greek word_text contains parenthetical transliteration

Source stores Greek words as `"Βίβλος (Biblos)"`. `split_greek_word()` in `helpers.php` and `strip_greek_parens()` separate them. The Python diff scripts also have `strip_greek_parens()`.

### 7.5 Hebrew slash/backslash separators

In source, `/` separates prefix/suffix morphemes and `\` separates punctuation morphemes within a word. `clean_inline()` in `helpers.php` strips them for display.

### 7.6 NA27 editorial-bracket bytes are U+FFFD in source

`bible_na27.Verse_Text` contains `EF BF BD` (literal UTF-8 U+FFFD replacement chars) around words NA27 prints in editorial brackets like `[ὁ]` (Matt 22:32) or `[νομικός]` (Matt 22:35). The original bracket character was lost in a transcode upstream of MariaDB. `normalize_for_diff` strips these. The bracketing **position** is recoverable from the source if we ever want to surface "editorially uncertain" as metadata — see Pending Work § 9.

### 7.7 Heb 4:12 `τε` — the textbook "absent" case

`τε` at Heb 4:12 word #20 is tagged in `word_edition` only for TR/Byz. Renders in TR view, doesn't render in NA28 view. **No variant row needed** — `word_edition` filtering alone handles it. Great regression-check verse.

### 7.8 John 1:18 — the textbook "substitution" case

NA28 reads `μονογενὴς θεός`; TR reads `ὁ μονογενὴς υἱός`. The canonical `θεός` (word_id 356804) is tagged only for NA editions. STEPBible variant 6686 (kind=`meaning`, text=`υἱός`) is tagged for Tyn/TR/Byz. The position-merge serves up the variant when edition=TR. **Another great regression-check verse.**

---

## 8. Web UI — current state

URL: `http://localhost/stepbible/index.php?book=Jhn&chapter=1&verse=1`

### Implemented

- Book / Chapter / Verse / Show / **Edition** dropdowns. Edition is always enabled (including Hebrew books, for LXX mode); auto-submits on change.
- Prev/Next links walk the canon, preserving Edition and Show count.
- Edition dropdown values depend on the current book's tradition:
  - **OT MT books** (Gen–Mal): `[BHS, LXX-Rahlfs]`. Default: BHS.
  - **OT LXX books** (LxxGen–LxxMal etc.): `[BHS, LXX-Rahlfs]`. Default: LXX-Rahlfs.
  - **NT books and NT LXX books**: `[NA28, TR, LXX-Rahlfs]`. Default: NA28 (or LXX-Rahlfs for LXX books).
  Edition auto-submits on change. Switching editions triggers an auto-jump:
  - OT MT book + LXX-Rahlfs → parallel LXX book at same chapter/verse.
  - OT LXX book + BHS → parallel MT OT book at same chapter/verse.
  - OT LXX book + NA28/TR → Mat 1:1 (NT editions don't cover OT content).
  Other Greek editions (NA27, SBL, WH, Treg, Byz, Tyn) exist in the `edition` table for word/variant tagging; not surfaced in the dropdown.
- Biblehub-style interlinear: gematria / original / translit / English / Strong's / grammar.
- Assembled prose Original + English lines above interlinear. **English line uses the tagged KJV from the `bible_kjv` table for Hebrew OT / Greek NT verses** — each tagged word becomes hoverable and triggers the same Strong's tooltip path as the interlinear `.strongs-link` cells. See § 13.
- Variant indicator bar on words with variants; click to cycle base ↔ variant(s).
- Gematria panel: per-active-type sum and prime factorization. Updates on edition change, variant click, and word-cell selection.
- Word selection (click to toggle, shift+mousemove to paint).
- Detail panel (HTML present; click-to-expand needs rewiring — see § 9).
- **Strong's hover tooltip** on interlinear `.strongs` divs — `strongs-tooltip.js` fetches `?api=strongs` and shows a card with lemma, gloss, transliteration. Also handles multi-code `data-strongs` on KJV tagged spans (stacked entries with divider).
- **Strong's click-to-search** on interlinear `.strongs` divs — clicking any Strong's cell in a word cell navigates to `search.php?q=H0430&mode=strongs` (pads to 4-digit form). Cursor shows `pointer`.
- **Grammar tag expansion tooltip** — hovering any `.grammar` div shows a card expanding abbreviations. Greek: Robinson morphology parsed in JS (tense/voice/mood, case/number/gender, compound codes, etc.). Hebrew: STEPBible TAHOT formatted output (`V-Qal-Perf-3ms`, `Art-h | N-ms`) parsed segment-by-segment, including smart participial vs. finite verb tail detection, suffix pgn (4-char `p[person][gender][number]` format), and all particle subtypes. Language detected via `data-lang` attribute (`grk`/`heb`) on the grammar div. Cursor shows `help`.

### Search bar (unified — 2026-05-21)

Always-visible search bar in the ref-line nav. The separate "Reference" input box and "Look up" button have been removed; **all navigation now flows through the single search box**. Priority order in `doSearch()`:

1. **Verse reference** — if the input matches a known book name + chapter (optionally verse), navigates to `index.php?ref=<input>`. Pattern matching in JS (`BOOK_PREFIXES` set + regex) runs before any search routing; the server's `parse_reference()` does the canonical resolution.
   - `Jhn 3:16`, `John 3 16`, `1 Cor 13:4` → exact verse.
   - `Jhn 3`, `Psalm 23`, `1 Cor 13` → chapter at verse 1 (PHP `parse_reference` extended to handle chapter-only).
   - If the book name isn't in `BOOK_PREFIXES`, falls through to search (prevents "beginning 2" being mistaken for a reference).
2. **Strong's code(s)** — auto-detected by `^[HG]\d{1,5}[A-Za-z]?(,\s*[HG]\d{1,5}[A-Za-z]?)*$`; supports comma-separated multi-code input (e.g. `H430, G3056` from clicking multiple cells). Routes to `search.php?mode=strongs`.
3. **Phrase / text** — remaining input auto-detects script (Hebrew / Greek / English); phrase checkbox visible, checked = exact phrase, unchecked = AND-of-words. Routes to `search.php?mode=phrase` or `?mode=text`.

Three automatic fill signals: word-cell click (Strong's), drag over `.assembled .original` (Hebrew/Greek phrase), drag over `.assembled .english` (KJV phrase — auto-expanded to whole-word boundaries). The init `setTimeout` correctly calls `updateDetected()` before syncing UI state so back-navigation shows the right mode for browser-restored form values. See § 13 for the search-side PHP details.

### Search results page (`search.php`)

- **Verse reference links** in all result sections carry `class="verse-ref" data-book data-chapter data-verse`. Hovering fires `verse-tooltip.js` which fetches `?api=kjv_verse` and pops a KJV preview card (cached, stale-safe).
- **Strong's / gematria results**: each Strong's code renders as a clickable `.strongs-link` `<a>` — zero-padded display (`H0430`), href to `?q=H0430&mode=strongs`, `data-strongs="H430"` for tooltip. Hover fires `strongs-tooltip.js` normally.
- **API handlers** at the top of `search.php` (before any output): `?api=strongs&code=H430` and `?api=kjv_verse&book=Gen&chapter=1&verse=1`. Both return JSON and `exit`. The `strongs-tooltip.js` on `index.php` fetches the same API there; `search.php` has its own identical handlers so tooltip JS works on the search page too.

### Things that don't exist yet

- Edition-comparison side-by-side view
- Variant browser page (filter by book / kind / supporting edition)
- Whole-chapter view (currently up to N consecutive verses)
- Word detail panel wired to actual click events (HTML exists but click-to-expand JS was removed when word selection was added)
- Hebrew edition support (the `edition` table has L, Q, K, R, X, A-V; UI doesn't expose them)

---

## 9. Pending work flagged by the user

1. **Drop `edition_verse_text`** after a week of UI testing. Served only as Phase 3 workbench input. The live UI does not query it.
2. **Optional**: Preserve NA27 editorial-bracket signal. A small script could scan `bible_na27.Verse_Text` for `�word�` patterns, map them via verse+position to `word.id`, and tag a `na27_uncertain` flag (column on word or separate table). NA27 prints these as `[ὁ]`, `[νομικός]`. Useful textual-critical metadata; not blocking anything.
3. **Septuagint (LXX) import** — schema + loader landed (2026-05-21). Source: `eliranwong/LXX-Rahlfs-1935` (CC BY-NC-SA 4.0, CCAT user declaration acknowledged). See § 12 below for the full architecture. Open follow-ups: smart MT↔LXX edition toggle (right now you switch books from the Book dropdown), deuterocanonical book grouping in the dropdown, and integration of `08_versification` for cross-tradition verse alignment.
4. **Future search modes** (user priority order):
   - Strong's concordance (click any Strong's number → list of verses)
   - Edition diff view (NA28 vs TR side-by-side)
   - Variant browser
   - (English keyword search shipped 2026-05-21 via `bible_kjv.Verse_Text_Clean` LIKE; verse-reference search shipped 2026-05-21 via unified search box. If LIKE becomes slow, add a FULLTEXT index on `Verse_Text_Clean` and switch to `MATCH...AGAINST`.)

---

## 10. Conventions / gotchas for future Claude

### Edit-tool truncation on Windows mount

The Edit and Write tools sometimes truncate files mid-write on this user's Windows-mounted filesystem. **For any file longer than ~300 lines or when applying multiple edits in sequence, write via `bash` heredoc** (`cat > "..." << 'EOF' ... EOF`) instead. Verify with `wc -l` and a tail check after every write. The user has been patient about this; don't blame the editor — just route around it.

### The literal-combining-marks regex trap

Writing `[̀-ͯ]` as a literal regex character class in Python source can decompose U+0344 into `U+0308 + U+0301` during normalization, breaking the range to `[U+0300-U+0308]` and silently letting smooth/rough/circumflex through. **Always use explicit escapes**: `[̀-̈́͆-ͯ]` in Python, `[̀-̈́͆-ͯ]` in JS.

### Position-key normalization

`word.position` is SMALLINT, `variant.position` is DECIMAL(6,2). PDO returns them as `'5'` and `'5.00'` respectively. Use `sprintf('%.2f', (float)$position)` to normalize before keying any map by position. This is fixed in `bible_assemble_words` but mention it in any new code that touches positions.

### Null-byte injection on PHP edits

The Windows-mounted filesystem occasionally injects null bytes into PHP files after a Python `open(...).write()` cycle, causing PHP to fail with `syntax error, unexpected character 0x00`. If the user reports a PHP parse error after an edit, **first** run this one-liner from the project root:

```bash
python3 -c "
import glob
for p in glob.glob('web/*.php') + glob.glob('web/js/*.js') + ['web/style.css']:
    d = open(p,'rb').read()
    if b'\x00' in d: open(p,'wb').write(d.replace(b'\x00', b'')); print(f'{p}: stripped nulls')
"
```

It's idempotent — does nothing on clean files, fixes any contaminated ones. Don't reach for code rewrites until you've ruled this out.

### Hebrew section markers — let the DB do the math

`compute_gematria.py` correctly strips `\פ` (Petuhah) and `\ס` (Setumah) paragraph markers before summing — its precomputed values in `gematria_word`/`gematria_verse` are right. `clean_inline()` in `helpers.php` removes the leading `\` for display, leaving a bare `פ` or `ס` in the rendered text. **Do not recompute Hebrew gematria from displayed text in JS** — `variant-switcher.js`'s `syncGematriaOnLoad()` explicitly skips Hebrew cells for this reason. (Hebrew has no edition dropdown anyway, so the precomputed values are always authoritative.) If you ever add Hebrew edition substitution, fix this by extending JS `hebGemVal` to also recognize standalone-letter section markers.

### Don't synthesize when the data can answer

The architecture took two iterations to get right. The first iteration tried to synthesize "addition" synthetic words in `db.php`, resolve conflicts between `omission` and `meaning` variants, dedupe across kinds — none of it worked. The current architecture works because `variant.position` makes synthesis unnecessary: just SELECT and merge by position. If you find yourself adding conflict-resolution logic, stop and ask whether the schema is missing something.

### The user values clarity over cleverness

When the code got complex, the user said so. The refactor toward position-aware variants was driven by that feedback. Keep changes small, prefer SELECT-and-display over compute-on-the-fly, and call out when something feels hacky so we can fix it before it ossifies.

---

## 11. How to pick up where we left off

1. Read this file end to end.
2. Skim `schema.sql` for table layout. Remember `variant.position` was added later.
3. Read `web/db.php` from `bible_verse_full()` down through `bible_attach_per_word_data()`. That's the heart of the rendering. About 200 lines.
4. Open the running web app at `http://localhost/stepbible/index.php` and try:
   - **John 1:1 / NA28** — baseline. Hover `N-NSM` grammar tag → tooltip shows "Noun · Nominative · Singular · Masculine".
   - **John 1:18 / TR** — should show `… ὁ μονογενὴς υἱός ὁ ὢν …`; click `υἱός` to cycle to `θεός`.
   - **Heb 4:12 / TR** — `τε` appears; NA28 doesn't have it.
   - **Heb 4:13 / TR** — `εστι` instead of `εστιν`.
   - **John 1:3 / either** — `δι᾽` should NOT have a variant bar (post-elision-cleanup).
   - **Gen 1:1** — Hebrew; hover `V-Qal-Perf-3ms` grammar tag → tooltip shows "Verb · Qal · Perfect · 3rd · Masc · Sing". Hover `Art-h | N-mp` → two sections: "Article" + "Noun · Masc · Plur".
   - **Click any Strong's number** in any word cell → navigates to `search.php?q=H0430&mode=strongs`.
   - **Search for H430** or **H0430** (both work, normalized to 4 digits) → concordance results. Hover a verse reference link → KJV preview tooltip. Click a Strong's code in gematria results → concordance lookup.
   - **Type a number like `3713`** in the search box → navigates to gematria search.
5. Ask Richard what he wants to tackle next. Likely answers: drop edition_verse_text (after testing), Strong's concordance, English search, LXX, wiring the detail panel.

**If this file is wrong or stale as you work, update it.** The next handoff
shouldn't have to re-discover what we just learned.

---

## 12. LXX (Septuagint) — separate-tables design (updated 2026-05-21)

### Source

`eliranwong/LXX-Rahlfs-1935` — Rahlfs 1935 editio minor with CATSS
morphology + Open Scriptures lexeme/Strong's joins. License is
**CC BY-NC-SA 4.0**, and the underlying CATSS data carries a separate
user-declaration requirement
(`http://ccat.sas.upenn.edu/gopher/text/religion/biblical/lxxmorph/0-user-declaration.txt`).
Fine for local use; attribute to CATSS / TLG / UBS / Eliran Wong if
you ever redistribute.

Clone target: any local path to the `eliranwong/LXX-Rahlfs-1935` repository  
(Use `--lxx-root <path>` when running `import_lxx.py`).

### Design choice — keep LXX in its own namespace

The LXX lives in three new tables (`book_lxx`, `verse_lxx`, `word_lxx`)
that sit **parallel** to the existing 11-table v2 schema. The shared
`book` / `verse` / `word` tables are never touched. The shared
`edition` table gains one row, `LXX-Rahlfs`, which the web UI uses as
a *mode switch* — picking it from the Edition dropdown routes lookups
to the LXX tables and (where `book_lxx.mt_parallel_osis` allows)
auto-jumps to the parallel LXX book at the same chapter/verse.

Why separate? LXX uses Rahlfs's own versification (Ps 9 ≈ MT 9+10,
Esther has Greek-only additions tagged 1:1a..1:1s, Jeremiah's chapter
order differs in the back half), and several books have multiple
recensions in the source data: Joshua A/B, Judges A/B, OG vs
Theodotion Daniel/Susanna/Bel, Tobit B/A vs S. Mixing those into the
shared tables would force constant alignment-table lookups and break
invariants in code that assumes one tradition per `book_id`.

### File-layout cheat sheet (source data)

The 8 per-word files we read are **line-aligned** (623,693 rows in
each). Row N in one file is the same Greek word as row N in every
other file. Verse boundaries live in a separate 30,637-row file.

| File | Field |
|---|---|
| `01_wordlist_unicode/text_accented.csv` | Accented Greek surface |
| `01_wordlist_unicode/alignment_with_OSSP/E-verse.csv` | `start_row\tstart_row\t「Book Chap:Verse[sub]」` |
| `02_lexemes/OSSP_lexemes.csv` | Lemma |
| `03b_descriptions_on_morphology_codes/morphology_623693_with_description.csv` | Morph code + plain-English description |
| `04_SBL_transliteration/final_transliteration_SBL.csv` | SBL transliteration |
| `05_pronunciation/final_pronunciation_modern_Greek.csv` | Modern Greek pronunciation |
| `06_English_gloss/beta.csv` | 1-2 sense English gloss |
| `07_StrongNumber/final_Strongs.csv` | Strong's number |

A handful of `E-verse.csv` lines have no chapter:verse (only `「Od 」`
title-headers between odes); the loader merges those into the
previous verse's word range.

### Schema (lxx_schema.sql)

Three new tables, fully `DROP / CREATE`-safe to re-run:

- **`book_lxx`** (59 rows, ids 1-59) — `osis_code` (e.g. `LxxGen`, `LxxJoshA`, `LxxPsSol`), `name`, `mt_parallel_osis` (the MT `book.osis_code` this LXX book parallels — NULL for deuteros), `tradition` (`LXX` / `LXX-alt` / `LXX-OG` / `Theodotion`), `rahlfs_code` (source identifier like `1Sam/K`, `TobBA`), `book_order`.
- **`verse_lxx`** — per-LXX-verse row. `(book_id, chapter, verse, subverse)` is the unique key. `subverse` is empty for normal verses and `a..s` for additions (Esther 1:1a..1:1s, Prov 3:16a, etc.). `text_original` and `text_english` hold assembled per-verse strings.
- **`word_lxx`** — per-word row. Greek surface, SBL transliteration, English gloss, Strong's, CATSS morph code + plain-English description, lemma, pronunciation. Unique key `(verse_id, position)`.

Plus one INSERT into the shared `edition` table: `LXX-Rahlfs`, `Greek`, edition_order 25.

### Book inventory (59)

37 protocanonical LXX (Gen–Mal) with `mt_parallel_osis` populated, 2 Joshua + 2 Judges recensions, OG + Theodotion Daniel (LxxDan + LxxDanTh), Susanna OG + Theodotion (LxxSus + LxxSusTh), Bel OG + Theodotion (LxxBel + LxxBelTh), Tobit BA + S (LxxTobBA + LxxTobS), plus 11 deuterocanonical with `mt_parallel_osis = NULL`: Jdt, 1Esd, 1-4Mac, Wis, Sir, Bar, EpJer, Odes, PsSol.

Naming conventions: all LXX `osis_code` values start with `Lxx` so the web UI can detect them via `strpos($code, 'Lxx') === 0`. Kingdoms books use `Kdm` not `Sam/Kgs` (`Lxx1Kdm` = MT 1 Sam, `Lxx3Kdm` = MT 1 Kgs) to reflect the source's own naming. Rahlfs's "2 Esdras" is MT Ezra-Neh; the apocryphal "1 Esdras" is `Lxx1Esd`.

### import_lxx.py

Reads the 8 per-word files into parallel lists, walks the verse-boundary file, and for each boundary slices `[start..end]` across all the lists into one `verse_lxx` row plus N `word_lxx` rows. **Idempotent** — each run does `DELETE FROM word_lxx; DELETE FROM verse_lxx; ALTER ... AUTO_INCREMENT = 1` first. `book_lxx` stays put (seeded by `lxx_schema.sql`).

Dry-run summary (validated 2026-05-21):

```
boundaries: 30,637 verses → 346 title-only rows merged → 30,291 verses inserted
words: 623,693 across 59 LXX books
```

Run order on Richard's Windows box:

```
mysql stepbible < lxx_schema.sql
python import_lxx.py
```

`--dry-run` validates the parser without touching the DB.  
`--lxx-root` is required (no default path is provided).

### Web UI (web/db.php + web/index.php)

In `db.php` the existing `bible_*` functions are unchanged. New parallel set targets the LXX tables:

- `lxx_books()` — list every `book_lxx` row.
- `lxx_chapters($lxx_osis_code)`, `lxx_verses($lxx_osis_code, $chapter)` — populate the chapter/verse dropdowns.
- `lxx_book_by_osis($code)` — fetch one LXX book row.
- `lxx_book_by_mt_osis($mt_code)` — return the *primary* LXX parallel of an MT book (prefers `tradition='LXX'` over OG/alt/Theodotion). Drives the auto-jump.
- `lxx_verse_full($code, $ch, $v, $sub='')` — same return shape as `bible_verse_full` so the existing interlinear template renders LXX rows without changes. Synthesizes the editions/alts/morphemes/links/variants keys that the template expects, with the LXX-Rahlfs edition pre-attached. Gematria seeds at 0 because the precomputed `gematria_word` table is keyed to MT `word.id`; client-side `syncGematriaOnLoad` recomputes from the displayed Greek (existing behavior).
- `lxx_neighbor($code, $ch, $v, $sub, $direction)` — walk `book_order, chapter, verse, subverse`.

In `index.php`:

- The Edition dropdown stays as the only control surface: when `edition_code = 'LXX-Rahlfs'`, the page is in **LXX mode**.
- `$lxx_mode` gets computed early. The book list, chapter list, verse list, verse data, and prev/next all flip to the `lxx_*` set.
- **Auto-jump on edition flip**: if the user picks `LXX-Rahlfs` while on an MT book, `lxx_book_by_mt_osis` swaps the book to the parallel LXX book (Gen 1:1 → LxxGen 1:1). If they flip back to `NA28`/`TR` while on an LXX book, `lxx_book_by_osis(...)->mt_parallel_osis` walks them back to the MT parallel. NT books with no LXX parallel fall back to `LxxGen 1:1`.
- AJAX `chapters` / `verses` endpoints route by book-code prefix (`strpos($book,'Lxx') === 0`) so the chained dropdowns stay correct after an edition flip.

The Hebrew "disable Edition dropdown" rule has been lifted — Edition is always enabled now so the user can switch into LXX mode from any starting book.

### Smoke-test URLs

After `mysql ... < lxx_schema.sql && python import_lxx.py`:

```
http://localhost/stepbible/index.php?book=Gen&chapter=1&verse=1                     -- MT, unchanged
http://localhost/stepbible/index.php?book=Gen&chapter=1&verse=1&edition=LXX-Rahlfs  -- auto-jumps to LxxGen 1:1
http://localhost/stepbible/index.php?book=LxxGen&chapter=1&verse=1                  -- direct LXX nav
http://localhost/stepbible/index.php?book=LxxPs&chapter=50&verse=1                  -- LXX Ps 50 ≈ MT Ps 51
http://localhost/stepbible/index.php?book=LxxEsth&chapter=1&verse=1                 -- check subverse stepping via Next
http://localhost/stepbible/index.php?book=LxxSir&chapter=1&verse=1                  -- deuterocanonical
http://localhost/stepbible/index.php?book=LxxDanTh&chapter=1&verse=1                -- Theodotion Daniel
http://localhost/stepbible/index.php?book=Jhn&chapter=1&verse=1                     -- NT regression, NA28
```

### Known follow-ups

- **Subverse navigation**: prev/next steps through subverses correctly, but the Verse dropdown collapses them and the prev/next URLs don't yet carry a `subverse` query param. Esther 1:1a-s etc. are reachable but only by clicking Next from 1:1. Adding `?subverse=a` to the prev/next links would round-trip cleanly (the routing already accepts `$_GET['subverse']`).
- **`08_versification/map_NRSV.csv`**: a 6,790-row word-level Rahlfs↔NRSV alignment. Not loaded. Wiring it would let a "stay on the same English-language reference" mode track Ps 51 ↔ LxxPs 50 word-by-word instead of just chapter-aligning.
- **Strong's lookup**: LXX uses `G####` like the NT. The existing `bible_strongs_lookup` works for LXX too as long as `strongs` is populated, but the per-word click-to-lookup UI hasn't been retested for the new rows.
- **Gematria precompute**: `gematria_word` is keyed to `word.id` (MT/NT only). For LXX, `syncGematriaOnLoad` recomputes from displayed text — correct but slightly slower than NT path. If LXX gematria becomes a hot path, build a `gematria_word_lxx` table.

---

## 13. KJV English with inline Strong's tags (added 2026-05-21)

### Source

A new `bible_kjv` table inside `stepbible`. Schema:

| col | type | note |
|---|---|---|
| `Verse_Order` | INT PK | 1..31102 across the full canon |
| `Book` | INT | matches stepbible `book.id` (1..66) — direct map, no translation table needed |
| `Chapter` | INT | |
| `Verse` | INT | |
| `Verse_Text` | VARCHAR(1000) | KJV English with inline Strong's tags like `In the beginning <07225> God <0430> created <01254> <0853> the heaven <08064> ...` |
| `Gematria` | INT | not currently used by the UI |
| `Verse_Text_Clean` | VARCHAR(1000) | same text with tags stripped; used by the English phrase-search path (`mode=phrase&lang=english` → `LIKE %needle%`) |

### Tag convention (REVERSE-ENGINEERED FROM THE DATA)

Each `<NNNN>` tag attaches to the **immediately preceding** English word. Multiple tags can chain on one word: `created <01254> <0853>` means "created" gets both H1254 (bara) and H0853 (the et accusative marker, untranslated in English but attributed to whichever English word is nearest). KJV-supplied insertions appear in square brackets — `darkness <02822> [was] upon` — and **never** consume tags; they render italic and muted.

Hebrew OT (Book 1..39) emits `H`-prefixed codes, Greek NT (Book 40..66) emits `G`-prefixed. Leading zeros are stripped to match the canonical lookup format in the `strongs` table (`H430`, not `H0430`).

### Web wiring

- **`web/db.php` → `kjv_verse_text($book_id, $chapter, $verse)`** — single-row lookup. Static-cached per `(book, chapter, verse)`. Returns `null` if the row is absent (KJV doesn't carry Rev 12:18 etc.); the caller falls back to the STEPBible-supplied English. Wrapped in try/catch so a missing/renamed table degrades silently — if you suspect a lookup issue, drop in a `kjv_debug.php` (now deleted, but `SHOW TABLES` + `DESCRIBE bible_kjv` + a sample `kjv_verse_text(1,1,1)` is the recipe).
- **`web/helpers.php` → `render_kjv_tagged($raw, $testament)`** — tokenizes the tagged text and emits sanitized HTML. Words with tags become `<span class="kjv-tag strongs-link" data-strongs="H1254 H853">created</span>`. Bracketed inserts become `<em class="kjv-supplied">was</em>`. The dual class — `kjv-tag` for styling and `strongs-link` for hover — means the existing tooltip event delegation picks them up for free.
- **`web/index.php`** — the `.english` div under `<div class="assembled">` now calls `kjv_verse_text` + `render_kjv_tagged` whenever `!$lxx_mode`. LXX mode is untouched; the STEPBible-supplied `text_english` continues to render there. The `<div class="label verse-eng-label">English</div>` heading gains a small `(KJV)` chip in non-LXX mode.
- **`web/js/strongs-tooltip.js`** — extended to handle multi-code `data-strongs`. `splitCodes()` splits on whitespace/comma; `renderOneEntry()` builds one `.st-entry` block per code; the tooltip stacks them with a thin divider. The single-code interlinear cells still work identically (one-entry render).
- **`web/style.css`** — `.kjv-tag` gets `cursor: help`, a dotted underline in `--accent`, and a light hover background. `.kjv-supplied` is italic + muted. `.strongs-tooltip .st-entry + .st-entry` adds the divider between stacked entries. `.word-search-bar` (always-visible search) gets an inline-flex select/input/button row that sits in the ref-line nav.

### Search-bar integration (added the same day)

The search bar that used to be hidden-until-populated is now always visible and typable. Three input signals plus a typed-input auto-detector populate it:

1. **Word-cell click** in the interlinear → mode = Strong's or Text, one comma-separated value per cell (unchanged behavior).
2. **Drag-select in `.assembled .original`** → mode = Phrase, lang = the verse's source language. Hits `verse.text_search`.
3. **Drag-select in `.assembled .english` (KJV)** → mode = Phrase, lang = English. **The selection is auto-expanded to whole-word boundaries** so "od created th" populates as "God created the". Expansion uses a throwaway `Range` from the container to translate the selection boundary into a flat-text offset, then walks `\p{L}\p{M}\p{N}'` characters outward — but only if the selection's own edge char is a word char, so flanking spaces don't sweep in neighbors.
4. **Typed/pasted input** → `detectScript()` looks at the value: Strong's pattern `^[HG]\d{1,5}[A-Za-z]?$` → mode = strongs; Hebrew block / presentation forms → lang = Hebrew; Greek block / Greek Extended → lang = Greek; Latin letters → lang = English. When whitespace is present and mode isn't strongs, mode auto-flips to phrase. The dropdown still works as a manual override.

PHP side (`web/search.php`): phrase mode branches on `lang`. With `lang=english` it runs
```sql
EXISTS (SELECT 1 FROM bible_kjv k
        WHERE k.Book    = b.id
          AND k.Chapter = v.chapter
          AND k.Verse   = v.verse
          AND k.Verse_Text_Clean LIKE ?)
```
and the results header reads "KJV phrase". Hebrew/Greek phrase mode is unchanged. The `mode=text` (per-word AND) path is also unchanged — it still normalizes against `word.text_search` and assumes Hebrew/Greek.

JS regression notes — there's a subtle gotcha I hit: `textOffsetInContainer` originally tried to hand-roll the element-typed boundary case and had an infinite-recursion bug. The shipping version uses a one-line `Range.setStart(container,0)+setEnd(node,offset)+toString().length` — simpler and lets the browser handle nested-span boundaries correctly. Don't refactor it back to a manual walker without retesting.

### Smoke-test URLs

```
http://localhost/stepbible/index.php?book=Gen&chapter=1&verse=1   -- "In the beginning..." with KJV tags
http://localhost/stepbible/index.php?book=Gen&chapter=1&verse=2   -- [was] should render italic/muted
http://localhost/stepbible/index.php?book=Jhn&chapter=3&verse=16  -- KJV with G-prefixed Strong's
http://localhost/stepbible/index.php?book=LxxGen&chapter=1&verse=1 -- LXX mode: KJV NOT used (heading is plain "English")

Search regression checks (after loading any verse):
- Highlight "od created th" in Gen 1:1 KJV → box fills with "God created the", mode = Phrase. Press Enter → results page lists every KJV verse containing that exact substring.
- Type H430 → mode auto-flips to Strong's.
- Type Hebrew or Greek directly → mode flips to Phrase, lang flips to Hebrew / Greek.
- Highlight a single English word with flanking spaces (" created ") → expands to just "created", NOT "God created the".
```

### Pending follow-ups

- **LXX KJV**: KJV doesn't cover the deuterocanonical / LXX-only material, and the MT books-in-LXX-versification mapping is non-trivial. LXX mode currently shows the STEPBible-supplied `text_english`. If/when a mapping layer exists (see § 12's `08_versification` note), KJV could light up for parallel-MT LXX verses too.
- **Strong's concordance**: with tagged English now in the assembled view, clicking a tag (rather than just hovering) could navigate to a per-Strong's concordance page once that feature is built.
- **`Verse_Text_Clean` is now wired up** (it's the English phrase-search target). The current `LIKE %needle%` works on 31k rows but if it ever gets slow, add a FULLTEXT index on that column and switch to `MATCH(...) AGAINST (...)`.
- **`Gematria` column** is still unused — could drive a KJV per-verse English gematria display in the gematria panel alongside the original-language values.

---

## 14. Session log

### 2026-05-21 (session 1) — LXX + KJV tagged English + unified search bar

- LXX import pipeline built and validated (`lxx_schema.sql`, `import_lxx.py`).
- `bible_kjv` table imported with inline `<NNNN>` Strong's tags.
- `render_kjv_tagged()` in `helpers.php` tokenizes the tagged text into hoverable spans.
- `strongs-tooltip.js` extended to stack multi-code entries.
- Search bar made always-visible; drag-select over assembled English KJV expanded to whole-word boundaries; script auto-detect added.
- PHP `search.php` routes `mode=phrase&lang=english` to `Verse_Text_Clean LIKE %…%`.

### 2026-05-21 (session 2) — Strong's multi-code + unified reference search

**Strong's auto-detect fixes (`web/js/search-trigger.js`)**

- Regex was `/^[HG]\d{1,5}[A-Za-z]?$/i` — only matched single codes. Multi-cell clicks produce `"H430, G3056"` which failed. Fixed to `/^[HG]\d{1,5}[A-Za-z]?(,\s*[HG]\d{1,5}[A-Za-z]?)*$/i`.
- Init `setTimeout` was calling `syncPhraseLabel()` without first calling `updateDetected()`, so `isStrongs` was `false` after browser back-navigation even when the form value was a Strong's code. Fixed: `setTimeout(function () { updateDetected(); syncClearBtn(); }, 0)`.

**Verse reference in the unified search box**

- The separate "Reference" `<input name="ref">` form and "Look up" button removed from the nav bar in `web/index.php`.
- Related dead CSS (`.selector .or`, `.selector button.alt`) removed from `web/style.css`.
- `web/book_aliases.php` — `parse_reference()` extended to handle **chapter-only** input (`"Jhn 3"`, `"Psalm 23"`) by matching a second regex `/^([1-3]?\s*[A-Za-z]+)\s+(\d+)$/u` and returning `verse=1`.
- `web/js/search-trigger.js` — added `BOOK_PREFIXES` (Set of all recognised book-name keys, mirrors PHP `BOOK_ALIASES`) and `tryNavigateRef(q)` which:
  - Matches full refs (`Book Ch:V` / `Book Ch.V` / `Book Ch V`) and chapter-only (`Book Ch`).
  - Validates the book part against `BOOK_PREFIXES` to avoid false-positives on text like `"beginning 2"`.
  - On match, navigates to `index.php?ref=<input>` and returns `true`; `doSearch()` short-circuits before search routing.
- Search input placeholder updated to `"Jhn 3:16, word, phrase, or H0430"`.

**Edition dropdown — OT/NT split**

- OT Hebrew books (Gen–Mal) now get `[BHS, LXX-Rahlfs]` in the Edition dropdown; NT and LXX books get `[NA28, TR, LXX-Rahlfs]`.
- PHP: `const OT_BOOK_CODES = [...]` in `index.php`; `$is_ot_book` detection sets `$editions` and `$default_edition` before any auto-jump.
- JS (`web/js/dropdowns.js`): `syncEditionOptions()` repopulates the edition select on book-change based on `option.dataset.lang`; `OT_EDITIONS` / `NT_EDITIONS` consts defined.

**Edition auto-jump edition-list bug fixed**

- Root cause: `$is_ot_book` and `$editions` were computed from the URL's book code *before* the LXX auto-jump block, so when a user selected NA28 while viewing an LXX book (e.g. `?book=LxxGen&edition=NA28`) PHP jumped to the MT parallel (Gen) but the dropdown still showed the NT edition set with NA28 selected.
- Fix: after the auto-jump block, `$current_is_lxx_book`, `$is_ot_book`, `$editions`, `$valid_codes`, and `$edition_code` are all recomputed from the final `$book_code`. Any invalid edition (e.g. NA28 on an OT book) falls back to the correct default (BHS for OT, LXX-Rahlfs for LXX).

### 2026-05-22 (session 3) — OT LXX edition dropdown + auto-jump landing pages

**LXX auto-jump landing destinations (web/index.php)**

- When on an OT LXX book (e.g. `LxxGen`) and switching to BHS: auto-jumps to the MT parallel (`Gen`, same chapter/verse).
- When on an OT LXX book and switching to NA28 or TR: auto-jumps to **Mat 1:1** — NT editions have no OT content. Previously, the `!$lxx_mode && $current_is_lxx_book` branch always tried to find an MT parallel regardless of edition; extended to `if ($edition_code === 'BHS') { ...MT parallel... } else { $book_code = 'Mat'; $chapter = 1; $verse = 1; }`.

**OT LXX edition dropdown fixed (web/index.php + web/js/dropdowns.js)**

- Root cause: the initial editions block treated ALL LXX books as `$is_ot_book=false` → `bible_greek_editions()` = [NA28, TR, LXX-Rahlfs]. OT LXX books were shown NT editions.
- PHP fix: added `$is_lxx_ot = $current_is_lxx_book && in_array(substr($book_code, 3), OT_BOOK_CODES, true)` (strips `Lxx` prefix, checks against `OT_BOOK_CODES`). Condition changed to `if ($is_ot_book || $is_lxx_ot)` in both the initial editions block and the post-auto-jump recompute block. Default edition for LXX OT books is `LXX-Rahlfs` (not BHS).
- JS fix (`syncEditionOptions` in `dropdowns.js`): added `const isLxx = opt.value.startsWith('Lxx')` and changed condition to `lang === 'Hebrew' || isLxx` → `OT_EDITIONS`. This treats all Lxx-prefixed books as OT-edition candidates.

**Known limitation**: the JS fix equates `startsWith('Lxx')` with OT. If NT LXX books exist in the DB (the module has `nt.bzs`), selecting one in the book dropdown would show `[BHS, LXX-Rahlfs]` (wrong — should be NT editions). PHP handles this correctly via `OT_BOOK_CODES`; the mismatch only shows client-side when the user changes the book dropdown without submitting. Full fix would require: (a) fix `lxx_books()` SQL to compute `CASE WHEN mt_parallel_osis IS NOT NULL THEN 'OT' ELSE 'NT' END AS testament`, (b) add `data-testament` to book option HTML, (c) update JS to check `data-testament` instead of bare `startsWith`.

### 2026-05-22 (session 4) — KJV↔interlinear highlight fixes + auto-nav dropdowns + Strong's equivalence analysis

**Alt-Strong's matching in KJV hover highlight (`web/js/strongs-tooltip.js`)**

- Problem: KJV word hover uses `applyKjvHighlight()` to find the matching interlinear cell. The word *was* in Jhn 1:1 is tagged KJV G2258, but TAGNT's `strongs_primary` for εἰμί is G1510. The alt code G2258 is in `word_alt_strong` but wasn't being checked.
- Fix: `applyKjvHighlight` now also reads `WORD_DATA[cell.dataset.wordId].alts` (already populated in the page's `<script id="word-data">` JSON) and unions alt codes with primary codes before matching.
- Also added **earliest-code-wins** logic: when a KJV word is tagged with multiple codes (e.g. `created <01254> <0853>`), only cells whose code matches the **first** KJV code index are highlighted — the secondary H0853 (accusative marker) was spuriously matching and lighting up extra cells.

**STRONG_EQUIV synonym map introduced, then expanded**

- Problem: *spoken* in Mat 3:3 is tagged KJV G4483 (ῥηθείς passive); TAGNT uses G2046 for the same words. Not an alt-strong issue — a genuine systematic code discrepancy between source traditions.
- Fix: added `STRONG_EQUIV` constant in `strongs-tooltip.js` and `expandEquiv()` helper. `applyKjvHighlight` calls `expandEquiv(primaryCodes.concat(altCodes))` before matching so synonyms resolve transparently.
- Initial map: `{ 'G2046': ['G4483'], 'G4483': ['G2046'] }`.
- Later in this session expanded to 10 pairs after systematic analysis (see `find_strongs_equiv.py` below).

**All dropdowns auto-submit on change (`web/js/dropdowns.js`)**

- Book change: fetches the chapter list, populates it, then immediately calls `form.submit()`. Page lands at chapter 1, verse 1 of the new book (same edition).
- Chapter change: fetches the verse list, populates it, then calls `form.submit()`. Page lands at verse 1 of the new chapter.
- Verse change: resets Show-N count to 1, then submits.
- Show-N count change: submits immediately.
- Edition change was already auto-submitting; no change there.

**LXX-Rahlfs label shortened to "LXX" in the Edition dropdown**

- PHP (`web/index.php` line ~261): `<?= h($ed['code'] === 'LXX-Rahlfs' ? 'LXX' : $ed['code']) ?>` (title= still shows full name on hover).
- JS (`web/js/dropdowns.js`): `OT_EDITIONS` and `NT_EDITIONS` objects gained a `label` field for `LXX-Rahlfs`; `o.textContent = ed.label || ed.code` uses it when JS repopulates the dropdown after a book change. Both paths needed the fix because server-rendered initial state (PHP) and AJAX-repopulated state (JS) are separate code paths.

**Greek/Hebrew text selection word-boundary expansion fixed (`web/js/search-trigger.js`)**

- Problem: drag-selecting within `.assembled .original` (Hebrew/Greek prose line) wasn't expanding to word boundaries. A `setTimeout(0)` added earlier to handle span-based English selections was *clearing* the selection by the time the Greek handler read it. Greek text nodes are plain text (no nested spans), so the selection is available synchronously.
- Fix: the `.assembled .original` handler calls `expandSelectionToWords(assembledOrig)` synchronously (no setTimeout). The `.assembled .english` (KJV) handler retains `setTimeout(0)` because its span-based selection finalizes asynchronously.

**`find_strongs_equiv.py` — systematic Strong's code analysis**

- New script in the project root. Connects to MariaDB via `config.ini`, reads every verse in `bible_kjv`, and for each verse:
  1. Extracts all `<NNNN>` tags → normalizes to `H`/`G`-prefixed codes (leading zeros stripped).
  2. Queries `word.strongs_primary` + `word_alt_strong.alt_strong` for the same verse from the TAGNT/TAHOT word tables.
  3. Both sides are normalized the same way (leading zeros stripped) before comparison.
  4. Codes in KJV but not in TAGNT = "orphaned KJV codes". Codes in TAGNT but not in KJV = "TAGNT-only" (H9001-H9999 STEPBible function-word extension codes are excluded from this side).
  5. Records co-occurrence counts: how often each orphaned KJV code X appears alongside each TAGNT-only code Y.
  6. Reports candidates sorted by confidence (count/total).
- Run: `python find_strongs_equiv.py` (default thresholds: min 3 co-occurrences, min 50% confidence). Output also saved to `strongs_equiv_report.txt`.
- **Key Greek findings** (all now in `STRONG_EQUIV`):

  | KJV | TAGNT | Confidence | Verses | Reason |
  |-----|-------|-----------|--------|--------|
  | G1492 | G6063 | 98.5% | 259 | οἶδα "know" — STEPBible split code |
  | G3440 | G3441 | 100% | 64 | μόνον/μόνος adv vs adj |
  | G3364 | G3361 | 97.6% | 84 | strong negation οὐ μή vs μή |
  | G3187 | G3173 | 97.6% | 42 | "great" comparative μείζων vs positive μέγας |
  | G2117 | G2112 | 100% | 8 | εὐθύς/εὐθέως "straightway" |
  | G2419 | G2414 | 88.9% | 9 | Jerusalem two spellings |
  | G3700 | G3708 | 100% | 5 | ὀπτάνομαι/ὁράω "appear/see" |
  | G4119 | G4183 | 90% | 10 | πλείων/πολύς "more/many" comparative vs positive |
  | G4386 | G4387 | 100% | 4 | πρότερον/πρότερος "formerly" |

- Hebrew findings: mostly H9xxx function-word noise (particles KJV doesn't tag) — no actionable code-equivalence pairs in the Hebrew OT. `H116↔H1768` (Aramaic then/conjunction, 100%, 18 verses) is a marginal candidate but hasn't been added.
- The `STRONG_EQUIV` map in `strongs-tooltip.js` now carries all 10 pairs (G2046↔G4483 original + 9 new).

### 2026-05-23 (session 5) — search.php UX polish + grammar tooltip (OT + NT)

#### Gematria isGematria flag — complete (`web/js/search-trigger.js`)

The `isGematria` flag (introduced to route pure-integer input to `search.php?mode=gematria`) was missing from the two clear-handler paths, causing the phrase-label to re-appear after clearing a gematria value. All five points where `isStrongs` is reset now also reset `isGematria = false`: the `×` button handler, the Escape-key handler, the empty-value branch of `updateDetected`, the `doSearch` fallthrough, and the initial `syncPhraseLabel` guard.

#### Strong's links in gematria search results (`web/search.php`)

Gematria results previously showed a bare Strong's number in the table. Now the Strong's cell renders an `<a>` link styled as a hoverable `.strongs-link` with:
- **Display**: zero-padded form matching `word.strongs` column — e.g. `H0430` (not `H430`).
- **href**: `search.php?q=H0430&mode=strongs` — routes to the Strong's concordance.
- **Tooltip**: `data-strongs="H430"` (canonical unpadded key for the `strongs` DB table lookup).
- The `strongs-tooltip.js` hover tooltip fires normally on hover.

This required separating two formats that were conflated elsewhere: `$strg_key = strongs_full_code(...)` (canonical DB key, e.g. `H430`) vs `$strg_disp = prefix . strongs_display(...)` (display/href form, e.g. `H0430`).

**Bug fixed — Strong's search normalization (`web/search.php` strongs-mode block)**: `LIKE '%H430%'` does NOT match `{H0430G}` in `word.strongs`. Fixed by normalizing the input before the LIKE query: `str_pad($sm[2], 4, '0', STR_PAD_LEFT)` pads the digit portion to 4 places so `H430` → `H0430` → matches `{H0430G}`.

#### KJV verse preview tooltip on search results (`web/js/verse-tooltip.js`, new)

Hovering any `<a class="verse-ref">` link in search results (both regular and gematria modes) now pops a card showing the KJV text of that verse. Features:

- Fetches `search.php?api=kjv_verse&book=Gen&chapter=1&verse=1`, response: `{"text": "In the beginning..."}`.
- Cache per `"book:ch:v"` key; generation counter for stale-response safety (no flicker on rapid mouse-moves).
- Shows "Loading…" → KJV text + small reference label.
- Positions below/above the link, avoiding viewport overflow.
- Included in `search.php` via `<script src="js/verse-tooltip.js"></script>` (added at the bottom of both the gematria early-exit section and the main results section).

The `search.php` API handler (`?api=kjv_verse`) was added alongside the existing `?api=strongs` handler at the top of the file (before any output).

All verse reference links in search results were given `class="verse-ref" data-book="Gen" data-chapter="1" data-verse="1"` attributes to serve as the tooltip anchor.

#### Strong's click-to-search from word cells (`web/js/strongs-tooltip.js`)

The `.strongs` div in each word cell on `index.php` was already a `.strongs-link` (for hover tooltip) but clicking it did nothing. Added a `click` event handler at the bottom of `strongs-tooltip.js` that:
- Ignores `<a>` tags (already navigating on click).
- For non-`<a>` `.strongs-link` elements, reads `data-strongs` (canonical key, e.g. `H430`), pads to 4 digits (`H0430`), and navigates to `search.php?q=H0430&mode=strongs`.

`style.css` gained `cursor: pointer` on `.strongs-link` to signal clickability.

#### Grammar tag expansion tooltip (`web/js/grammar-tooltip.js`, new)

Hovering the `.grammar` div in any word cell shows a card expanding the abbreviations.

**Language detection**: `index.php` now emits `data-lang="grk"` or `data-lang="heb"` on every `.grammar` div (derived from `$lcls`). The JS reads this attribute; if absent it falls back to heuristic (all-uppercase = Greek).

**Greek (Robinson morphology)**: expands POS codes, tense/voice/mood, case/number/gender, participle vs finite vs infinitive forms, 2nd-form prefix, compound codes with ` + ` separator (e.g. `CONJ + G1437=COND`), negative particle `PRT-N`.

**Hebrew (STEPBible TAHOT — output of `format_hebrew_grammar()`)**: parses the already-formatted strings like `V-Qal-Perf-3ms` or `Conj-w | Art-h | N-ms-c`:
- **Verb** (`V-Stem-Aspect[-tail]`): stem expanded (e.g. `Hith` → Hithpael), aspect expanded (`Perf` → Perfect, `ConsecImperf` → Consec. Imperfect, etc.). Tail is smart: starts with `1/2/3` → finite pgn `[person][gender][number]`; starts with `m/f/c` → participial `[gender][number][state]` (e.g. `mpa` = Masc·Plur, `msc` = Masc·Sing·Construct).
- **Noun/Adjective** (`N/Adj[-pr|-gent]-gn[-c]`): 2-char gender+number pairs (`ms`=Masc·Sing, `fp`=Fem·Plur, `bs`=Both·Sing etc.), optional `pr`→Proper / `gent`→Gentilic prefix, optional `-c`→Construct.
- **Pronoun** (`Pro-p3ms`): 4-char pgn starting with `p`; expands person/gender/number from positions [1][2][3].
- **Suffix** (`Suf-h-p3ms`): 1-char letter then 4-char pgn — detects and expands the pgn.
- **Particles** (`Conj`, `Prep`, `Art`, `Neg`, `Adv`, `Acc`, `Inter`, `Rel`, `Cond`, etc.): just shows POS name.
- Compound morphemes (joined by ` | `) render as sections with dividers.

`style.css`: `.grammar-tooltip` block added (same card/shadow as strongs/verse tooltips). `.word-cell .grammar` gets `cursor: help`.

`index.php`: removed the unused "Click any word above for full detail" hint div and the `$all_sums` / `<details>Source-file verse summary blocks</details>` block. Added `<script src="js/grammar-tooltip.js"></script>` after `strongs-tooltip.js`.

#### `search.php` API endpoint added for Strong's lookups

`strongs-tooltip.js` fetches `?api=strongs&code=H430` for its tooltip. On `index.php` this worked fine, but gematria results are on `search.php`. The `?api=strongs` handler (identical to `index.php`'s handler) was added to the top of `search.php` so tooltips work on that page too.

#### Strong's zero-padding — definitive reference (KEY)

Three formats coexist:
- **`word.strongs` column**: zero-padded with braces and optional grammar suffix: `{H0430G}`, `{G3056}`.
- **Display / href key**: prefix + `strongs_display()` = digits stripped of leading zeros, then re-prefixed: `H0430`. Used in user-visible text and `?q=` param.
- **Canonical DB lookup key**: `strongs_full_code()` strips braces and leading zeros: `H430`. Used for `data-strongs` attribute and the `strongs` table lookup.
- **LIKE search**: the strongs-mode query uses `LIKE '%H0430%'` (4-digit padded) to match inside `{H0430G}`. `str_pad` in `search.php` normalizes any input to 4 digits before the query.

### 2026-06-01 (session 6) — search.php works in remote API mode + project moved folders

The project moved from `C:\Work\Resurrected\Claude\BibleDB\Bible Database` to `C:\Work\Resurrected\Bible Wheel Site\BibleDB`. The new layout has `scripts/import/`, `scripts/maintenance/`, `sql/schema/`, `data/raw/`, `data/processed/`, `docs/` (handoffs moved here), and `web/` (unchanged). The path-map references in earlier sessions still hold semantically but the folder names changed.

Up to this point, `search.php` short-circuited with a "Search functionality is currently disabled when using remote API mode" message in remote mode. This session makes search (and every other UI feature) work over remote API.

#### Architecture — local PHP proxy, not direct JS-to-remote

The clean pattern, now applied uniformly:

1. Browser JS always fetches **local PHP** (`localhost/bible/api.php?...`). Never the remote site directly.
2. Local PHP helpers (`bible_search_*`, `bible_strongs_lookup`, `bible_kjv_verse_clean`) check `should_use_remote_api()`. In remote mode they call `remote_api_call($endpoint, $params)` which `file_get_contents()`s the live `api.php`. In local mode they run the original SQL.
3. The live `api.php` exposes the same set of `?api=*` endpoints, runs them locally against its own DB, and returns JSON.

Why this matters: an earlier design had JS fetching the *remote URL directly* via `window.BIBLE_API_BASE = '<remote URL>'`. This breaks on cross-origin fetches (CORS error from `strongs-tooltip.js`, `dropdowns.js`, viewcount). The local-proxy pattern sidesteps CORS and reuses the dispatch logic that already exists in `db.php`.

#### Files added / changed

**New file: `web/search_lib.php`** — Two helpers extracted from `search.php`:
- `bible_search_gematria(int $value): array` — calls the `GetGematriaWords` stored proc, groups by `text_search`, dedupes (book,ch,v), caps at 6000 occurrences. Returns `['groups', 'truncated', 'form_count', 'total_occ']`. In remote mode, delegates to `remote_api_call('search_gematria', ['value' => $value])`.
- `bible_search_verses(string $mode, string $q_raw, string $lang): array` — handles Strong's / text / phrase / English-KJV-phrase modes. Returns `['rows', 'truncated', 'not_found', 'norms', 'error'?]`. In remote mode, delegates to `remote_api_call('search_verses', ...)`.

Both helpers hold the formerly-private `search_escape_like()` and `search_normalize_query()` (renamed from `escape_like` / `normalize_query` to avoid name collisions).

**`web/db.php`** —
- `bible_strongs_lookup($code)` now actually calls `remote_api_call('strongs', ['code' => $code])` in remote mode. Previously it returned `null` unconditionally, which silently broke all Strong's tooltips and the search.php Strong's-validation step.
- New `bible_kjv_verse_clean($osis, $ch, $v): ?string` returns the tag-stripped KJV text for one verse, with remote delegation. Used by the `verse-tooltip.js` API path.
- `get_api_base()` rewritten to always return `''`. **This is the CORS fix.** Previously it returned the live URL in remote mode, which `index.php` then emitted into `window.BIBLE_API_BASE` — causing every `${base}/api.php` fetch (strongs tooltip, dropdowns, viewcount) to go cross-origin and 403/CORS-fail. Now JS always falls back to `/bible` (relative) and hits the local PHP proxy.

**`web/api.php`** — Three new endpoints:
- `?api=kjv_verse&book=X&chapter=N&verse=N` → `{"text": "..."}` (or `{"text": null}`).
- `?api=search_gematria&value=N` → `{"groups": [...], "truncated": bool, "form_count": int, "total_occ": int}`.
- `?api=search_verses&mode=...&q=...&lang=...` → `{"rows": [...], "truncated": bool, "not_found": bool, "norms": [...]}`.
Also: `require` → `require_once` for `db.php`, `book_aliases.php`, `search_lib.php`, and `search.php` does the same for `db.php`, `helpers.php`, `search_lib.php`. Reason: on Windows with mixed `\` and `/` path separators from `__DIR__`, plain `require` of `db.php` from one file plus `require_once` from another file occasionally fails to dedupe, triggering "Cannot redeclare function `bible_pdo`" fatals in remote mode.

**`web/remote_api.php`** — Four wrapper functions for the new endpoints: `remote_bible_strongs_lookup()`, `remote_bible_kjv_verse_clean()`, `remote_bible_search_gematria()`, `remote_bible_search_verses()`. The dispatching code in `db.php` / `search_lib.php` calls `remote_api_call(...)` directly rather than going through these wrappers; both styles coexist. The wrappers exist for consistency with the older `remote_bible_*` set.

**`web/search.php`** — Removed the early-exit `"Search functionality is currently disabled..."` block (lines 13–17 of the prior version). Replaced the gematria stored-proc + grouping block (~60 lines) with one call to `bible_search_gematria()`. Replaced the verse-search SQL builder + execution block (~170 lines) with one call to `bible_search_verses()`. The `?api=kjv_verse` handler at the top of the file now uses `bible_kjv_verse_clean()` instead of querying `bible_pdo()` directly. All HTML rendering is unchanged — the helper return shapes are designed to feed the existing renderer.

#### Deployment for remote API mode

For remote mode to work on a local box, **both** the local and the remote (live) site need the new PHP files. The minimum live upload is `web/search_lib.php`, `web/api.php`, `web/db.php`. The live's `config.php` keeps `use_remote_api => false`; only the developer's local config sets `use_remote_api => true`.

#### Gotchas / debugging tips for next time

- **CORS error from `strongs-tooltip.js` or similar**: check `web/db.php` → `get_api_base()`. It must return `''` (or anything same-origin). If it returns the remote URL, JS will cross-origin-fetch and fail. We tried that design and walked away from it.
- **"Cannot redeclare function `bible_pdo`"**: a file in the include chain is using plain `require` instead of `require_once`. Convert it. Affects api.php, search.php, els.php, index.php, stats.php — only api.php and search.php were converted this session; the rest haven't manifested the bug yet but probably should be converted too for safety.
- **Search returns empty rows in remote mode but no errors**: the remote `api.php` doesn't have the new endpoints yet. Upload `web/search_lib.php` + `web/api.php` to the live site.
- **Live api.php returns `{"error": "unknown api"}`** for `search_gematria` etc.: same — old api.php is still deployed live.
- **Sanity URLs for the proxy chain** (replace `H430` / `value=37` as needed):
  - `https://biblewheel.com/bible/api.php?api=strongs&code=H430` — live should return the row directly.
  - `http://localhost/bible/api.php?api=strongs&code=H430` — local in remote mode should return the same row, proxied through.

#### Schema / DB note — partial-schema recovery

While bringing up the new folder, the local `stepbible` DB was found to be missing six tables: `word_edition`, `word_alt_strong`, `word_morpheme`, `word_link`, `variant`, `variant_edition`. These are exactly the first six `DROP TABLE IF EXISTS` lines in `sql/schema/schema.sql`, suggesting an aborted `--create-schema` run had dropped them without re-CREATEing. The live `biblewhe_stepbible` still had them. Recovery path that worked: `mysqldump` just those six tables from the live DB, then `Get-Content tables.sql | mysql -u root -p stepbible` locally (PowerShell doesn't support `<` redirection; use `Get-Content | mysql` or `cmd /c "mysql ... < file.sql"`).

A full rebuild via `import_bible.py --create-schema --with-gematria` would also work but would drop `bible_kjv`, `bible_na27`, `bible_scr`, `greek`, `hebrew`, `p_variants_import`, `verse_views` — none of which have re-importers in `scripts/import/`. Those were originally imported by tools outside the current repo. If you ever do a full rebuild, you'll need to re-source those tables from elsewhere (or, again, mysqldump them off the live first).

#### Follow-up — els.php proxy + stats.php friendly disable

After the initial session-6 work, two secondary pages still hit `bible_pdo()` directly and would 500 in remote mode. Both now handled:

**`web/els.php` — full remote proxy** (matches the pattern used for search):
- Extracted `els_strip()` and `els_fetch()` into new `web/els_lib.php`. `els_letter_value()` stays in `els.php` (used only locally by the in-page gematria display).
- `els_fetch()` checks `should_use_remote_api()` and delegates to `remote_api_call('els_fetch', [...])` in remote mode.
- Added `?api=els_fetch&book=...&chapter=...&verse=...&edition=...&letters=...` endpoint to `api.php`, plus a `remote_els_fetch()` wrapper in `remote_api.php` for symmetry with the rest of the remote_* helpers.
- `els.php` now `require_once`s the four core libs (db, book_aliases, helpers, els_lib).

**`web/stats.php` — friendly disable**:
- Added an early `should_use_remote_api()` guard. Renders a minimal page saying view counts are private per-instance and exits before any DB call.
- This matches the existing `?api=viewcount` privacy policy (returns 0/0 in remote mode).
- Also switched the requires to `require_once` for consistency.

For remote-mode users, the upload set is now `api.php`, `db.php`, `search_lib.php`, `els_lib.php` (any time those change on local). `stats.php` is local-only — the friendly-disable path is hit only by the developer's machine. `remote_api.php` is also only used by remote-mode local sites, but uploading it doesn't hurt.

#### Follow-up — make every URL work at any deploy path (`/bible/` *or* root)

The web UI used to assume Apache/IIS was serving it under `/bible/`. Hard-coded `/bible/...` URLs in the sidebar, stylesheet links, and JS fetches all broke under `php -S localhost:8080` (which serves the `web/` folder at the origin root). Fix: relativise everything, centralise layout decisions in helpers.

**New helpers in `web/helpers.php`** (single source of truth for the standalone-vs-biblewheel layout split):

- `bible_is_local_layout(): bool` — cached `file_exists()` check for `../include/bwHeader.inc`. True when the external biblewheel.com includes aren't present.
- `bible_render_layout_header(): void` — call before `<html>`. Emits either `local_header.inc.php` (standalone) or `bwHeader.inc` (production).
- `bible_render_layout_banner(): void` — call as first thing inside `<body>`. Same logic, swaps `local_banner.inc.php` ↔ `bwBanner.php`.
- `bible_render_layout_styles(): void` — call inside `<head>`. In production, emits the absolute `/include/bw.css` link (biblewheel-shared) plus the local stylesheet. In standalone, emits only the local stylesheet. The local stylesheet href is always relative (`style.css?v=<mtime>`) so it works at any path.

**Pages refactored to use the helpers** (replacing 6–8 lines of inline `$use_local_layout` conditional + hard-coded `<link>` tags per page): `index.php`, `search.php` (both layout blocks — gematria and main results), `els.php`, `stats.php` (both — remote-disabled page and main page), `numbers.php` (also gained `require_once helpers.php`, which it was missing).

**`bible_sidebar.php`** — sidebar `<a href="/bible/x.php">` links → relative `<a href="x.php">`. Works because the sidebar is included from sibling pages, so relative resolves correctly at any deploy path.

**JS fetches** — `strongs-tooltip.js`, `dropdowns.js`, and the inline viewcount refresh in `index.php` now use relative `api.php?...` URLs (was `${base}/api.php`). The `window.BIBLE_API_BASE` JS global and the PHP `get_api_base()` function it sourced from are both removed — they were dead code after the CORS-era pivot.

**Result**: the site now works under all four deploy modes with zero configuration:
- Apache/IIS at `/bible/` — production layout (biblewheel includes), `/bible/style.css`-style cache busting.
- Apache/IIS at root — production layout, root-relative URLs.
- `php -S localhost:8080 -t web/` — standalone layout (local includes), root-relative URLs.
- `php -S localhost:8080` with `mklink /J bible web` from one level up — production-style `/bible/...` URLs, standalone or production layout depending on whether the biblewheel includes are found.

**Best-practices outcome**: the `$use_local_layout` boolean and the hard-coded `/bible/...` patterns are gone. Adding a new top-level page now means three helper calls instead of three nested conditionals plus stylesheet boilerplate.

#### Follow-up — NA28↔KJV versification remap (`verse_kjv_alt` table)

STEPBible's TAGNT files use NA28-style versification. Five NT verses don't line up with KJV's older numbering, so a direct KJV lookup against `bible_kjv` returns nothing (or the wrong verse):

| STEPBible (NA28) ref | KJV ref |
|----------------------|---------|
| Rev 12:18 | KJV 13:1 (cross-chapter — NA28's 12:18 simply doesn't exist in KJV) |
| Php 1:16 | KJV 1:17 (NA28 and KJV have these two verses swapped) |
| Php 1:17 | KJV 1:16 |
| 2Co 13:13 | KJV 13:14 |
| 3Jn 1:15 | KJV 1:14 |

**Source of truth**: the TAGNT files annotate every cross-tradition difference inline — every summary header that needs a remap reads `# Ref [KJV X.Y]` (e.g. `# Rev.12.18 [KJV 13.1a]`). The 39 annotations across both TAGNT files reduce to 5 once we filter out the `a`/`b` partial-verse cases where the KJV verse number still exists.

**Build/refresh**: `python scripts/maintenance/fix_kjv_versification.py`
- Auto-discovers anomalies from the TAGNT source files; nothing hard-coded.
- Idempotent: drops + re-CREATEs `verse_kjv_alt` on each run.
- Tiny table (5 rows): `(book_id, na28_chapter, na28_verse, kjv_chapter, kjv_verse)` with `(book_id, na28_chapter, na28_verse)` PK.
- `--dry-run` flag prints what would be inserted without touching the DB.

**Web wiring** — three KJV-lookup functions in `web/db.php` now check `verse_kjv_alt` whenever the direct hit returns null:
- `kjv_verse_text($book_id, $chapter, $verse)` — used by `index.php` for the assembled English line.
- `kjv_verse_order($book_id, $chapter, $verse)` — used wherever Verse_Order indexing matters.
- `bible_kjv_verse_clean($osis, $chapter, $verse)` — used by `search.php`'s verse-tooltip endpoint.

Plus `web/els_lib.php`'s KJV ELS path uses the same lookup for the starting verse so an ELS run beginning at Rev 12:18 works correctly.

The lookup is implemented by one shared helper `kjv_alt_ref($book_id, $chapter, $verse)` that loads the whole tiny table once into a static cache. If `verse_kjv_alt` is missing (e.g. the maintenance script hasn't been run yet), the helper degrades silently and direct lookups continue to work as before — no error, just no remapping.

**Remote API mode**: works transparently. The local PHP proxies to the live `api.php`, which runs the same `bible_kjv_verse_clean()` against its own DB (with its own `verse_kjv_alt`). Just make sure the live deployment also runs `fix_kjv_versification.py` after any DB rebuild.

**Adding more anomalies later**: nothing to write. If a future STEPBible revision adds new `[KJV X.Y]` annotations, just re-run the script — it picks them up automatically.
