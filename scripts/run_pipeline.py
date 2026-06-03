#!/usr/bin/env python3
"""
run_pipeline.py — orchestrate the full STEPBible database build.

Runs the seven steps required to build a fully-functional Bible database
from the STEPBible source files (data/raw/TAGNT*.txt, TAHOT*.txt) plus
the three SQL dumps (bible_na27.sql, bible_scr.sql, bible_kjv.sql).

The LXX pipeline is intentionally NOT included — `import_lxx.py` is an
optional add-on (see the README).

Pipeline order
--------------
    [1/7]  import_bible.py                STEPBible schema + TAHOT/TAGNT load
    [2/7]  bible_na27.sql + bible_scr.sql + bible_kjv.sql + strongs-mysql.sql
           SQL dump imports (editions for NA27/SCR/KJV + strongs lookup for tooltips)
    [3/7]  compute_gematria.py            gematria_word + gematria_verse
    [4/7]  populate_verseunicode.py       decode BibleWorks transliteration
    [5/7]  build_edition_verse_text.py
           diff_editions.py               Phase 3 variant emission
    [6/7]  add_text_search.py
           add_verse_search.py            phrase-search column population
    [7/7]  fix_kjv_versification.py       verse_kjv_alt mapping

DB-name handling
----------------
`--db-name NAME` is REQUIRED — there is no env-var fallback.

Resume support (log-based)
--------------------------
Each pipeline run writes a log to logs/pipeline-<db-name>-YYYYMMDD-HHMMSS.log.
As each step completes (or is skipped because a prior run finished it), the
orchestrator appends a STEP_COMPLETE marker line to the log.

On the next run the orchestrator finds the most-recent log file for the db that
actually contains markers (skipping "empty" logs produced by --dry-run or by
the "already complete" short-circuit) and skips the steps marked done.

Prior log state is ignored if --create-db actually created the DB this run,
or if --rerun-all / --rerun-from is used.

Override with --rerun-all (ignore log entirely) or --rerun-from STEP (force
STEP and everything after to run; everything before is treated as done).

Self-healing schema migrations run every invocation (idempotent). Ensures:
variant.position column, verse_views table + record_verse_view proc (for
view counters), GetGematriaWords proc (for local gematria searches).

After a successful run, the script prints a reminder to sync web/config.php
'database' key (and use_remote_api=false) so the browser UI is not blank/empty.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Set


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
DATA_RAW     = PROJECT_ROOT / "data" / "raw"
LOGS_DIR     = PROJECT_ROOT / "logs"

sys.path.insert(0, str(SCRIPTS_ROOT))
from _db import load_config  # noqa: E402


STEP_MARKER_PREFIX = ">>> STEP_COMPLETE:"
STEP_MARKER_RE = re.compile(
    rf"^{re.escape(STEP_MARKER_PREFIX)}\s+(?P<db>\S+)\s+::\s+(?P<step>\S+)\s*$"
)


# ---------------------------------------------------------------------------
# Step definitions
# ---------------------------------------------------------------------------

@dataclass
class Step:
    name: str
    label: str
    script: Optional[Path] = None
    extra_args: List[str] = field(default_factory=list)


def _script(*parts: str) -> Path:
    return SCRIPTS_ROOT.joinpath(*parts)


PIPELINE: List[List[Step]] = [
    [Step(name="import_bible", label="import_bible.py",
          script=_script("import", "import_bible.py"))],
    [Step(name="sql_dumps",
          label="SQL dump imports (bible_na27, bible_scr, bible_kjv + strongs lookup)")],
    [Step(name="compute_gematria", label="compute_gematria.py",
          script=_script("import", "compute_gematria.py"))],
    [Step(name="populate_verseunicode", label="populate_verseunicode.py",
          script=_script("import", "populate_verseunicode.py"))],
    [
        Step(name="build_edition_verse_text", label="build_edition_verse_text.py",
             script=_script("import", "build_edition_verse_text.py")),
        Step(name="diff_editions", label="diff_editions.py",
             script=_script("import", "diff_editions.py")),
    ],
    [
        Step(name="add_text_search", label="add_text_search.py",
             script=_script("maintenance", "add_text_search.py")),
        Step(name="add_verse_search", label="add_verse_search.py",
             script=_script("maintenance", "add_verse_search.py")),
    ],
    [Step(name="fix_kjv_versification", label="fix_kjv_versification.py",
          script=_script("maintenance", "fix_kjv_versification.py"))],
]


STEPBIBLE_GLOBS = [
    ("TAHOT Gen-Deu", "TAHOT Gen-Deu*.txt"),
    ("TAHOT Jos-Est", "TAHOT Jos-Est*.txt"),
    ("TAHOT Job-Sng", "TAHOT Job-Sng*.txt"),
    ("TAHOT Isa-Mal", "TAHOT Isa-Mal*.txt"),
    ("TAGNT Mat-Jhn", "TAGNT Mat-Jhn*.txt"),
    ("TAGNT Act-Rev", "TAGNT Act-Rev*.txt"),
]

REQUIRED_DUMPS = ["bible_na27.sql", "bible_scr.sql", "bible_kjv.sql"]


# ---------------------------------------------------------------------------
# CLI + DB-name handling
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--db-name", required=True,
                    help="REQUIRED. Target database name. No env-var fallback.")
    ap.add_argument("--config", default=str(PROJECT_ROOT / "config.ini"),
                    help="Path to config.ini (default: project root)")
    ap.add_argument("--force", action="store_true",
                    help="Auto-yes to import_bible.py's 'DB has data' prompt.")
    ap.add_argument("--rerun-all", action="store_true",
                    help="Ignore previous-log state; run every step.")
    ap.add_argument("--rerun-from", metavar="STEP",
                    help="Force re-run starting at named step. Everything before is treated as done.")
    ap.add_argument("--skip", action="append", default=[], metavar="NAME",
                    help="Skip a step by name (repeatable; for debugging).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Run preflight + load log state; print plan; do nothing else.")
    ap.add_argument("--log-file", default=None,
                    help="Override the auto-generated log path.")
    return ap.parse_args(argv)


def resolve_db_name(args: argparse.Namespace, log: Optional[Callable[[str], None]] = None) -> str:
    def _log(msg: str):
        if log:
            log(msg)
        else:
            print(msg)
    name = args.db_name.strip()
    if not name:
        _log("ERROR: --db-name cannot be empty.")
        sys.exit(2)
    env_val = (os.environ.get("BIBLE_DB_NAME") or "").strip()
    if env_val and env_val != name:
        _log(f"⚠ WARNING: BIBLE_DB_NAME is set in your shell to '{env_val}'")
        _log(f"            but --db-name says '{name}'.")
        _log(f"            The pipeline will use '{name}' (the flag wins).")
        _log("")
    return name


# ---------------------------------------------------------------------------
# Create the target DB if missing
# ---------------------------------------------------------------------------

def _server_connect(cfg: dict):
    common = dict(host=cfg["host"], port=int(cfg["port"]),
                  user=cfg["user"], password=cfg["password"])
    try:
        import mariadb  # type: ignore
        return mariadb.connect(**common)
    except Exception:
        pass
    import pymysql  # type: ignore
    return pymysql.connect(charset="utf8mb4", **common)


def create_database_if_missing(db_name: str, cfg_path: Path, log, dry_run: bool = False) -> Optional[bool]:
    """Returns True if DB already existed, False if newly created, None on failure.
    If dry_run, only checks existence; never creates.
    """
    os.environ["BIBLE_DB_NAME"] = db_name
    try:
        cfg = load_config(cfg_path)
    except Exception as e:
        log(f"  ✗ Could not read config: {e}")
        return None
    log(f"Ensuring database '{db_name}' exists (utf8mb4)...")
    try:
        conn = _server_connect(cfg)
    except Exception as e:
        log(f"  ✗ Server-level connect failed: {e}")
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
            (db_name,),
        )
        existed = cur.fetchone() is not None
        if dry_run:
            if existed:
                log(f"  ✓ (dry-run) database '{db_name}' already exists.")
            else:
                log(f"  ✓ (dry-run) database '{db_name}' does not exist (would create).")
            return existed
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
            f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        conn.commit()
        if existed:
            log(f"  ✓ database '{db_name}' already exists — left untouched.")
            return True
        log(f"  ✓ database '{db_name}' created (fresh — prior log state will be ignored).")
        return False
    except Exception as e:
        log(f"  ✗ CREATE DATABASE failed: {e}")
        return None
    finally:
        try: conn.close()
        except Exception: pass


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def preflight(db_name: str, cfg_path: Path, args, log, dry_run: bool = False, db_existed: bool = True) -> Optional[dict]:
    log("Preflight checks...")
    missing: List[str] = []
    if not cfg_path.exists():
        missing.append(f"config.ini not found at {cfg_path}")
    else:
        log(f"  ✓ config.ini found at {cfg_path}")

    for label, pattern in STEPBIBLE_GLOBS:
        hits = sorted(DATA_RAW.glob(pattern))
        if not hits:
            missing.append(f"STEPBible file matching '{pattern}' not in data/raw/")
        else:
            log(f"  ✓ {label}: {hits[0].name}")

    for fname in REQUIRED_DUMPS:
        p = DATA_RAW / fname
        if not p.exists():
            missing.append(f"SQL dump not found: data/raw/{fname}")
        else:
            log(f"  ✓ {fname} ({p.stat().st_size:,} bytes)")

    # strongs lookup table (for tooltips and search validation)
    strongs_sql = PROJECT_ROOT / "sql" / "schema" / "strongs-mysql.sql"
    if not strongs_sql.exists():
        missing.append(f"strongs lookup SQL not found: {strongs_sql}")
    else:
        log(f"  ✓ strongs-mysql.sql ({strongs_sql.stat().st_size:,} bytes)")

    for group in PIPELINE:
        for step in group:
            if step.script and not step.script.exists():
                missing.append(f"script missing: {step.script.relative_to(PROJECT_ROOT)}")

    known = {s.name for grp in PIPELINE for s in grp}
    for s in args.skip:
        if s not in known:
            missing.append(f"--skip '{s}' is not a known step name. Known: {', '.join(sorted(known))}")
    if args.rerun_from and args.rerun_from not in known:
        missing.append(f"--rerun-from '{args.rerun_from}' is not a known step name. Known: {', '.join(sorted(known))}")

    cfg = None
    try:
        os.environ["BIBLE_DB_NAME"] = db_name
        cfg = load_config(cfg_path)
        if not (dry_run and not db_existed):
            from _db import get_connection
            conn, _ = get_connection(cfg)
            cur = conn.cursor()
            cur.execute("SELECT DATABASE()")
            actual = cur.fetchone()[0]
            cur.close(); conn.close()
            if actual != cfg["database"]:
                missing.append(f"DB live-verify mismatch (server reports '{actual}' but we expected '{db_name}')")
        else:
            log("  ✓ (dry-run on fresh DB) skipping live DB connect/verify")
    except SystemExit:
        missing.append("could not connect to MariaDB (no driver?). See _db.py error above.")
    except Exception as e:
        missing.append(f"DB connection check failed: {e}")

    if missing:
        log("")
        log("✗ Preflight FAILED:")
        for m in missing:
            log(f"  - {m}")
        return None
    log("  ✓ All preflight checks passed.")
    return cfg


# ---------------------------------------------------------------------------
# Schema migrations (idempotent self-healing)
# ---------------------------------------------------------------------------

def ensure_schema_migrations(cfg: dict, log) -> bool:
    """Apply idempotent schema migrations on top of the current DB.
    Handles: variant.position, verse_views table + record_verse_view proc,
    GetGematriaWords proc (for local gematria search), plus self-heal of
    word.strongs_primary for compound tags so gematria results show the
    correct (lexical) Strong's number.
    Returns True on success."""
    from _db import get_connection
    log("Schema migrations (idempotent)...")
    try:
        conn, _ = get_connection(cfg)
    except Exception as e:
        log(f"  ✗ Could not open connection for migrations: {e}")
        return False
    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            " WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'variant' "
            "   AND COLUMN_NAME = 'position'",
            (cfg["database"],),
        )
        has_position = (cur.fetchone()[0] or 0) > 0

        if not has_position:
            log("  - variant.position column missing — adding now ...")
            cur.execute("ALTER TABLE variant ADD COLUMN position DECIMAL(6,2) NOT NULL DEFAULT 0")
            cur.execute("ALTER TABLE variant ADD KEY idx_variant_position (word_id, position)")
            cur.execute("UPDATE variant v JOIN word w ON w.id = v.word_id SET v.position = w.position")
            conn.commit()
            log(f"    ✓ added variant.position + index; backfilled "
                f"{cur.rowcount:,} variant row(s) from word.position.")
        else:
            cur.execute(
                "SELECT COUNT(*) FROM variant v "
                " WHERE v.position = 0 "
                "   AND EXISTS (SELECT 1 FROM word w WHERE w.id = v.word_id AND w.position > 0)"
            )
            unset = cur.fetchone()[0] or 0
            if unset > 0:
                log(f"  - variant.position present but {unset:,} row(s) "
                    f"still at DEFAULT 0 — backfilling ...")
                cur.execute(
                    "UPDATE variant v JOIN word w ON w.id = v.word_id "
                    "  SET v.position = w.position WHERE v.position = 0"
                )
                conn.commit()
                log(f"    ✓ backfilled {cur.rowcount:,} variant row(s).")
            else:
                log("  ✓ variant.position already present and populated.")

        # Ensure verse_views table (for page view counters in index/stats/api)
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.TABLES "
            " WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'verse_views'",
            (cfg["database"],),
        )
        has_views = (cur.fetchone()[0] or 0) > 0
        if not has_views:
            log("  - verse_views table missing — creating ...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS verse_views (
                    book_code  VARCHAR(10) NOT NULL,
                    chapter    INT NOT NULL,
                    verse      INT NOT NULL,
                    view_count INT NOT NULL DEFAULT 0,
                    PRIMARY KEY (book_code, chapter, verse)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            conn.commit()
            log("    ✓ created verse_views table")

        # Ensure record_verse_view proc (called by index.php record_verse_view etc.)
        log("  - ensuring record_verse_view procedure ...")
        cur.execute("DROP PROCEDURE IF EXISTS record_verse_view")
        cur.execute("""
            CREATE PROCEDURE record_verse_view(
                IN p_book VARCHAR(20),
                IN p_chapter INT,
                IN p_verse INT,
                OUT p_verse_count INT,
                OUT p_total INT
            )
            BEGIN
                INSERT INTO verse_views (book_code, chapter, verse, view_count)
                VALUES (p_book, p_chapter, p_verse, 1)
                ON DUPLICATE KEY UPDATE view_count = view_count + 1;
                SELECT view_count INTO p_verse_count 
                  FROM verse_views 
                 WHERE book_code = p_book AND chapter = p_chapter AND verse = p_verse;
                SELECT COALESCE(SUM(view_count), 0) INTO p_total FROM verse_views;
            END
        """)
        conn.commit()
        log("    ✓ record_verse_view procedure ensured")

        # Ensure GetGematriaWords proc for local-mode gematria search (?mode=gematria)
        # (remote mode bypasses this via API proxy)
        log("  - ensuring GetGematriaWords procedure ...")
        cur.execute("DROP PROCEDURE IF EXISTS GetGematriaWords")
        cur.execute("""
            CREATE PROCEDURE GetGematriaWords(IN p_val INT)
            BEGIN
                SELECT 
                    w.book_id,
                    v.chapter,
                    v.verse,
                    w.text_search,
                    w.text_original,
                    w.transliteration,
                    w.translation,
                    w.strongs_primary,
                    w.language
                FROM gematria_word gw
                JOIN word w ON w.id = gw.word_id
                JOIN verse v ON v.id = w.verse_id
                WHERE gw.standard = p_val
                ORDER BY w.book_id, v.chapter, v.verse, w.position;
            END
        """)
        conn.commit()
        log("    ✓ GetGematriaWords procedure ensured")

        # Self-heal strongs_primary for compound dStrongs tags (e.g. H9003/{H7225G}).
        # Older importer took the first match (the prefix); gematria search (and
        # strongs_primary consumers) should show the lexical form inside {} .
        # The parser fix + this healer makes both fresh and pre-existing DBs correct.
        log("  - ensuring strongs_primary uses lexical form for compound tags (e.g. H9003/{H7225G} -> H7225)...")
        try:
            cur.execute(
                "SELECT id, strongs, strongs_primary FROM word "
                "WHERE strongs IS NOT NULL AND strongs LIKE '%{%' "
                "LIMIT 100000"
            )
            fixes = []
            pat = re.compile(r'\{([HG])(\d{3,5})')
            for wid, s, old_p in cur.fetchall():
                m = pat.search(s or "")
                if m:
                    new_p = f"{m.group(1)}{m.group(2)}"
                    if new_p != (old_p or ""):
                        fixes.append((new_p, wid))
            if fixes:
                cur.executemany(
                    "UPDATE word SET strongs_primary = %s WHERE id = %s",
                    fixes
                )
                conn.commit()
                log(f"    ✓ updated {len(fixes)} rows")
            else:
                log("    ✓ no fixes required")
        except Exception as e:
            log(f"    ! strongs_primary heal skipped: {e}")

        return True
    except Exception as e:
        log(f"  ✗ Schema migration failed: {e}")
        return False
    finally:
        try: conn.close()
        except Exception: pass


# ---------------------------------------------------------------------------
# Log-based resume state
# ---------------------------------------------------------------------------

def _safe_db_name_for_filename(db_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", db_name)


def _parse_done_from_log(path: Path, db_name: str) -> Set[str]:
    """Parse STEP_COMPLETE markers from one log file for the given db."""
    done: Set[str] = set()
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = STEP_MARKER_RE.match(line.strip())
                if m and m.group("db") == db_name:
                    done.add(m.group("step"))
    except Exception:
        return set()
    return done


def find_latest_log(db_name: str) -> Optional[Path]:
    """Return the most-recent (by mtime) log that contains at least one
    STEP_COMPLETE marker for this db-name.

    This deliberately skips "empty" logs produced by --dry-run or by the
    "every step already complete" short-circuit (those runs create a
    timestamped log but never emit markers, which used to poison resume
    state for the next real run).
    """
    if not LOGS_DIR.exists():
        return None
    safe = _safe_db_name_for_filename(db_name)
    candidates = sorted(
        LOGS_DIR.glob(f"pipeline-{safe}-*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in candidates:
        if _parse_done_from_log(p, db_name):
            return p
    return None


def read_log_state(db_name: str, log) -> Set[str]:
    latest = find_latest_log(db_name)
    if latest is None:
        log("No prior log with STEP_COMPLETE markers found for this db-name — treating as fresh run.")
        return set()
    log(f"Reading prior log: {latest.name}")
    done = _parse_done_from_log(latest, db_name)
    if done:
        log(f"  ✓ {len(done)} step(s) recorded complete in that log:")
        for s in sorted(done):
            log(f"      • {s}")
    else:
        # Shouldn't reach here; find_latest_log already filtered for markers.
        log("  (no STEP_COMPLETE markers found — treating as fresh run.)")
    return done


def emit_step_complete(log, db_name: str, step_name: str) -> None:
    log(f"{STEP_MARKER_PREFIX} {db_name} :: {step_name}")


# ---------------------------------------------------------------------------
# Step runners
# ---------------------------------------------------------------------------

def _fmt_cmd(args: List[str]) -> str:
    """Format command list for logging as a copy-paste friendly shell line.

    On Windows uses subprocess.list2cmdline so spaces in paths (e.g. 'Bible Wheel Site')
    get proper quoting in the '>' echo line. On POSIX uses shlex.quote.
    The actual execution always uses the arg list (never the string), so this is display only.
    """
    if os.name == "nt":
        return subprocess.list2cmdline([str(a) for a in args])
    import shlex
    return " ".join(shlex.quote(str(a)) for a in args)


def run_subprocess(args: List[str], env: dict, log) -> int:
    log(f"    > {_fmt_cmd(args)}")
    child_env = dict(env)
    child_env.setdefault("PYTHONUNBUFFERED", "1")
    child_env.setdefault("PYTHONIOENCODING", "utf-8")
    proc = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env=child_env, bufsize=1, encoding="utf-8", errors="replace",
        cwd=str(PROJECT_ROOT),
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        log("    " + line.rstrip())
    return proc.wait()


def run_python_step(step: Step, cfg_path: Path, env: dict, log) -> int:
    args = [sys.executable, str(step.script), "--config", str(cfg_path)] + list(step.extra_args)
    return run_subprocess(args, env, log)


def import_sql_dumps(cfg: dict, env: dict, log) -> int:
    base_env = dict(env)
    base_env["MYSQL_PWD"] = cfg.get("password", "")
    common = [
        "mysql",
        f"--host={cfg['host']}", f"--port={cfg['port']}", f"--user={cfg['user']}",
        "--default-character-set=utf8mb4", cfg["database"],
    ]
    for fname in REQUIRED_DUMPS:
        path = DATA_RAW / fname
        table = fname.replace('.sql', '')
        log(f"  → importing {fname}")
        # Drop first for idempotent re-runs (dumps contain CREATE TABLE + plain INSERTs)
        log(f"    > dropping {table} if exists (for clean import)")
        drop_cmd = common[:-1] + ["-e", f"DROP TABLE IF EXISTS `{table}`;"]
        subprocess.run(drop_cmd, env=base_env, cwd=str(PROJECT_ROOT), capture_output=True)
        log(f"    > mysql ... {cfg['database']} < {path.name}")
        t0 = time.monotonic()
        with path.open("rb") as src:
            proc = subprocess.Popen(
                common, stdin=src, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=base_env, cwd=str(PROJECT_ROOT), bufsize=1, encoding="utf-8", errors="replace"
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                log("    " + line.rstrip())
            rc = proc.wait()
        log(f"    ✓ {fname} ({fmt_elapsed(time.monotonic()-t0)})")
        if rc != 0:
            log(f"  ✗ mysql exited {rc} on {fname}")
            return rc

    # Load strongs lookup table (for strongs tooltips / api.php?api=strongs).
    # The dump file includes its own DROP TABLE IF EXISTS + CREATE + INSERTs.
    strongs_path = PROJECT_ROOT / "sql" / "schema" / "strongs-mysql.sql"
    if strongs_path.exists():
        log("  → importing strongs lookup table")
        log(f"    > mysql ... {cfg['database']} < {strongs_path.name}")
        t0 = time.monotonic()
        with strongs_path.open("rb") as src:
            proc = subprocess.Popen(
                common, stdin=src, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=base_env, cwd=str(PROJECT_ROOT), bufsize=1, encoding="utf-8", errors="replace"
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                log("    " + line.rstrip())
            rc = proc.wait()
        log(f"    ✓ strongs ({fmt_elapsed(time.monotonic()-t0)})")
        if rc != 0:
            log(f"  ✗ mysql exited {rc} on strongs")
            return rc
    else:
        log("  ! strongs-mysql.sql not found — strongs lookups will fail")
    return 0


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

class TeeLogger:
    def __init__(self, log_path: Path):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.fp = log_path.open("w", encoding="utf-8", buffering=1)
        self.path = log_path

    def __call__(self, line: str = "") -> None:
        print(line, flush=True)
        self.fp.write(line + "\n")

    def close(self) -> None:
        try: self.fp.close()
        except Exception: pass


def fmt_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s"


def banner(log, title: str) -> None:
    line = "═" * 63
    log(""); log(line); log(f"  {title}"); log(line); log("")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    label: str
    status: str
    elapsed: float = 0.0
    detail: str = ""


def _flat_index_of(step_name: str) -> Optional[int]:
    i = 0
    for grp in PIPELINE:
        for s in grp:
            if s.name == step_name:
                return i
            i += 1
    return None


def run_pipeline(args: argparse.Namespace, log: TeeLogger) -> int:
    db_name = resolve_db_name(args, log)
    cfg_path = Path(args.config)

    banner(log,
           f"Bible DB Pipeline   |   target: {db_name}   |   "
           f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    db_existed = create_database_if_missing(db_name, cfg_path, log, dry_run=args.dry_run)
    if db_existed is None:
        return 1
    log("")

    cfg = preflight(db_name, cfg_path, args, log, dry_run=args.dry_run, db_existed=(db_existed or False))
    if cfg is None:
        return 1
    log("")

    # Self-healing schema migrations (idempotent). Run for existing DBs and
    # also for fresh ones (the checks are cheap and ensure extra tables/procs
    # like verse_views and GetGematriaWords that are not yet in the core schema.sql).
    # Skip during --dry-run to avoid side effects.
    if not args.dry_run:
        if not ensure_schema_migrations(cfg, log):
            return 1
        log("")

    # Resolve which steps are already done.
    if args.rerun_all:
        log("--rerun-all: ignoring prior log state; every step will run.")
        done_set: Set[str] = set()
    elif not db_existed:
        log("Fresh database — prior log state ignored.")
        done_set = set()
    else:
        done_set = read_log_state(db_name, log)

    # --rerun-from STEP: mark prior steps as done, force STEP and after to run.
    if args.rerun_from:
        cutoff = _flat_index_of(args.rerun_from)
        if cutoff is not None:
            flat = [s for grp in PIPELINE for s in grp]
            for s in flat[:cutoff]:
                done_set.add(s.name)
            for s in flat[cutoff:]:
                done_set.discard(s.name)
            log(f"--rerun-from {args.rerun_from}: marking the {cutoff} "
                f"step(s) before it as done; forcing re-run of "
                f"'{args.rerun_from}' and everything after.")

    for s in args.skip:
        done_set.add(s)

    # Seed STEP_COMPLETE markers for the current done_set into *this* run's log
    # file right now. This guarantees that every log we create (including ones
    # from --dry-run, from the "already complete" short-circuit, or from a run
    # that crashes early) can itself serve as a valid prior log for future
    # resume. Without this, a dry-run or no-op run would create a newer log
    # containing zero markers, causing the *next* real run to see
    # "no STEP_COMPLETE markers found — treating as fresh run" and re-execute
    # everything.
    every_step = [s for grp in PIPELINE for s in grp]
    for s in every_step:
        if s.name in done_set:
            emit_step_complete(log, db_name, s.name)
    if all(s.name in done_set for s in every_step) \
       and not args.rerun_all and not args.rerun_from:
        log("")
        log("✓ Every step already complete according to the prior log.")
        log("  Re-run with --rerun-all or --rerun-from STEP to force work.")
        return 0

    if args.dry_run:
        log("")
        log("Plan (--dry-run; nothing will run):")
        for i, group in enumerate(PIPELINE, start=1):
            labels = " + ".join(s.label for s in group)
            done_marks = [s.name in done_set for s in group]
            if all(done_marks):
                tag = "  (already done — skip)"
            elif any(done_marks):
                tag = "  (partial; will run remaining)"
            else:
                tag = ""
            log(f"  [{i}/{len(PIPELINE)}] {labels}{tag}")
        log("")
        return 0

    child_env = os.environ.copy()
    child_env["BIBLE_DB_NAME"] = db_name
    if args.force:
        child_env["BIBLE_PIPELINE_FORCE"] = "1"

    total_start = time.monotonic()
    results: List[StepResult] = []

    for i, group in enumerate(PIPELINE, start=1):
        label = " + ".join(s.label for s in group)
        log("")
        log(f"[{i}/{len(PIPELINE)}] {label}")

        if all(s.name in done_set for s in group):
            log("      ✓ already done (prior log) — skipping")
            # (markers for these were already seeded at the top of this log)
            results.append(StepResult(label, "done", 0.0, "from log"))
            continue

        log(f"      Started {datetime.now().strftime('%H:%M:%S')}")
        group_start = time.monotonic()
        rc = 0
        for step in group:
            if step.name in done_set:
                log(f"      — sub-step '{step.name}' already done (prior log); skipping")
                # (marker was already seeded at the top of this log)
                continue
            if step.script is not None:
                rc = run_python_step(step, cfg_path, child_env, log)
            else:
                rc = import_sql_dumps(cfg, child_env, log)
            if rc != 0:
                log(f"      ✗ FAILED ({step.label}) — exit code {rc}")
                break
            emit_step_complete(log, db_name, step.name)

        elapsed = time.monotonic() - group_start
        if rc == 0:
            log(f"      ✓ Done in {fmt_elapsed(elapsed)}")
            results.append(StepResult(label, "✓", elapsed))
        else:
            results.append(StepResult(label, "✗", elapsed, f"exit {rc}"))
            for j in range(i, len(PIPELINE)):
                rem = PIPELINE[j]
                rem_label = " + ".join(s.label for s in rem)
                results.append(StepResult(rem_label, "—", 0.0, "not reached"))
            break

    total = time.monotonic() - total_start
    failed = sum(1 for r in results if r.status == "✗")
    overall_ok = (failed == 0)

    title = ("Pipeline complete" if overall_ok else "Pipeline FAILED")
    banner(log, f"{title}   |   total: {fmt_elapsed(total)}")

    for i, r in enumerate(results, start=1):
        gap = " " * max(2, 40 - len(r.label))
        elapsed_str = fmt_elapsed(r.elapsed) if r.elapsed > 0 else ""
        detail = f"  ({r.detail})" if r.detail else ""
        log(f"  [{i}/{len(PIPELINE)}] {r.label}{gap}{r.status}  {elapsed_str}{detail}")

    log("")
    log(f"Full log: {log.path}")
    log("")
    if overall_ok:
        log("Next steps for the web UI (to avoid blank screen / empty content):")
        log(f"  - Edit web/config.php and set 'database' => '{db_name}'")
        log("  - Make sure 'use_remote_api' => false (for local DB access)")
        log("  - If you used a non-default config.ini, also update web/config.php host/user/password to match.")
        log("  - Visit index.php?book=Gen&chapter=1&verse=1 (or your preferred start ref)")
    log("")
    return 0 if overall_ok else 1


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = parse_args(argv)
    if args.log_file:
        log_path = Path(args.log_file)
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_db = _safe_db_name_for_filename(args.db_name)
        log_path = LOGS_DIR / f"pipeline-{safe_db}-{stamp}.log"
    log = TeeLogger(log_path)
    try:
        return run_pipeline(args, log)
    finally:
        log.close()


if __name__ == "__main__":
    sys.exit(main())
