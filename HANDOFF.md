# Bible Gematria Handoff

Last updated: 2026-06-03

This is the current root handoff for the Bible Gematria website/app. It is
written for the next developer or agent who continues the work, and also for a
beginner who needs to understand what has been set up without guessing.

## 1. Current Project Goal

The project is a Bible gematria study tool with:

- A full PHP/MySQL local app for the complete Bible database.
- A static GitHub Pages preview for iPhone viewing.
- A premium mobile-first interface focused on iPhone use.
- Word, phrase, and verse analysis for Hebrew and Greek Bible texts.
- Gematria, textual data, translations/glosses, comparison, export, and search
  features.

The immediate design direction from Johan was:

- Make the iPhone version elegant, intuitive, and premium.
- Improve the tool itself after the mobile experience is solid.
- Keep the database/private Bible files local unless a real hosting strategy is
  chosen.

## 2. Repository And URLs

Local repo:

```text
/Users/johanfrenck/Documents/Codex/2026-06-02/what-s-the-difference-between-standard/biblegematria-iphone
```

GitHub remote:

```text
git@github.com:jjjohan564/-BibleGematria_1.git
```

Public GitHub Pages URL:

```text
https://jjjohan564.github.io/-BibleGematria_1/
```

Important branch notes:

- `main` contains the full source repo: PHP app, scripts, SQL schemas, docs,
  static preview files, launchers, and handoff docs.
- A `gh-pages` branch also exists from earlier deployment work.
- GitHub Pages was enabled by Johan in the GitHub UI. Before changing deployment
  behavior, check the GitHub Pages setting to confirm whether Pages is serving
  from `main/docs`, `gh-pages`, or another source.
- GitHub Pages cannot run PHP or MySQL. It can only serve static files.

## 3. Critical Safety Rules

Do not commit or upload private/local files:

- `config.ini`
- `web/config.php`
- `data/raw/`
- `logs/`
- `.python-deps/`
- SQL dumps, local zip dumps, database exports, or credentials

These are already protected by `.gitignore`, but always verify before zipping,
committing, or deploying.

Reason:

- `config.ini` and `web/config.php` can contain local database credentials.
- `data/raw/` contains large/private Bible source material and SQL dumps.
- The BibleWorks-derived SQL dumps should not be published casually.
- Logs can leak local paths, database names, or errors.

The source code is safe to share. The private database content is not included
in the clean website zip.

## 4. What Was Set Up On The Mac

The MacBook has the development prerequisites needed for the local app:

- Git / Apple Command Line Developer Tools were installed.
- MAMP is installed.
- MAMP PHP is available at:

```text
/Applications/MAMP/bin/php/php/bin/php
/Applications/MAMP/bin/php/php8.4.17/bin/php
```

- MAMP MySQL startup helper is available at:

```text
/Applications/MAMP/Library/bin/mysql80/bin/mysqld_safe
```

- The local project has a GitHub deploy SSH key configured via repo-local Git
  config. The key path is local to this Mac:

```text
/Users/johanfrenck/.ssh/biblegematria_github
```

Do not copy this key into the repo or zip.

## 5. Local App Versus GitHub Pages

There are two different viewing modes. This distinction matters a lot.

### Full local app

The full app is the real Bible Gematria tool. It needs:

- PHP
- MySQL/MariaDB
- `web/config.php`
- A populated Bible database
- The PHP files in `web/`

This version can:

- Select books, chapters, verses, and editions.
- Query the full Bible database.
- Run PHP APIs such as `api.php?api=formations`.
- Use the local/private database.

### Static GitHub Pages preview

The GitHub Pages version is a static preview. It needs:

- HTML
- CSS
- JavaScript
- Static embedded data

This version cannot:

- Run PHP.
- Connect to MySQL.
- Load the private database.
- Run live database search unless a remote API is added.

It is useful for:

- iPhone visual preview.
- Mobile UI testing.
- Sharing a public link quickly.
- Showing the direction of the design.

To make the full app public online, use real PHP/MySQL hosting or a remote API
server. GitHub Pages alone is not enough.

## 6. Main Files And Folders

```text
biblegematria-iphone/
├── HANDOFF.md                         # This current detailed handoff
├── README_LOCAL_APP.md                # Beginner local/iPhone launcher guide
├── BibleGematria.command              # Double-click Mac launcher
├── BibleGematria-iPhone-Share.command # Local-network iPhone launcher
├── config.ini.sample                  # Import pipeline DB config template
├── docs/                              # Static GitHub Pages preview/docs
├── macos/Bible Gematria.app           # Small Mac app wrapper around launcher
├── scripts/                           # Python import/maintenance pipeline
├── sql/schema/                        # SQL schema files
├── web/                               # Full PHP app and static preview assets
└── data/raw/                          # Private source data, gitignored
```

Key web files:

```text
web/index.php                 # Main PHP Bible viewer
web/style.css                 # Mobile-first premium UI styling
web/api.php                   # JSON endpoints for dropdowns/search/forms/ELS
web/db.php                    # Local DB and remote API data layer
web/search_lib.php            # Search, gematria search, letter formations
web/els.php                   # ELS grid page
web/els_lib.php               # ELS data helpers
web/js/analysis.js            # Audit, compare, forms, exports
web/js/gematria.js            # Live gematria panel
web/js/word-selection.js      # Tap/drag word selection
web/js/variant-switcher.js    # Variant cycling and gematria sync
web/manifest.webmanifest      # PWA install metadata
web/icon.svg                  # App icon
web/icon-180.png              # Apple touch icon
web/icon-512.png              # PWA icon
```

## 7. Data Sources And Database

The inherited database work is based on:

- STEPBible tagged Hebrew OT and Greek NT source files.
- SQL dumps Richard provided for:
  - `bible_na27.sql`
  - `bible_scr.sql`
  - `bible_kjv.sql`
- Local MySQL/MariaDB tables used by the PHP app.

The raw SQL dumps were supplied separately in `bible_sql_dumps.zip`. They are
not committed to Git and are not included in the clean website zip.

Important database tables include:

- `book`
- `verse`
- `word`
- `word_edition`
- `variant`
- `variant_edition`
- `word_morpheme`
- `word_link`
- `word_alt_strong`
- `gematria_word`
- `gematria_verse`
- `bible_na27`
- `bible_scr`
- `bible_kjv`
- `strongs`

The app expects `web/config.php` to point to the local database. The sample file
is `web/config.php.sample`.

## 8. How To Run The Full Local App

For Johan, the easiest path is:

1. Double-click `BibleGematria.command`.
2. If macOS blocks it the first time, right-click it and choose `Open`.
3. The launcher starts MAMP MySQL.
4. The launcher starts PHP's local web server.
5. The browser opens:

```text
http://127.0.0.1:8888/index.php?book=Gen&chapter=1&verse=1
```

The launcher writes the PHP server PID to:

```text
logs/php_server_8888.pid
```

To stop the PHP server manually:

```sh
kill $(cat logs/php_server_8888.pid)
```

MAMP MySQL may keep running after the PHP server stops. Stop it from the MAMP
app if needed.

## 9. How To View The Full Local App From iPhone

The iPhone cannot run the PHP/MySQL app by itself. It can view the Mac's local
server while both devices are on the same Wi-Fi/hotspot network.

Use:

```text
BibleGematria-iPhone-Share.command
```

That launcher:

- Starts the app on host `0.0.0.0`.
- Uses port `8887` by default.
- Prints local network URLs.
- Lets Safari on the iPhone open the Mac-hosted app.

This only works while:

- The Mac is awake.
- The Mac and iPhone are on the same hotspot/Wi-Fi.
- The network allows local device-to-device connections.

Because this exposes the local PHP server to the local network, only use it on a
network Johan trusts.

## 10. How To View The Public Static Version From iPhone

Open the GitHub Pages URL on the iPhone:

```text
https://jjjohan564.github.io/-BibleGematria_1/
```

In Safari, use:

```text
Share > Add to Home Screen
```

The web app has PWA metadata and icons:

- `web/manifest.webmanifest`
- `web/icon.svg`
- `web/icon-180.png`
- `web/icon-512.png`

If the static Pages source is `docs/`, mirror any required static icons/manifest
there before expecting them to appear on the public URL.

## 11. Features Implemented

### Premium iPhone interface

The app was restyled toward a premium iPhone experience:

- Mobile-first layout.
- Clear study panels.
- Touch-friendly controls.
- Reduced visual clutter.
- Better typography and spacing.
- More app-like navigation.
- PWA metadata/icon support for home-screen installation.

### Book/chapter/verse navigation

The PHP app supports real dropdown navigation:

- Book selection.
- Chapter selection.
- Verse selection.
- Neighbor navigation.
- Edition selection where relevant.

The static GitHub Pages preview is intentionally more limited because it has no
PHP/MySQL backend.

### Full verse and word translation data

The app displays:

- Coherent verse translation/readout where data exists, including KJV clean text.
- Direct word gloss/meaning.
- Transliteration.
- Strong's number.
- Grammar/morphology tags.
- Tooltips for Strong's and grammar details.

### Standard, ordinal, and reduced values

The app tracks three gematria systems:

- Standard value.
- Ordinal value.
- Reduced value.

The values update for:

- Whole verse.
- Selected words.
- Selected phrase/section.
- Variant changes where applicable.

### Word and letter counts

The analysis panel shows:

- Word count.
- Letter count.

Important detail:

- Hebrew section markers are excluded correctly.
- Greek diacritics are stripped for counting.
- Greek iota subscript is counted as a real iota.

### Prime factorization and prime index

The gematria panel and analysis/export payload include:

- Prime factorization.
- Prime/non-prime status.
- Prime index for prime values.

Example behavior:

- A prime total shows its 1-based position in the sequence of primes.
- A non-prime total reports "not prime".

### Individual word and verse-section selection

Selection is implemented in `web/js/word-selection.js` and consumed by
`web/js/gematria.js` and `web/js/analysis.js`.

Supported behavior:

- Tap/click a word to select or unselect it.
- Drag/paint select with the mouse in desktop use.
- Clear selection with Escape or the clear control.
- When no words are selected, analysis defaults to the whole verse.
- When words are selected, analysis switches to selected section mode.

This covers:

- Individual words.
- Short phrase/section selections.
- Clause-like analysis when the user selects the clause manually.

### Letter-by-letter audit trail

The Audit tab shows, for each analyzed word:

- Original word.
- Meaning/gloss.
- Strong's and grammar metadata.
- Standard/ordinal/reduced value.
- Letter-by-letter chips.
- Each letter's standard, ordinal, and reduced contribution.

This gives a full audit trail for each word/value instead of only showing the
final total.

### Comparison mode

The Compare tab shows selected material side by side:

- Original-language text.
- Meaning/gloss line.
- Individual word rows.

This is the current comparison foundation. Full cross-edition side-by-side
comparison can be expanded later from the existing edition-aware data layer.

### Export functions

The app can export the current analysis as:

- Copy to clipboard.
- TXT.
- CSV.
- JSON.
- PDF/print.

The export includes:

- Reference.
- Edition.
- Scope.
- Word and letter counts.
- Standard/ordinal/reduced values.
- Factorization.
- Prime index.
- Original text.
- Meaning.
- Per-word metadata.
- Per-letter audit details.

The implementation is in `web/js/analysis.js`.

### Real Bible letter formations

The Forms tab answers the later request:

"For each selected word, provide all possible letter formations, only coherent
word/phrase results."

The implemented version does not generate random permutations. It filters to
real corpus hits:

- Real Bible word forms.
- Real contiguous Bible phrases.
- Same letters/signature as the selected target.
- Hebrew final forms normalized to base forms.
- Greek sigma and final sigma normalized.
- Greek diacritics stripped.
- Iota subscript treated as iota.

Limits:

- Select up to 8 words and 40 letters in the UI.
- Phrase search is skipped for targets over 28 letters.
- Word forms are capped at 50 groups.
- Phrase forms are capped at 30 groups.
- This currently scans corpus data directly; later it should be optimized with
  stored formation signatures/index tables if it becomes slow.

Files:

- Frontend: `web/js/analysis.js`
- API endpoint: `web/api.php`, case `formations`
- Backend: `web/search_lib.php`, function `bible_letter_formations()`

### ELS support

ELS files are present:

- `web/els.php`
- `web/els_lib.php`

The ELS implementation fetches a stream of stripped letters from the selected
location and renders an ELS grid. It supports Hebrew, Greek, and English paths
depending on the selected source/edition.

### Remote API mode

The web app has a remote API mode in `web/config.php`:

```php
'use_remote_api' => true,
'remote_api_base' => 'https://your-live-domain.example/bible',
```

When enabled, the local PHP layer calls a remote server instead of directly
opening the local database. This is useful for future public hosting or for
frontend contributors who do not have the private database.

Current caveat:

- The remote server must run compatible versions of `api.php`, `db.php`,
  `search_lib.php`, `els_lib.php`, and `remote_api.php`.

## 12. GitHub Work Completed

Git was initialized and connected to:

```text
git@github.com:jjjohan564/-BibleGematria_1.git
```

Commits already pushed before this handoff included:

```text
bab0484 Initial Bible Gematria app setup
d81f172 Add selected letter formations search
64a114f Update GitHub Pages offline app
```

GitHub Pages was enabled by Johan and verified as live from the iPhone.

## 13. Current Known Limitations

### GitHub Pages is not the full app

The public Pages link is static. It cannot run PHP/MySQL. The user noticed that
the public preview does not behave like the full app with all book selection and
database-backed features. That is expected until we add real hosting.

Options for the full online version:

- PHP/MySQL hosting.
- A small VPS.
- Shared hosting that supports PHP and MySQL.
- A remote API server plus a static frontend.
- Temporary tunnel from the Mac for private testing.

### LXX status

There is LXX-related code and schema support:

- `scripts/import/import_lxx.py`
- `sql/schema/lxx_schema.sql`
- `web/db.php` LXX helpers

Do not assume LXX is fully imported in every local database. Verify the actual
database tables before promising LXX completeness.

### BibleWorks-derived SQL dumps

The SQL dumps from Richard made the local pipeline practical. They are not
public distribution assets. Keep them local unless Richard explicitly approves a
different publishing plan.

### Formation search performance

The Forms tab currently searches existing word and phrase data at request time.
It is usable for short selections but should be indexed later if this becomes a
major feature.

Recommended later improvement:

- Add `formation_signature` and `formation_letter_count` columns/table.
- Precompute signatures for words.
- Precompute contiguous phrase signatures up to a small phrase length.
- Query signatures directly instead of scanning.

### Clause detection is manual

The app can analyze verse sections when the user selects the words. It does not
yet automatically detect clauses from syntax. Automatic clause detection would
need grammar/syntax rules and should be planned separately.

## 14. Suggested Next Improvements

High-value next steps:

1. Decide hosting path for the full public app.
2. If using PHP/MySQL hosting, deploy `web/` and import the database there.
3. If keeping GitHub Pages, add a remote API server and point the static app to
   it.
4. Improve full cross-edition side-by-side comparison beyond the current Compare
   tab.
5. Add indexed letter-formation search.
6. Add better iPhone gestures for range/phrase selection.
7. Add saved/shareable analysis links.
8. Add a clearer public/static banner explaining when the viewer is in preview
   mode.
9. Add automated smoke tests for PHP syntax and critical API endpoints.
10. Add a small demo dataset for public development that does not expose private
    dumps.

## 15. Verification Commands

From the repo root:

```sh
git status --short --branch
php -l web/index.php
php -l web/api.php
php -l web/search_lib.php
php -l web/db.php
```

With MAMP PHP explicitly:

```sh
/Applications/MAMP/bin/php/php/bin/php -l web/index.php
/Applications/MAMP/bin/php/php/bin/php -l web/api.php
/Applications/MAMP/bin/php/php/bin/php -l web/search_lib.php
/Applications/MAMP/bin/php/php/bin/php -l web/db.php
```

To run the local app manually without the launcher:

```sh
/Applications/MAMP/bin/php/php/bin/php -S 127.0.0.1:8888 -t web
```

Then open:

```text
http://127.0.0.1:8888/index.php?book=Gen&chapter=1&verse=1
```

## 16. Packaging Notes

A safe website zip should include:

- Source code.
- PHP app files.
- Static preview files.
- Docs and handoffs.
- SQL schema files.
- Import scripts.
- Mac launchers.
- PWA icons/manifest.

A safe website zip should not include:

- `.git/`
- `config.ini`
- `web/config.php`
- `data/raw/`
- `logs/`
- `.python-deps/`
- Any private SQL dumps.
- Any local database exports.
- Any SSH keys.

The cleanest packaging method after committing the intended files is:

```sh
git archive --format=zip --output ../BibleGematria_website_handoff.zip HEAD
```

That uses the tracked Git tree and automatically excludes ignored private local
files.

## 17. Human Context

Johan is controlling the MacBook and Codex from an iPhone. Do not assume that he
is sitting directly at the desktop with a full keyboard.

Keep instructions beginner-friendly:

- Say exactly what to click or double-click.
- Avoid vague phrases like "configure the environment" without concrete steps.
- Be explicit about what is safe and what is private.
- Do not delete local files unless Johan clearly asks for that specific action.

The user is understandably cautious about file access and deletion. Respect that:

- Inspect before changing.
- Explain what will be edited.
- Keep private data out of Git and zips.
- Use reversible Git commits for source-code changes.

