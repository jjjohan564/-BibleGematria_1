#!/usr/bin/env python3
"""
scripts/_db.py
==============

Single shared module for all import/ and maintenance/ scripts.

Eliminates ~80 lines of duplicated config-loading + connect boilerplate
per script (and the drift that caused some to still accept config.ini
database= or mention stepbible defaults).

Single source of truth rule (enforced here):
  - Database name: ONLY from BIBLE_DB_NAME (or BIBLE_DATABASE) environment variable.
  - Never falls back to config.ini [mariadb] database key.
  - Host/port/user/password: BIBLE_DB_* env vars > config.ini [mariadb] > defaults.

Exposed API (use the one that fits):
    from _db import load_config, get_connection, verify_db_name
    from _db import connect   # convenience that also prints + verifies

Typical collapse in a script:
    # before: 70+ lines of configparser, driver try, connect, prints, verify...
    # after:
    from _db import connect
    conn, cur, cfg = connect(args.config)   # or connect() using default path logic

Or the lower-level if you need full control:
    cfg = load_config(Path(args.config))
    conn, driver = get_connection(cfg)
    cur = conn.cursor()
    verify_db_name(cur, cfg["database"])
"""

from __future__ import annotations

import configparser
import os
import sys
from pathlib import Path
from typing import Optional, Tuple, Union, Dict, Any

__all__ = ["load_config", "get_connection", "connect", "verify_db_name"]


def load_config(path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """
    Load database connection settings with a strict single source of truth.

    For the DATABASE NAME:
        - The ONLY source is the BIBLE_DB_NAME environment variable (BIBLE_DATABASE also works).
        - It is deliberately NOT read from config.ini.

    For the other fields (host, port, user, password):
        - Environment variables (BIBLE_DB_*) take precedence.
        - Then config.ini [mariadb] section.
        - Then reasonable defaults.

    This gives us a true single source of truth for which database we are
    targeting, while still allowing convenient configuration of connection
    details.
    """
    cfg: Dict[str, Any] = {
        "host":     "127.0.0.1",
        "port":     "3306",
        "user":     "root",
        "password": "Zubi3168^2!!",
        "database": None,
    }

    # Determine config file path if not provided
    if path is None:
        # Walk up from this file to find a sibling or parent config.ini
        here = Path(__file__).resolve()
        candidates = [
            here.parent.parent / "config.ini",  # scripts/config.ini when _db is in scripts/
            here.parent / "config.ini",         # if someone puts _db elsewhere
            Path.cwd() / "config.ini",
        ]
        for cand in candidates:
            if cand.exists():
                path = cand
                break

    # Read non-database values from config.ini first
    if path:
        p = Path(path)
        if p.exists():
            cp = configparser.ConfigParser()
            cp.read(p, encoding="utf-8")
            if "mariadb" in cp:
                sec = cp["mariadb"]
                for key in ("host", "port", "user", "password"):
                    if key in sec and sec[key].strip():
                        cfg[key] = sec[key].strip()

    # Environment variables override config.ini for host/port/user/password
    for key in ("host", "port", "user", "password"):
        env_val = os.environ.get(f"BIBLE_DB_{key.upper()}")
        if env_val and env_val.strip():
            cfg[key] = env_val.strip()

    # DATABASE NAME: strictly from BIBLE_DB_NAME (single source of truth).
    # We also accept the common alternative spelling BIBLE_DATABASE for convenience.
    db_name = (os.environ.get("BIBLE_DB_NAME")
               or os.environ.get("BIBLE_DATABASE"))
    if db_name and db_name.strip():
        cfg["database"] = db_name.strip()
    else:
        cfg["database"] = None

    # Enforce single source of truth for database name
    if not cfg.get("database"):
        raise ValueError(
            "Database name MUST be provided via the BIBLE_DB_NAME environment variable\n"
            "(BIBLE_DATABASE is also accepted as an alias).\n"
            "It is no longer read from config.ini (single source of truth).\n\n"
            "On Windows PowerShell this is PER-SESSION by default:\n"
            "    $env:BIBLE_DB_NAME = \"stepbible\"\n"
            "    python scripts/import/import_bible.py\n\n"
            "To make it survive new terminals, use the helper (recommended):\n"
            "    .\\scripts\\set-bible-db.ps1 -Name stepbible -Persist\n"
            "    (or use a test name like stepbibletest for clean testing)\n\n"
            "(After -Persist you must close & reopen your PowerShell window.)"
        )
    return cfg


def get_connection(cfg: Dict[str, Any]) -> Tuple[Any, str]:
    """Open a connection using the best available driver.

    Tries mariadb first (preferred), then pymysql as fallback.
    Returns (connection, driver_name).
    Raises SystemExit on total failure.
    """
    if not cfg.get("database"):
        raise ValueError("Database name must be provided via the BIBLE_DB_NAME environment variable (single source of truth). See the error from load_config for Windows PowerShell examples and the set-bible-db.ps1 helper.")

    common = dict(
        host=cfg["host"], port=int(cfg["port"]),
        user=cfg["user"], password=cfg["password"],
        database=cfg["database"],
    )
    try:
        import mariadb  # type: ignore
        return mariadb.connect(**common), "mariadb"
    except Exception:
        pass
    try:
        import pymysql  # type: ignore
        return pymysql.connect(charset="utf8mb4", **common), "pymysql"
    except Exception as e:
        print("ERROR: Could not connect using either 'mariadb' or 'pymysql'.")
        print("Install one with: pip install mariadb   # preferred")
        print("                  pip install pymysql   # fallback")
        print(f"Last error: {e}")
        sys.exit(2)


def verify_db_name(cur: Any, expected_db: str) -> bool:
    """Ask the server what database this connection is actually using.

    Returns True if it matches the expected single source of truth.
    Always prints the result for visibility during testing.
    (Previously named verify_connected_database in import_bible.py.)
    """
    cur.execute("SELECT DATABASE()")
    actual = cur.fetchone()[0]
    print(f"  + Server reports current database: {actual}")
    if actual != expected_db:
        print(f"  ! WARNING: MISMATCH! Expected '{expected_db}' but server reports '{actual}'")
        print("    The script read the correct value, but the connection is using something else.")
        return False
    print("  + Confirmed: connection is using the resolved database name.")
    return True


def connect(config: Optional[Union[str, Path, Dict[str, Any]]] = None) -> Tuple[Any, Any, Dict[str, Any]]:
    """High-level convenience for the common case.

    Accepts:
      - None (auto-discovers config.ini)
      - a path to config.ini (str or Path)
      - a ready-made cfg dict (from load_config)

    Behavior:
      - Loads cfg if needed (via load_config)
      - Prints the single-source-of-truth banner
      - Opens the connection
      - Prints driver
      - Runs verify_db_name (SELECT DATABASE())
      - Returns (conn, cur, cfg)

    This is the one-liner most scripts can now use:
        from _db import connect
        conn, cur, cfg = connect(args.config)
    """
    if isinstance(config, dict):
        cfg = config
    else:
        cfg = load_config(config)

    print("\nConnecting using single-source-of-truth config:")
    print(f"  host={cfg['host']}  port={cfg['port']}  user={cfg['user']}  database={cfg['database']}")
    print(f"  (database name comes EXCLUSIVELY from BIBLE_DB_NAME (or BIBLE_DATABASE) env var)")
    print("  -> A live verification query (SELECT DATABASE()) will confirm we are on the correct DB.")

    conn, driver = get_connection(cfg)
    cur = conn.cursor()
    print(f"  connected via '{driver}'.")

    print()
    verify_db_name(cur, cfg["database"])
    print()

    return conn, cur, cfg
