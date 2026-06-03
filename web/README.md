# Bible Browser — PHP web UI

A drop-in PHP page that displays a full interlinear view of any verse.

**Two ways to run it:**

- **With a local database**: Requires PHP + the PDO MySQL extension.
- **Remote API mode** (recommended for external contributors): Only requires PHP. The UI fetches data from a remote instance instead of a local database. No database driver needed.

> **External contributors:** The web UI is ready for development even if you
> don’t have a local copy of the full database. Enable remote API mode in
> `config.php` to work against a live instance while the import pipeline
> is still being stabilized. See the “Remote development” section below.

## Files

| File                | Purpose                                                |
|---------------------|--------------------------------------------------------|
| `index.php`         | Main page — verse display + AJAX API for dropdowns     |
| `db.php`            | Database layer (supports both local PDO and remote API mode) |
| `style.css`         | Page styling                                           |
| `config.sample.php` | Sample DB credentials — copy to `config.php` and edit  |

## Setup

### 1. PHP requirements

- **Local database mode**: PHP 7.4+ with the `pdo_mysql` extension.
- **Remote API mode** (no local database): Just PHP 7.4+. No database extension required.

To check if you have the MySQL driver (only needed for local DB mode):

```
php -m | findstr pdo_mysql
```

If it prints `pdo_mysql`, the extension is enabled. You can enable it in `php.ini` with `extension=pdo_mysql` if needed.

### 2. Configure credentials

```cmd
copy config.sample.php config.php
notepad config.php
```

- **Local database mode**: Set your MariaDB credentials (host, user, password, database). On shared hosting the database name is often prefixed (e.g. `yourusername_stepbible`).
- **Remote API mode**: Set `'use_remote_api' => true` and provide a `'remote_api_base'` URL. You do **not** need local database credentials.

### 3. Serve the folder

Three options, pick whichever you have:

**Built-in PHP dev server** (zero install — just need `php` on PATH):
```cmd
# From the root of the BibleDB repository
cd web
php -S localhost:8080
```
Then open <http://localhost:8080> in your browser.

**Apache / XAMPP / WAMP**: copy the `web/` folder into your `htdocs`
(or symlink it), then open `http://localhost/web/`.

**IIS**: configure a virtual directory pointing at this folder.

## Running standalone (recommended for development)

The web UI can now run completely independently of the biblewheel.com site layout.

Just serve the `web/` folder directly:

```cmd
cd web
php -S localhost:8080
```

Then open http://localhost:8080

When the external `bwHeader.inc` / `bwBanner.php` files are not found, the UI automatically falls back to minimal local header and banner files (`local_header.inc.php` and `local_banner.inc.php`).

This makes it easy to develop the UI in isolation (especially when using remote API mode).

## Remote development (for external contributors)

You can develop and test the web UI without having the full local MariaDB database or running the Python import pipeline.

1. Copy `config.php.sample` → `config.php`
2. Edit `config.php` and set:
   ```php
   'use_remote_api' => true,
   'remote_api_base' => 'https://your-live-instance.example.com/bible',
   ```
3. The UI will now fetch data from the remote instance instead of your local database.

This is the recommended way for contributors to start working on the frontend while the data import side is still being stabilized.

**All features work in remote API mode**, including verse rendering, Strong's tooltips, KJV verse preview tooltips, grammar tooltips, gematria search, Strong's concordance, Hebrew / Greek / English text and phrase search, and the ELS (Equidistant Letter Sequence) grid. The architecture: client-side JS always fetches the *local* `api.php` on the same origin; the local PHP layer transparently proxies to the remote `api.php` via `remote_api_call()` when `use_remote_api` is true. No CORS configuration is needed and no client-side code needs to know whether it's running locally or remotely.

The one exception is page view stats (`stats.php`), which is intentionally disabled in remote mode — view counts are per-instance private data, mirroring the existing privacy policy on the `?api=viewcount` endpoint.

For this to work, the remote (live) site must be running the same code as your local checkout, since it has to expose the same `?api=*` endpoints. If you maintain the live site, deploy `web/api.php`, `web/db.php`, `web/search_lib.php`, `web/els_lib.php`, and `web/remote_api.php` whenever those change.

## Using the page

Two ways to navigate to a verse:

* **Dropdowns**: pick Book → Chapter → Verse. Chapter and Verse lists
  refresh automatically when you change Book / Chapter (via the JSON
  API at `?api=chapters&book=…` / `?api=verses&book=…&chapter=…`).
* **Reference text box**: type a free-form reference like `Jhn 3:16`,
  `1 Cor 13:13`, `Gen 1.1`, `Psalm 23:1`. Common abbreviations
  (Matt, Mt, Mk, Jn, 1Cor, Phlm, Rev, Ps, Song, etc.) are recognized.

The verse view shows:

1. **Assembled text** — the original-language line and the assembled
   English line (Hebrew rendered RTL).
2. **Word-by-word table** — one row per word with position, original
   text, transliteration (Hebrew only), English gloss, Strong's number,
   morphology code, and source type.
3. **Per-word detail** — directly under each word: the editions that
   contain it, alt Strong's, lemma/gloss, sub-meaning, conjoin links,
   Hebrew morpheme breakdown, and any textual variants (with the
   editions that support each variant).
4. **Source verse-summary blocks** — collapsible at the bottom, showing
   the verbatim `#_Translation` / `#_Word=Grammar` lines from the
   original STEPBible files for round-trip reference.

## Next steps

This first cut is reference lookup only. Future iterations can add:

* Strong's-number concordance (`?strongs=G2316`)
* English keyword search across `verse.text_english`
* Filter by edition (e.g. show only words present in NA28 but missing
  from TR)
* Filter by variant kind / book range
