# BibleDB

Full featured Bible Database with Greek, Hebrew, interlinear, grammar, concordance, gematria and more!

## Overview

This project consists of two main parts:

1. **Data Import Pipeline** (root directory)
   - One python script parses and loads STEPBible.org tagged Hebrew/Greek texts (BHS, NA27, Scrivener TR).
   - Extensive support for textual variants, morphology, Strong's numbers, gematria, and cross-edition comparison.
   - Coming: scripts to import LXX and other versions.

2. **Web Interface** (`web/` folder)
   - A PHP-based interlinear Bible browser.
   - Features include edition switching (NA28, TR, BHS), variant cycling, gematria calculations, Strong's tooltips, grammar tooltips, word selection, and powerful search.

## Project Structure

```
BibleDB/
├── *.py, *.sql                 # Data import pipeline and schemas
├── config.ini                  # Database credentials (not committed)
├── config.ini.sample           # Template for database config
├── docs/
│   ├── HANDOFF-current.md      # Recommended current handoff
│   └── HANDOFF.md              # Historical/archival notes
│
└── web/                        # PHP Web UI
    ├── index.php               # Main interlinear viewer
    ├── db.php                  # Database access layer
    ├── api.php                 # AJAX + remote API endpoints
    ├── config.php              # Web config (not committed)
    ├── config.php.sample       # Template for web config
    ├── js/                     # Frontend JavaScript
    └── HANDOFF.md              # Web UI specific documentation
```

## Getting Started

### 1. Database Setup (Optional for UI Development)

If you want to run the full stack locally:

1. Copy `config.ini.sample` → `config.ini` and fill in your credentials and a database name of your choice.
2. Run the import pipeline command: python scripts/run_pipeline.py --db-name <database name>. It imports everything and configures the DB.
3. The script displays progress and a "success" message when all steps complete. If there are any errors, check the log in the log folder. 

### 2. Web UI Setup

1. Copy `web/config.php.sample` → `web/config.php` and update the credentials.
2. If you do not have a local database, set use_remote_api' => true, and 'remote_api_base' = 'https:biblewheel.com/bible' (or whatever server hosts the db).  
3. Point your web server (Apache, nginx, PHP built-in server, etc.) at the `web/` directory. 
4. Access the interface (example: `http://localhost/stepbible`).

## Development

- The **web UI** can run completely independently of the data import scripts if you use the remote api.
- Most frontend development work happens inside the `web/` folder and requires no updates to the DB.

## Documentation

- **`docs/HANDOFF-current.md`** — Recommended starting point (current workflows, single source of truth for DB name, easy fresh database creation).
- **Root `HANDOFF.md`** — Historical/archival notes from earlier development sessions (still useful for deep context).
- **`web/HANDOFF.md`** — Details about the web UI, JavaScript components, and frontend architecture.

## License

MIT license for the code in this project. Data sources have their own licenses (primarily CC BY 4.0 from STEPBible.org and related projects). See individual source files and the root HANDOFF for attribution details.

## Contributing / External Development

**External contributors welcome!**  

