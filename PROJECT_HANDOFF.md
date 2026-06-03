# Project Handoff: Bible Gematria iPhone/Web Tool

Last updated: 2026-06-04

This handoff summarizes the whole thread and the current project state. It is
intended for the next developer, agent, or future Johan returning to the work.

## 1. High-Level Goal

Build and improve a Bible gematria tool that feels elegant and intuitive on
iPhone, while preserving the full scholarly/database depth of the inherited PHP
Bible browser.

Primary goals established in the thread:

- Create a premium iPhone-friendly version first.
- Keep the full Bible database local and private unless real hosting is chosen.
- Use GitHub for backup/versioning and GitHub Pages for a public preview.
- Later improve the gematria/research tool itself with richer analysis.
- Package the website cleanly for handoff without private database dumps or
  local credentials.

## 2. Communication And Safety Decisions

Johan is controlling a MacBook and Codex mostly from an iPhone. Instructions
should therefore be simple and concrete: say what to click, what file to open,
and what is safe.

Safety decisions made early:

- Read-only access is safer for initial inspection.
- Writing/editing is needed for full implementation, but only inside the project
  workspace.
- Do not delete files unless Johan explicitly asks for that specific deletion.
- Do not publish local database credentials.
- Do not publish private SQL dumps or raw Bible source data.
- Keep source code, docs, and static assets in Git; keep local/private runtime
  files ignored.

Johan was worried Codex might delete important files. The project is now set up
so the important private/local files are ignored by Git and excluded from clean
archives.

## 3. Beginner Setup Context From The Thread

Johan asked what PHP is and how to make the app fully runnable.

Explanation used:

- PHP is the server-side language this inherited Bible app uses.
- The full app needs PHP plus MySQL/MariaDB because it queries the Bible
  database dynamically.
- GitHub Pages cannot run PHP/MySQL. It can only serve static HTML/CSS/JS.
- A public full version needs PHP/MySQL hosting or a remote API.

Mac setup steps completed:

- Apple Command Line Developer Tools were installed after macOS prompted for
  the `git` command.
- MAMP is installed and provides PHP/MySQL locally.
- Git and GitHub were configured.
- A repo-specific GitHub SSH deploy key was configured locally.

Important local paths:

```text
/Applications/MAMP/bin/php/php/bin/php
/Applications/MAMP/bin/php/php8.4.17/bin/php
/Applications/MAMP/Library/bin/mysql80/bin/mysqld_safe
/Users/johanfrenck/.ssh/biblegematria_github
```

Do not commit the SSH key path contents or any private key.

## 4. Repository And Deployment State

Project repo:

```text
/Users/johanfrenck/Documents/Codex/2026-06-02/what-s-the-difference-between-standard/biblegematria-iphone
```

GitHub remote:

```text
git@github.com:jjjohan564/-BibleGematria_1.git
```

Public Pages URL:

```text
https://jjjohan564.github.io/-BibleGematria_1/
```

Current branch:

```text
main
```

Current latest commit at the time of this handoff:

```text
5a92872 Move word cards above analysis on website
```

Recent commits:

```text
5a92872 Move word cards above analysis on website
bce117c Add website handoff and launch packaging
64a114f Update GitHub Pages offline app
d81f172 Add selected letter formations search
bab0484 Initial Bible Gematria app setup
```

Branch notes:

- `main` is synced with `origin/main`.
- `gh-pages` exists but is behind `main`.
- If GitHub Pages is configured to serve from `main/docs`, the latest
  `docs/index.html` work should be the live preview.
- If GitHub Pages is configured to serve from `gh-pages`, then public Pages is
  not showing the latest `main` work. Verify in GitHub repository settings
  before relying on the public preview.

## 5. Local App Versus GitHub Pages Preview

This was a major source of confusion and is still the most important technical
distinction.

Full local app:

- Runs PHP.
- Uses MySQL/MariaDB.
- Reads `web/config.php`.
- Can select real books/chapters/verses from the database.
- Can use all PHP-backed endpoints.
- Can use the private local Bible database.

Static GitHub Pages preview:

- Runs only HTML/CSS/JavaScript.
- Cannot run PHP.
- Cannot connect directly to MySQL.
- Cannot use private local database data.
- Is useful for mobile UI preview and public sharing.

Johan noticed the public version only showed the preview and did not fully
support changing books like the local app. That is expected with GitHub Pages.

## 6. Files And Artifacts Discussed

User-provided/attached files:

- `Foto 1.jpg`: screenshot of macOS asking to install Command Line Developer
  Tools for `git`.
- `bible_sql_dumps.zip`: SQL dumps supplied by Richard for the missing Bible
  tables.

Generated/package files:

- `BibleGematria_website_handoff_2026-06-03.zip`: earlier clean website package.
- `BibleGematria_website_thread_handoff_2026-06-04.zip`: current clean website
  package produced with this handoff.

Important repo files:

```text
HANDOFF.md                         # Detailed technical handoff from 2026-06-03
PROJECT_HANDOFF.md                 # This conversation-level handoff
README_LOCAL_APP.md                # Beginner local/iPhone launcher guide
BibleGematria.command              # Mac double-click launcher
BibleGematria-iPhone-Share.command # iPhone local-network share launcher
macos/Bible Gematria.app           # Small Mac app wrapper
config.ini.sample                  # DB import config template, no secrets
web/config.php.sample              # web DB config template, no secrets
docs/index.html                    # static GitHub Pages preview
web/index.php                      # full PHP Bible viewer
web/api.php                        # JSON/API endpoints
web/db.php                         # database and remote API layer
web/search_lib.php                 # search and letter-formation backend
web/js/analysis.js                 # audit, compare, forms, exports
web/js/gematria.js                 # live gematria panel
web/js/word-selection.js           # word/phrase selection
web/style.css                      # main UI styling
web/manifest.webmanifest           # PWA install metadata
web/icon.svg
web/icon-180.png
web/icon-512.png
scripts/run_pipeline.py            # database build orchestrator
sql/schema/schema.sql              # core schema
sql/schema/gematria_schema.sql     # gematria tables
```

Private/ignored local files:

```text
config.ini
web/config.php
data/raw/
logs/
.python-deps/
```

These should not be included in public zips or Git commits.

## 7. Data Decision: Missing SQL Dumps

At one point two or three SQL dump files were missing. Another agent
investigated and said the dumps were proprietary BibleWorks-derived production
database exports that were not publicly available.

Advice given:

- If Richard can provide the original dumps, use Richard's dumps.
- If not, open data equivalents could be generated later, but they may not be
  textually identical to the original production database.

Richard then provided the SQL dumps. The project proceeded with those.

SQL dump tables:

- `bible_na27`
- `bible_scr`
- `bible_kjv`

These are needed for the full local database pipeline but are not committed.

## 8. Features Requested By Johan

Johan requested the improved tool show:

- Word counts.
- Letter counts.
- Prime factorization.
- Prime index.
- Full-verse translation.
- Direct word translation/meaning.
- Standard, ordinal, and reduced value.
- Individual verse-section/phrase selection.
- Individual word selection.
- Elegant and intuitive UI.
- Letter-by-letter breakdown with full audit trail.
- Comparison mode for different texts side by side.
- Export functions: copy, text, CSV, JSON, PDF.
- For each selected word/phrase, all possible letter formations, but only
  coherent real word/phrase results.

## 9. Implemented Features

Current implemented work includes:

- Premium iPhone-oriented UI.
- Static GitHub Pages preview.
- Full PHP app structure preserved.
- Git/GitHub setup.
- GitHub Pages setup by Johan.
- Local Mac launcher for the full app.
- iPhone local-network launcher for viewing the Mac app from Safari.
- PWA manifest and icons.
- Word count and letter count display.
- Standard, ordinal, and reduced values.
- Prime factorization.
- Prime index.
- Full verse/meaning data where database data exists.
- Word gloss/meaning/transliteration/Strong's/grammar display.
- Select individual words.
- Select short phrases/sections manually.
- Letter-by-letter audit trail.
- Comparison tab.
- Export as copy/TXT/CSV/JSON/PDF.
- Real Bible letter formations search, filtered to real corpus words and
  contiguous phrases.
- Latest static preview layout update: word cards moved above analysis on the
  website.

## 10. Letter Formations Design Decision

Johan asked for "all possible letter formations" for selected words.

Important decision:

- Do not generate every mathematical permutation.
- Only return coherent results already found in the Bible corpus.
- Include real word forms and contiguous phrase forms.

Reason:

- Raw permutations would produce nonsense.
- Corpus-filtered forms match the user's intent: coherent word/phrase results.

Implementation:

- UI in `web/js/analysis.js`.
- API case in `web/api.php`: `formations`.
- Backend in `web/search_lib.php`: `bible_letter_formations()`.

Current limits:

- UI accepts up to 8 selected words and 40 letters.
- Phrase search is skipped above 28 letters.
- Word groups capped at 50.
- Phrase groups capped at 30.
- Future performance improvement should precompute formation signatures.

## 11. Local Run Commands

Beginner path:

```text
Double-click BibleGematria.command
```

If macOS blocks it:

```text
Right-click BibleGematria.command > Open
```

Manual local PHP server command:

```sh
/Applications/MAMP/bin/php/php/bin/php -S 127.0.0.1:8888 -t web
```

Local app URL:

```text
http://127.0.0.1:8888/index.php?book=Gen&chapter=1&verse=1
```

iPhone local-network launcher:

```text
Double-click BibleGematria-iPhone-Share.command
```

Stop local PHP server:

```sh
kill $(cat logs/php_server_8888.pid)
```

Stop iPhone-share server:

```sh
kill $(cat logs/php_server_8887.pid)
```

## 12. Git And Packaging Commands

Check repo state:

```sh
git status --short --branch
```

Show recent commits:

```sh
git log --oneline --decorate -5
```

PHP syntax checks:

```sh
/Applications/MAMP/bin/php/php/bin/php -l web/index.php
/Applications/MAMP/bin/php/php/bin/php -l web/api.php
/Applications/MAMP/bin/php/php/bin/php -l web/search_lib.php
/Applications/MAMP/bin/php/php/bin/php -l web/db.php
```

Validate manifest JSON:

```sh
node -e "JSON.parse(require('fs').readFileSync('web/manifest.webmanifest','utf8')); console.log('manifest OK')"
```

Create a clean zip from tracked Git files:

```sh
git archive --format=zip --output ../BibleGematria_website_thread_handoff_2026-06-04.zip HEAD
```

Verify forbidden private files are absent:

```sh
zipinfo -1 ../BibleGematria_website_thread_handoff_2026-06-04.zip | rg '(^|/)(config\.ini|config\.php|data/raw|logs|\.git|\.python-deps)(/|$)|\.(zip|dump)$'
```

Expected result: no output.

## 13. Implementation Plan Going Forward

Recommended sequence:

1. Confirm GitHub Pages source.
2. Decide if the public site should remain a static preview or become the real
   full app.
3. If keeping GitHub Pages, build or configure a remote API so static frontend
   can fetch live Bible data.
4. If making the full app public, choose PHP/MySQL hosting and deploy `web/`.
5. Import the private database on the hosting server only if licensing/privacy
   questions are settled.
6. Improve side-by-side comparison mode.
7. Optimize letter formations with precomputed signatures.
8. Add iPhone-friendly range selection controls.
9. Add shareable analysis links.
10. Add automated smoke tests.

## 14. Unresolved Issues And Risks

GitHub Pages source:

- `gh-pages` exists but is behind `main`.
- Need confirm whether GitHub Pages serves from `main/docs` or `gh-pages`.

Full public app:

- Not solved by GitHub Pages alone.
- Requires PHP/MySQL hosting or a remote API.

Private data:

- Richard's SQL dumps are local/private.
- Do not publish them without permission.

Database completeness:

- LXX support exists in code/schema, but do not assume every local database has
  LXX imported. Verify tables before promising LXX completeness.

Formation search:

- Works for short selections.
- Needs indexing for scale.

Clause detection:

- Manual selection works.
- Automatic clause detection is not implemented.

Static preview limitation:

- The static preview cannot mirror all full app behaviors without a backend.

## 15. What To Hand Off

For a next agent/developer, provide:

- The clean zip package.
- `PROJECT_HANDOFF.md`.
- `HANDOFF.md`.
- `README_LOCAL_APP.md`.
- GitHub repository URL.
- GitHub Pages URL.

Do not provide:

- `web/config.php`
- `config.ini`
- `data/raw/`
- local SQL dumps
- SSH keys
- logs

## 16. Current Best Next Step

The best next technical step is to decide hosting:

- If Johan wants a real public app with all books and search, choose PHP/MySQL
  hosting or a remote API.
- If Johan only needs visual previews on iPhone for now, keep improving
  `docs/index.html` and the static preview.

Once hosting is decided, continue improving the actual research features rather
than fighting GitHub Pages' static limitations.
