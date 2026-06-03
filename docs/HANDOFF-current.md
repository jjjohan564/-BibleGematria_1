# Current Handoff — BibleDB (as of 2026)

**This is the recommended document for anyone picking up the project now.**

The original `HANDOFF.md` contains a lot of historical session notes. This file focuses on the current state, conventions, and the easiest ways to work with the project.

---

## Core Principle: Single Source of Truth for Database Name

**The database name has one and only one source:**

- `BIBLE_DB_NAME` environment variable (required)

It is **never** read from `config.ini`.

This was made strict so you can easily target different databases (e.g. `stepbible` for production work, `stepbibletest` for clean testing) without editing files.

**Example (for creating the real "stepbible" database):**
Use the new orchestrator for the full pipeline (recommended for normal use):

```powershell
$env:BIBLE_DB_NAME = "stepbible"
python scripts/run_pipeline.py --db-name stepbible
```

It runs the 7 steps in order (import + SQL dumps for editions + gematria compute + unicode + edition text/diff + search columns + KJV versification fix), with resume support, preflight checks, self-healing migrations, and a safety prompt if the DB has data.

For a quick test or single step, you can still run individual scripts (e.g. `python scripts/import/import_bible.py`), but they now default to full schema + gematria creation.

When the target database already contains data, the relevant script will print a warning and prompt exactly as:
"Selected database has data. It will be erased and replaced. Continue? (Y/N)"
This makes the process safe and simple for others to use right out of the box (no extra parameters or manual cleanup required for the common case).

**Critical PowerShell gotcha:** `$env:FOO = "bar"` only affects the **current PowerShell window** and programs you launch from it. Open a new terminal or restart PowerShell and the variable is gone.

There is a helper that makes this easy and also shows you the persistent command:

```powershell
# Session only (what you will use 95% of the time)
.\scripts\set-bible-db.ps1 -Name stepbibletest

# Make it survive new shells (writes to your user profile)
.\scripts\set-bible-db.ps1 -Name stepbibletest -Persist
# Then close this window and open a fresh one.
```

After using `-Persist` you must start a **new** PowerShell instance before Python (or the scripts) will see the value.

You can always check what the current process sees with:
```powershell
$env:BIBLE_DB_NAME
```

Every script that connects to the database now prints a live verification:

```
✓ Server reports current database: stepbibletest
✓ Confirmed: connection is using the resolved database name.
```

If the verification ever shows a mismatch, something is wrong with how the connection was obtained.

---

## Easiest Way to Create the stepbible Database (out-of-the-box for others)

```powershell
# 1. Create a clean empty database (or use an existing empty one)
mysql -u root -p -e "DROP DATABASE IF EXISTS stepbible; 
                     CREATE DATABASE stepbible 
                     CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 2. Point the scripts at it (use the helper for convenience + guidance)
.\scripts\set-bible-db.ps1 -Name stepbible
# (or for one-liner:  $env:BIBLE_DB_NAME="stepbible" )

# 3. Run the full pipeline (recommended).
#    It will create/refresh everything, warn/prompt if data exists, and remind you about web/config.php at the end.
python scripts/run_pipeline.py --db-name stepbible
```

This is the recommended "just works" path. No manual cleanup or extra flags needed for normal use or re-runs. The advanced flags (`--limit-verses`, `--dry-run`, `--truncate`) are kept only for development/debugging.

---

## Current Recommended Pipeline Order

For a complete fresh database (using `stepbible` as the example name):

```powershell
python scripts\run_pipeline.py --db-name stepbible
```

That single command:

- creates the target database (utf8mb4) if it doesn't exist yet
  (existing databases are left untouched; `import_bible.py` prompts before
  clobbering if there's data),
- runs all seven steps in order,
- streams output to the terminal and tees to `logs/pipeline-YYYYMMDD-HHMMSS.log`,
- stops on the first failure and prints a summary of what completed.

That's it. The orchestrator handles:

```
[1/7]  import_bible.py                STEPBible schema + TAHOT/TAGNT load
[2/7]  bible_na27.sql + bible_scr.sql + bible_kjv.sql
                                      External reference text dumps
                                      (must be present in data/raw/)
[3/7]  compute_gematria.py            gematria_word + gematria_verse
[4/7]  populate_verseunicode.py       decode BibleWorks transliteration
[5/7]  build_edition_verse_text.py
       diff_editions.py               Phase 3 variant emission
[6/7]  add_text_search.py
       add_verse_search.py            phrase-search columns
[7/7]  fix_kjv_versification.py       verse_kjv_alt mapping (Rev 12:18 etc.)
```

`--db-name` is REQUIRED — no env-var fallback. If `BIBLE_DB_NAME` is set in
your shell to a different value, the orchestrator prints a warning so a
stale env var doesn't silently route the build at the wrong DB. The flag's
value is then propagated to every child via the subprocess environment, so
`_db.py`'s env-var contract continues to work downstream.

Useful flags:

```powershell
python scripts\run_pipeline.py --db-name stepbibletest --dry-run   # preview
python scripts\run_pipeline.py --db-name stepbible --force         # auto-yes to clobber-prompt
python scripts\run_pipeline.py --db-name stepbible --skip diff_editions  # debug
```

### Optional extras (run after the pipeline)

- **LXX-Rahlfs**: `python scripts\import\import_lxx.py` — loads `book_lxx`,
  `verse_lxx`, `word_lxx` (see `web/HANDOFF.md` § 12).
- **Diagnostic / cleanup scripts** in `scripts/maintenance/`:
  `cleanup_stale_variants.py`, `cleanup_hebrew_variants.py`,
  `find_strongs_equiv.py`, `fix_strongs_primary.py`. Run individually as
  needed; they are not part of a standard rebuild.

### Where the SQL dumps come from

`data/raw/bible_na27.sql`, `bible_scr.sql`, and `bible_kjv.sql` are mysqldump
exports of the corresponding tables from a fully-populated reference instance
(e.g., the live `biblewhe_stepbible` database). They never change once
captured. If you need to regenerate them after a content update on the live
side:

```bash
mysqldump -u USER -p biblewhe_stepbible bible_na27 > data/raw/bible_na27.sql
mysqldump -u USER -p biblewhe_stepbible bible_scr  > data/raw/bible_scr.sql
mysqldump -u USER -p biblewhe_stepbible bible_kjv  > data/raw/bible_kjv.sql
```

The advanced flags on `import_bible.py` (`--limit-verses`, `--dry-run`, `--truncate`) are only for development and debugging. Normal users invoke the orchestrator and never run `import_bible.py` directly.

Most steps are idempotent and safe to re-run.

---

## Current Folder Structure

```
BibleDB/
├── data/
│   ├── raw/                    # STEPBible source files + SQL dumps
│   │   ├── TAHOT *.txt         # 4 files (Hebrew OT)
│   │   ├── TAGNT *.txt         # 2 files (Greek NT)
│   │   ├── bible_na27.sql      # NA27 critical text dump
│   │   ├── bible_scr.sql       # Scrivener TR dump
│   │   ├── bible_kjv.sql       # KJV English (with inline Strong's) dump
│   │   └── LXX/                # LXX-Rahlfs source (optional)
│   └── processed/
├── docs/
│   ├── HANDOFF.md              # Historical / detailed session notes (older)
│   └── HANDOFF-current.md      # ← You are here (recommended)
├── logs/                       # Pipeline run logs (auto-created; gitignored)
├── scripts/
│   ├── _db.py                  # Shared connection helpers
│   ├── run_pipeline.py         # ← Orchestrator (the one command)
│   ├── set-bible-db.ps1        # PowerShell helper to set BIBLE_DB_NAME
│   ├── import/
│   │   ├── import_bible.py
│   │   ├── compute_gematria.py
│   │   ├── populate_verseunicode.py
│   │   ├── build_edition_verse_text.py
│   │   ├── diff_editions.py
│   │   └── import_lxx.py       # optional extra
│   └── maintenance/
│       ├── add_text_search.py
│       ├── add_verse_search.py
│       ├── fix_kjv_versification.py
│       ├── cleanup_*.py
│       └── find_strongs_equiv.py
├── sql/schema/
│   ├── schema.sql              # Core 11 tables + view
│   ├── gematria_schema.sql     # gematria_word + gematria_verse
│   └── lxx_schema.sql          # LXX tables (optional)
├── config.ini.sample
├── config.ini                  # (gitignored)
└── web/                        # PHP UI (has its own HANDOFF.md)
```

---

## Key Improvements Made Recently

- **Single-command orchestrator** (`scripts/run_pipeline.py`): seven steps with preflight checks, live + tee'd logging, and a stop-on-failure summary.
- **NA27, Scrivener TR, and KJV come from SQL dumps** in `data/raw/` — no external DB dependency. The old DB-to-DB importer (`import_bw_bibles.py`) has been removed.
- Database name is now **strictly** from `BIBLE_DB_NAME` (single source of truth) for individual scripts, and from `--db-name` (no env fallback) for the orchestrator.
- The import script always ensures core schema + gematria tables (with safety prompt on data) as part of creating a clean database.
- Schema loading from Python is now robust:
  - Strips hard-coded `CREATE DATABASE` / `USE` statements
  - Uses `SET FOREIGN_KEY_CHECKS` during drops
  - Works with both pymysql and mariadb connector
- Every database connection prints a live `SELECT DATABASE()` verification.

---

## When to Use the Old HANDOFF.md

Keep using `docs/HANDOFF.md` if you need deep historical context, rationale from specific sessions, or details about one-off scripts and variant cleanup work.

For day-to-day work or onboarding, prefer this file (`HANDOFF-current.md`).

---

## Quick Commands

| Goal | Command |
|---|---|
| Build the full DB end-to-end | `python scripts\run_pipeline.py --db-name stepbible` |
| Preview without running | `python scripts\run_pipeline.py --db-name stepbibletest --dry-run` |
| Force-clobber re-run | `python scripts\run_pipeline.py --db-name stepbible --force` |
| Skip one step (debug) | `python scripts\run_pipeline.py --db-name stepbible --skip diff_editions` |
| Add the LXX (optional) | `python scripts\import\import_lxx.py` |
| See what DB you're using | Any single script prints a live `SELECT DATABASE()` verification on connect |

---

**Last major update:** Added `scripts/run_pipeline.py` orchestrator. NA27, Scrivener TR, and KJV now load from SQL dumps in `data/raw/` (the old `import_bw_bibles.py` was removed). `fix_kjv_versification.py` handles the five NA28↔KJV verse-numbering anomalies (Rev 12:18, Php 1:16/1:17, 2Co 13:13, 3Jn 1:15).