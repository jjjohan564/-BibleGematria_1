<?php
// PDO connection helper. Loads credentials from config.php (which the user
// creates by copying config.sample.php). Returns a PDO instance.

require_once __DIR__ . '/remote_api.php';

function bible_pdo(): PDO {
    // Guard: never allow local DB access when remote API mode is enabled.
    if (should_use_remote_api()) {
        $cfg = require __DIR__ . '/config.php';

        $msg = "Direct local database access is disabled (use_remote_api is true in config.php).";

        if (!empty($cfg['debug'])) {
            $trace = debug_backtrace(DEBUG_BACKTRACE_IGNORE_ARGS, 8);
            $caller = $trace[1] ?? [];
            $msg .= "<br><br><strong>Called from:</strong> " . 
                    htmlspecialchars(($caller['class'] ?? '') . ($caller['type'] ?? '') . ($caller['function'] ?? '')) .
                    " in " . htmlspecialchars($caller['file'] ?? '') . ":" . ($caller['line'] ?? '') . "<br><br>";

            $msg .= "<strong>Stack trace (first few frames):</strong><pre>" . 
                    htmlspecialchars(print_r(array_slice($trace, 0, 6), true)) . "</pre>";
        } else {
            $msg .= " Some code paths are not yet routed through the remote API. Enable debug in config.php for details.";
        }

        // Only try to set status code if headers haven't been sent yet.
        if (!headers_sent()) {
            http_response_code(500);
        }

        die($msg);
    }

    static $pdo = null;
    if ($pdo !== null) {
        return $pdo;
    }
    $cfg_path = __DIR__ . '/config.php';
    if (!file_exists($cfg_path)) {
        http_response_code(500);
        die("Missing config.php — copy config.sample.php to config.php and set your DB credentials.");
    }
    $cfg = require $cfg_path;

    $dsn = sprintf(
        'mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4',
        $cfg['host'], $cfg['port'], $cfg['database']
    );
    $opts = [
        PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES   => false,
        PDO::MYSQL_ATTR_INIT_COMMAND => "SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci",
    ];
    try {
        $pdo = new PDO($dsn, $cfg['user'], $cfg['password'], $opts);
    } catch (PDOException $e) {
        http_response_code(500);
        if (!empty($cfg['debug'])) {
            die("DB connection failed: " . htmlspecialchars($e->getMessage()));
        }
        die("DB connection failed.");
    }
    return $pdo;
}

/**
 * Returns true if we should use the remote API instead of local DB.
 * Controlled by 'use_remote_api' in config.php.
 */
function should_use_remote_api(): bool {
    static $use_remote = null;
    if ($use_remote !== null) return $use_remote;

    $cfg_path = __DIR__ . '/config.php';
    if (!file_exists($cfg_path)) {
        return false;
    }
    $cfg = require $cfg_path;
    $use_remote = !empty($cfg['use_remote_api']);

    // If remote mode is on but no base URL is set, fall back to local DB with a warning
    if ($use_remote && empty($cfg['remote_api_base'])) {
        error_log('use_remote_api is true but remote_api_base is empty — falling back to local DB.');
        $use_remote = false;
    }

    return $use_remote;
}

// ===================================================================
// MT / NT query helpers (existing 11-table v2 schema)
// ===================================================================

function bible_books(): array {
    if (should_use_remote_api()) {
        return remote_api_call('books') ?? [];
    }

    $stmt = bible_pdo()->query(
        "SELECT id, osis_code, name, testament, language
           FROM book
          ORDER BY book_order"
    );
    return $stmt->fetchAll();
}

function bible_chapters(string $osis_code): array {
    if (should_use_remote_api()) {
        return remote_bible_chapters($osis_code);
    }

    $sql = "SELECT DISTINCT v.chapter
              FROM verse v JOIN book b ON b.id = v.book_id
             WHERE b.osis_code = ?
             ORDER BY v.chapter";
    $stmt = bible_pdo()->prepare($sql);
    $stmt->execute([$osis_code]);
    return array_column($stmt->fetchAll(), 'chapter');
}

function bible_verses(string $osis_code, int $chapter): array {
    if (should_use_remote_api()) {
        return remote_bible_verses($osis_code, $chapter);
    }

    $sql = "SELECT v.verse
              FROM verse v JOIN book b ON b.id = v.book_id
             WHERE b.osis_code = ? AND v.chapter = ?
             ORDER BY v.verse";
    $stmt = bible_pdo()->prepare($sql);
    $stmt->execute([$osis_code, $chapter]);
    return array_column($stmt->fetchAll(), 'verse');
}

// Look up edition.id from a code like 'NA28' (or null). Cached.
function bible_edition_id(?string $code): ?int {
    if (should_use_remote_api()) {
        // Not needed in remote mode for most paths
        return null;
    }

    static $cache = null;
    if ($code === null || $code === '') return null;
    if ($cache === null) {
        $cache = [];
        $stmt = bible_pdo()->query("SELECT id, code FROM edition");
        foreach ($stmt->fetchAll() as $r) $cache[$r['code']] = (int)$r['id'];
    }
    return $cache[$code] ?? null;
}

// Editions surfaced in the UI dropdown. NA28 / TR are NT critical/Byz texts;
// LXX-Rahlfs is a *mode switch* — selecting it routes lookups to the LXX
// tables (book_lxx / verse_lxx / word_lxx) via the lxx_* helpers below.
function bible_greek_editions(): array {
    if (should_use_remote_api()) {
        // Static list for remote mode (avoids local DB)
        return [
            ['id' => 1, 'code' => 'NA28',        'name' => 'Nestle-Aland 28th'],
            ['id' => 2, 'code' => 'TR',          'name' => 'Textus Receptus'],
            ['id' => 3, 'code' => 'LXX-Rahlfs',  'name' => 'Rahlfs LXX 1935'],
        ];
    }

    $stmt = bible_pdo()->query(
        "SELECT id, code, name FROM edition
          WHERE code IN ('NA28','TR','LXX-Rahlfs')
          ORDER BY edition_order"
    );
    return $stmt->fetchAll();
}

// Look up a Strong's entry by canonical lookup key (e.g. 'H430', 'G851').
// Returns ['number','lemma','xlit','pronounce','description'] or null on miss.
function bible_strongs_lookup(string $code): ?array {
    static $cache = [];
    if ($code === '' || !preg_match('/^[HG]\d+[A-Za-z]?$/', $code)) return null;
    if (array_key_exists($code, $cache)) return $cache[$code];

    if (should_use_remote_api()) {
        $row = remote_api_call('strongs', ['code' => $code]);
        return $cache[$code] = (is_array($row) && !empty($row) ? $row : null);
    }

    $stmt = bible_pdo()->prepare(
        "SELECT number, lemma, xlit, pronounce, description
           FROM strongs WHERE number = ? LIMIT 1"
    );
    $stmt->execute([$code]);
    $row = $stmt->fetch();
    return $cache[$code] = ($row ?: null);
}

// Look up the clean (tag-stripped) KJV text for one verse. Used by the
// verse-tooltip API in search.php. Returns null on miss or in remote mode
// where the remote API serves the same endpoint.
function bible_kjv_verse_clean(string $osis_code, int $chapter, int $verse): ?string {
    static $cache = [];
    $key = "$osis_code.$chapter.$verse";
    if (array_key_exists($key, $cache)) return $cache[$key];

    if (should_use_remote_api()) {
        $resp = remote_api_call('kjv_verse', [
            'book'    => $osis_code,
            'chapter' => $chapter,
            'verse'   => $verse,
        ]);
        $text = is_array($resp) ? ($resp['text'] ?? null) : null;
        return $cache[$key] = (is_string($text) ? $text : null);
    }

    try {
        $pdo = bible_pdo();
        // Resolve book_id once so we can pass it to both queries and to
        // kjv_alt_ref() (which is keyed by book_id, not osis_code).
        $bk = $pdo->prepare("SELECT id FROM book WHERE osis_code = ? LIMIT 1");
        $bk->execute([$osis_code]);
        $book_id = (int)($bk->fetchColumn() ?: 0);
        if ($book_id === 0) return $cache[$key] = null;

        $stmt = $pdo->prepare(
            'SELECT Verse_Text_Clean FROM bible_kjv
              WHERE Book = ? AND Chapter = ? AND Verse = ? LIMIT 1'
        );
        $stmt->execute([$book_id, $chapter, $verse]);
        $row = $stmt->fetch();
        if ($row) return $cache[$key] = (string)$row['Verse_Text_Clean'];

        // Direct miss — check the NA28→KJV versification remap.
        if (($alt = kjv_alt_ref($book_id, $chapter, $verse)) !== null) {
            $stmt->execute([$book_id, $alt['chapter'], $alt['verse']]);
            $row = $stmt->fetch();
            if ($row) return $cache[$key] = (string)$row['Verse_Text_Clean'];
        }
        return $cache[$key] = null;
    } catch (Throwable $e) {
        return $cache[$key] = null;
    }
}

// Resolve a (book_osis, chapter, verse) into the verse row plus all
// joined per-word data (words, editions, variants, morphemes, links,
// alt strongs). When $edition_code is set and the verse is Greek, the
// returned `words` list is the edition-specific position-sorted merge
// of canonical words (filtered by word_edition) and variants (filtered
// by variant_edition). When $edition_code is null, the canonical word
// list is returned unchanged.
function bible_verse_full(string $osis_code, int $chapter, int $verse,
                          ?string $edition_code = null): ?array {
    if (should_use_remote_api()) {
        return remote_bible_verse_full($osis_code, $chapter, $verse, $edition_code);
    }

    $pdo = bible_pdo();

    $stmt = $pdo->prepare(
        "SELECT v.*, b.osis_code, b.name AS book_name,
                b.testament, b.language
           FROM verse v JOIN book b ON b.id = v.book_id
          WHERE b.osis_code = ? AND v.chapter = ? AND v.verse = ?"
    );
    $stmt->execute([$osis_code, $chapter, $verse]);
    $vrow = $stmt->fetch();
    if (!$vrow) return null;
    $verse_id = (int)$vrow['id'];

    $edition_id = ($vrow['language'] === 'Greek') ? bible_edition_id($edition_code) : null;
    $words = bible_assemble_words($pdo, $verse_id, $edition_id, $edition_code);

    $stmt = $pdo->prepare(
        "SELECT * FROM verse_summary WHERE verse_id = ? ORDER BY block_num"
    );
    $stmt->execute([$verse_id]);
    $summaries = $stmt->fetchAll();

    bible_attach_per_word_data($pdo, $words, $vrow['language']);

    return ['verse' => $vrow, 'words' => $words, 'summaries' => $summaries];
}

// Merge canonical words and variant rows by position. For an edition E:
//   - canonical words tagged with E in word_edition are kept
//   - variants tagged with E in variant_edition are merged in:
//       * variant.position == canonical word's position -> variant substitutes
//         (or, for kind='omission', drops the slot entirely)
//       * variant.position has no matching canonical word -> variant fills
//         the slot on its own (e.g. John 1:18 'υἱός' in TR -- canonical
//         θεος isn't tagged for TR, variant is)
//       * fractional positions (e.g. 4.5) -> variant inserts as a new slot
function bible_assemble_words(PDO $pdo, int $verse_id,
                              ?int $edition_id, ?string $edition_code): array {
    if ($edition_id === null) {
        $stmt = $pdo->prepare(
            "SELECT * FROM word WHERE verse_id = ? ORDER BY position"
        );
        $stmt->execute([$verse_id]);
        return $stmt->fetchAll();
    }

    $stmt = $pdo->prepare(
        "SELECT w.*
           FROM word w
           JOIN word_edition we ON we.word_id = w.id
                              AND we.edition_id = ?
          WHERE w.verse_id = ?"
    );
    $stmt->execute([$edition_id, $verse_id]);
    $canonical = $stmt->fetchAll();

    $stmt = $pdo->prepare(
        "SELECT v.*
           FROM variant v
           JOIN word w ON w.id = v.word_id
           JOIN variant_edition ve ON ve.variant_id = v.id
                                  AND ve.edition_id = ?
          WHERE w.verse_id = ?"
    );
    $stmt->execute([$edition_id, $verse_id]);
    $variants = $stmt->fetchAll();

    $slots = [];   // string(position) => ['word' => ..., 'variant' => ...]

    // sprintf('%.2f') normalizes slot keys (word.position is SMALLINT,
    // variant.position is DECIMAL(6,2) — without this they'd collide).
    foreach ($canonical as $w) {
        $key = sprintf('%.2f', (float)$w['position']);
        $slots[$key] = ['word' => $w, 'variant' => null];
    }
    foreach ($variants as $v) {
        $key = sprintf('%.2f', (float)$v['position']);
        if (!isset($slots[$key])) {
            $slots[$key] = ['word' => null, 'variant' => $v];
        } else {
            $slots[$key]['variant'] = $v;
        }
    }

    uksort($slots, fn($a, $b) => (float)$a <=> (float)$b);

    $out = [];
    foreach ($slots as $slot) {
        $w = $slot['word'];
        $v = $slot['variant'];

        if ($v && $v['kind'] === 'omission') continue;

        if ($w && $v) {
            $w['canonical_text_original']   = $w['text_original'];
            $w['canonical_transliteration'] = $w['transliteration'] ?? null;
            $w['canonical_translation']     = $w['translation']     ?? null;
            $w['canonical_strongs']         = $w['strongs']         ?? null;
            $w['canonical_grammar']         = $w['grammar']         ?? null;
            if (!empty($v['text_original']))   $w['text_original']   = $v['text_original'];
            if (!empty($v['transliteration'])) $w['transliteration'] = $v['transliteration'];
            if (!empty($v['translation']))     $w['translation']     = $v['translation'];
            if (!empty($v['strongs']))         $w['strongs']         = $v['strongs'];
            if (!empty($v['grammar']))         $w['grammar']         = $v['grammar'];
            $w['source_variant_id'] = (int)$v['id'];
            $out[] = $w;
        } elseif ($w) {
            $out[] = $w;
        } elseif ($v) {
            $out[] = bible_variant_as_word_row($v, $verse_id, $edition_code);
        }
    }
    return $out;
}

function bible_variant_as_word_row(array $v, int $verse_id, ?string $edition_code): array {
    return [
        'id'                => -((int)$v['id']),
        'verse_id'          => $verse_id,
        'book_id'           => null,
        'chapter'           => 0,
        'verse'             => 0,
        'position'          => $v['position'],
        'word_num'          => 0,
        'chunk_num'         => 1,
        'source_type'       => $v['kind'],
        'is_variant_marked' => 1,
        'language'          => 'Greek',
        'text_original'     => $v['text_original']   ?? '',
        'transliteration'   => $v['transliteration'] ?? '',
        'translation'       => $v['translation']     ?? '',
        'strongs'           => $v['strongs']         ?? '',
        'strongs_primary'   => '',
        'grammar'           => $v['grammar']         ?? '',
        'dictionary_form'   => '',
        'submeaning'        => '',
        'sstrong_instance'  => '',
        'text_search'       => '',
        'source_variant_id' => (int)$v['id'],
    ];
}

function bible_attach_per_word_data(PDO $pdo, array &$words, string $language): void {
    if (empty($words)) return;

    $real_ids = [];
    foreach ($words as $w) {
        $wid = (int)$w['id'];
        if ($wid > 0) $real_ids[] = $wid;
    }

    $eds = $alts = $morphs = $links = $vars = $gem = [];

    if (!empty($real_ids)) {
        $marks = implode(',', array_fill(0, count($real_ids), '?'));

        $stmt = $pdo->prepare("SELECT we.word_id, e.code, e.name, we.is_minor
                                 FROM word_edition we JOIN edition e ON e.id = we.edition_id
                                WHERE we.word_id IN ($marks)
                                ORDER BY e.edition_order");
        $stmt->execute($real_ids);
        foreach ($stmt->fetchAll() as $r) $eds[(int)$r['word_id']][] = $r;

        $stmt = $pdo->prepare("SELECT word_id, alt_strong FROM word_alt_strong
                                WHERE word_id IN ($marks) ORDER BY id");
        $stmt->execute($real_ids);
        foreach ($stmt->fetchAll() as $r) $alts[(int)$r['word_id']][] = $r['alt_strong'];

        $stmt = $pdo->prepare("SELECT * FROM word_morpheme WHERE word_id IN ($marks)
                                ORDER BY word_id, morpheme_num");
        $stmt->execute($real_ids);
        foreach ($stmt->fetchAll() as $r) $morphs[(int)$r['word_id']][] = $r;

        $stmt = $pdo->prepare("SELECT wl.*, tw.text_original AS target_text
                                 FROM word_link wl
                                 LEFT JOIN word tw ON tw.id = wl.target_word_id
                                WHERE wl.word_id IN ($marks)");
        $stmt->execute($real_ids);
        foreach ($stmt->fetchAll() as $r) $links[(int)$r['word_id']][] = $r;

        $stmt = $pdo->prepare("SELECT DISTINCT v.* FROM variant v
                                JOIN variant_edition ve ON ve.variant_id = v.id
                               WHERE v.word_id IN ($marks)
                                 AND ve.edition_id IN (1,2,7,8,11,12)
                               ORDER BY v.word_id, v.position, v.id");
        $stmt->execute($real_ids);
        foreach ($stmt->fetchAll() as $r) $vars[(int)$r['word_id']][] = $r + ['editions' => []];

        $vids = [];
        foreach ($vars as $vlist) foreach ($vlist as $v) $vids[] = (int)$v['id'];
        if (!empty($vids)) {
            $vmarks = implode(',', array_fill(0, count($vids), '?'));
            $stmt = $pdo->prepare("SELECT ve.variant_id, e.code, e.name, ve.is_minor
                                     FROM variant_edition ve
                                     JOIN edition e ON e.id = ve.edition_id
                                    WHERE ve.variant_id IN ($vmarks)
                                    ORDER BY e.edition_order");
            $stmt->execute($vids);
            $ve_by_var = [];
            foreach ($stmt->fetchAll() as $r) $ve_by_var[(int)$r['variant_id']][] = $r;
            foreach ($vars as &$vlist) foreach ($vlist as &$v) {
                $v['editions'] = $ve_by_var[(int)$v['id']] ?? [];
            }
            unset($vlist, $v);
        }

        try {
            $stmt = $pdo->prepare("SELECT word_id, standard, ordinal, reduced
                                     FROM gematria_word WHERE word_id IN ($marks)");
            $stmt->execute($real_ids);
            foreach ($stmt->fetchAll() as $r) $gem[(int)$r['word_id']] = $r;
        } catch (Throwable $e) { /* table missing -- degrade silently */ }
    }

    foreach ($words as &$w) {
        $wid = (int)$w['id'];
        $is_real = $wid > 0;
        $w['editions']  = $is_real ? ($eds[$wid]   ?? []) : [];
        $w['alts']      = $is_real ? ($alts[$wid]  ?? []) : [];
        $w['morphemes'] = $is_real ? ($morphs[$wid]?? []) : [];
        $w['links']     = $is_real ? ($links[$wid] ?? []) : [];
        $w['variants']  = $is_real ? ($vars[$wid]  ?? []) : [];
        $g = $is_real ? ($gem[$wid] ?? null) : null;
        $w['gem_std'] = $g ? (int)$g['standard'] : 0;
        $w['gem_ord'] = $g ? (int)$g['ordinal']  : 0;
        $w['gem_red'] = $g ? (int)$g['reduced']  : 0;
    }
    unset($w);
}


// Map for navigation: previous/next verse references.
function bible_neighbor(string $osis_code, int $chapter, int $verse, string $direction): ?array {
    if (should_use_remote_api()) {
        return remote_bible_neighbor($osis_code, $chapter, $verse, $direction);
    }

    $pdo = bible_pdo();
    if ($direction === 'next') {
        $sql = "SELECT b.osis_code, v.chapter, v.verse
                  FROM verse v JOIN book b ON b.id = v.book_id
                 WHERE (b.book_order, v.chapter, v.verse) > (
                       (SELECT book_order FROM book WHERE osis_code = ?),
                       ?, ?)
                 ORDER BY b.book_order, v.chapter, v.verse
                 LIMIT 1";
    } else {
        $sql = "SELECT b.osis_code, v.chapter, v.verse
                  FROM verse v JOIN book b ON b.id = v.book_id
                 WHERE (b.book_order, v.chapter, v.verse) < (
                       (SELECT book_order FROM book WHERE osis_code = ?),
                       ?, ?)
                 ORDER BY b.book_order DESC, v.chapter DESC, v.verse DESC
                 LIMIT 1";
    }
    $stmt = $pdo->prepare($sql);
    $stmt->execute([$osis_code, $chapter, $verse]);
    return $stmt->fetch() ?: null;
}


// ===================================================================
// KJV English text (the `bible_kjv` table inside stepbible)
// ===================================================================
// bible_kjv is keyed by stepbible book.id (1..66 canonical OT+NT),
// Chapter, Verse. Verse_Text carries inline Strong's tags like
// "In the beginning <07225> God <0430> created <01254> ..."; the tags
// follow the English word they refer to. Verse_Text_Clean is the same
// text with the tags stripped.
//
// Cross-tradition versification mismatches (Rev 12:18, Php 1:16/1:17,
// 2Co 13:13, 3Jn 1:15) are handled via the `verse_kjv_alt` table — see
// kjv_alt_ref() below and scripts/maintenance/fix_kjv_versification.py.
//
// Returns null only when the verse genuinely has no KJV mapping (e.g.
// the table is missing) — the caller falls back to the STEPBible English.

// Look up an NA28-style ref in verse_kjv_alt. Returns ['chapter','verse']
// for the KJV equivalent, or null if no remap applies. Caches the whole
// table on first call (it's tiny — single-digit rows).
function kjv_alt_ref(int $book_id, int $chapter, int $verse): ?array {
    static $cache = null;
    if ($cache === null) {
        $cache = [];
        try {
            $stmt = bible_pdo()->query(
                "SELECT book_id, na28_chapter, na28_verse, kjv_chapter, kjv_verse
                   FROM verse_kjv_alt"
            );
            foreach ($stmt->fetchAll() as $r) {
                $k = (int)$r['book_id'] . '|' . (int)$r['na28_chapter']
                   . '|' . (int)$r['na28_verse'];
                $cache[$k] = [
                    'chapter' => (int)$r['kjv_chapter'],
                    'verse'   => (int)$r['kjv_verse'],
                ];
            }
        } catch (Throwable $e) {
            // Table missing (e.g. script hasn't been run yet) — degrade
            // silently and let direct lookups continue to work.
        }
    }
    return $cache["$book_id|$chapter|$verse"] ?? null;
}

function kjv_verse_text(int $book_id, int $chapter, int $verse): ?string {
    // In remote API mode we don't have the bible_kjv table locally.
    // Fall back to the English text that comes from the remote data.
    if (should_use_remote_api()) {
        return null;
    }

    static $cache = [];
    $key = "$book_id.$chapter.$verse";
    if (array_key_exists($key, $cache)) return $cache[$key];
    try {
        $pdo  = bible_pdo();
        $stmt = $pdo->prepare(
            "SELECT Verse_Text
               FROM bible_kjv
              WHERE Book = ? AND Chapter = ? AND Verse = ?
              LIMIT 1"
        );
        $stmt->execute([$book_id, $chapter, $verse]);
        $row = $stmt->fetch();
        if ($row) {
            return $cache[$key] = (string)$row['Verse_Text'];
        }
        // Direct miss — check the NA28→KJV versification remap.
        if (($alt = kjv_alt_ref($book_id, $chapter, $verse)) !== null) {
            $stmt->execute([$book_id, $alt['chapter'], $alt['verse']]);
            $row = $stmt->fetch();
            if ($row) return $cache[$key] = (string)$row['Verse_Text'];
        }
        return $cache[$key] = null;
    } catch (PDOException $e) {
        return $cache[$key] = null;
    }
}

// Return the global Verse_Order (1..31102) for a given verse, or null if not
// found in bible_kjv (verse=0 psalm titles have no KJV row).
function kjv_verse_order(int $book_id, int $chapter, int $verse): ?int {
    // In remote API mode we don't have the bible_kjv table locally.
    if (should_use_remote_api()) {
        return null;
    }

    static $cache = [];
    $key = "$book_id.$chapter.$verse";
    if (array_key_exists($key, $cache)) return $cache[$key];
    if ($verse === 0) return $cache[$key] = null;
    try {
        $pdo  = bible_pdo();
        $stmt = $pdo->prepare(
            "SELECT Verse_Order
               FROM bible_kjv
              WHERE Book = ? AND Chapter = ? AND Verse = ?
              LIMIT 1"
        );
        $stmt->execute([$book_id, $chapter, $verse]);
        $row = $stmt->fetch();
        if ($row) return $cache[$key] = (int)$row['Verse_Order'];
        // Direct miss — check the NA28→KJV versification remap.
        if (($alt = kjv_alt_ref($book_id, $chapter, $verse)) !== null) {
            $stmt->execute([$book_id, $alt['chapter'], $alt['verse']]);
            $row = $stmt->fetch();
            if ($row) return $cache[$key] = (int)$row['Verse_Order'];
        }
        return $cache[$key] = null;
    } catch (PDOException $e) {
        return $cache[$key] = null;
    }
}


// ===================================================================
// LXX query helpers (book_lxx / verse_lxx / word_lxx)
// ===================================================================
// These mirror the bible_* set above but target the LXX tables.
// The web UI routes to these when edition_code = 'LXX-Rahlfs'.

function lxx_books(): array {
    // Synthesize testament/language to match bible_books()'s shape so the
    // existing index.php template can iterate the result uniformly.
    $stmt = bible_pdo()->query(
        "SELECT id, osis_code, name,
                'OT'    AS testament,
                'Greek' AS language,
                mt_parallel_osis, tradition, rahlfs_code, book_order
           FROM book_lxx
          ORDER BY book_order"
    );
    return $stmt->fetchAll();
}

function lxx_chapters(string $lxx_osis_code): array {
    $sql = "SELECT DISTINCT v.chapter
              FROM verse_lxx v JOIN book_lxx b ON b.id = v.book_id
             WHERE b.osis_code = ?
             ORDER BY v.chapter";
    $stmt = bible_pdo()->prepare($sql);
    $stmt->execute([$lxx_osis_code]);
    return array_column($stmt->fetchAll(), 'chapter');
}

// Returns one row per (verse, subverse) — Esther 1:1, 1:1a, 1:1b ...
// emit as separate rows so the verse dropdown can step through them.
function lxx_verses(string $lxx_osis_code, int $chapter): array {
    $sql = "SELECT v.verse, v.subverse
              FROM verse_lxx v JOIN book_lxx b ON b.id = v.book_id
             WHERE b.osis_code = ? AND v.chapter = ?
             ORDER BY v.verse, v.subverse";
    $stmt = bible_pdo()->prepare($sql);
    $stmt->execute([$lxx_osis_code, $chapter]);
    return $stmt->fetchAll();
}

// Look up a single LXX book row by osis_code.
function lxx_book_by_osis(string $lxx_osis_code): ?array {
    static $cache = [];
    if (array_key_exists($lxx_osis_code, $cache)) return $cache[$lxx_osis_code];
    $stmt = bible_pdo()->prepare(
        "SELECT id, osis_code, name, mt_parallel_osis, tradition, rahlfs_code, book_order
           FROM book_lxx WHERE osis_code = ? LIMIT 1"
    );
    $stmt->execute([$lxx_osis_code]);
    $row = $stmt->fetch();
    return $cache[$lxx_osis_code] = ($row ?: null);
}

// Given an MT osis_code (e.g. 'Gen'), return the *primary* LXX book row
// that parallels it (e.g. LxxGen). Prefers tradition='LXX' over 'LXX-alt',
// 'LXX-OG', 'Theodotion'. Returns null if no LXX parallel exists.
function lxx_book_by_mt_osis(string $mt_osis_code): ?array {
    static $cache = [];
    if (array_key_exists($mt_osis_code, $cache)) return $cache[$mt_osis_code];
    $stmt = bible_pdo()->prepare(
        "SELECT id, osis_code, name, mt_parallel_osis, tradition, rahlfs_code, book_order
           FROM book_lxx
          WHERE mt_parallel_osis = ?
          ORDER BY FIELD(tradition,'LXX','LXX-OG','LXX-alt','Theodotion'),
                   book_order
          LIMIT 1"
    );
    $stmt->execute([$mt_osis_code]);
    $row = $stmt->fetch();
    return $cache[$mt_osis_code] = ($row ?: null);
}

// Resolve (lxx_osis_code, chapter, verse, subverse) into the LXX verse row
// + word list. Mirrors bible_verse_full's return shape: ['verse', 'words',
// 'summaries'] (summaries is always empty for LXX rows since we have no
// equivalent of verse_summary).
function lxx_verse_full(string $lxx_osis_code, int $chapter, int $verse,
                        string $subverse = ''): ?array {
    if (should_use_remote_api()) {
        return remote_lxx_verse_full($lxx_osis_code, $chapter, $verse, $subverse);
    }

    $pdo = bible_pdo();

    // SELECT synthesizes the columns the index.php template expects from
    // the MT verse shape (has_significant_variant, testament, language)
    // so the rendering path stays unified.
    $stmt = $pdo->prepare(
        "SELECT v.*, b.osis_code, b.name AS book_name,
                b.mt_parallel_osis, b.tradition, b.rahlfs_code,
                'OT' AS testament, 'Greek' AS language,
                0 AS has_significant_variant
           FROM verse_lxx v JOIN book_lxx b ON b.id = v.book_id
          WHERE b.osis_code = ? AND v.chapter = ? AND v.verse = ? AND v.subverse = ?
          LIMIT 1"
    );
    $stmt->execute([$lxx_osis_code, $chapter, $verse, $subverse]);
    $vrow = $stmt->fetch();
    if (!$vrow) return null;
    $verse_id = (int)$vrow['id'];

    // Load words. Synthesize the canonical_* and editions/alts/morphemes/
    // links/variants keys the template expects, so the interlinear renderer
    // doesn't have to special-case LXX rows.
    $stmt = $pdo->prepare(
        "SELECT * FROM word_lxx WHERE verse_id = ? ORDER BY position"
    );
    $stmt->execute([$verse_id]);
    $words_raw = $stmt->fetchAll();

    // Gather gematria for the LXX words if the precompute table covers them.
    // (gematria_word.word_id references word.id, not word_lxx.id. For LXX
    // rows we compute on-the-fly in the JS layer via syncGematriaOnLoad.)
    $words = [];
    foreach ($words_raw as $w) {
        $w['language']                = 'Greek';
        $w['word_num']                = (int)$w['position'];
        $w['chunk_num']               = 1;
        $w['source_type']             = 'LXX';
        $w['is_variant_marked']       = 0;
        $w['submeaning']              = $w['lemma'] ?? '';
        $w['sstrong_instance']        = '';
        $w['canonical_text_original'] = $w['text_original'];
        $w['canonical_transliteration'] = $w['transliteration'] ?? null;
        $w['canonical_translation']   = $w['translation']     ?? null;
        $w['canonical_strongs']       = $w['strongs']         ?? null;
        $w['canonical_grammar']       = $w['grammar']         ?? null;
        $w['source_variant_id']       = null;
        $w['editions']                = [['code' => 'LXX-Rahlfs',
                                          'name' => 'LXX Rahlfs 1935',
                                          'is_minor' => 0]];
        $w['alts']                    = [];
        $w['morphemes']               = [];
        $w['links']                   = [];
        $w['variants']                = [];
        // Gematria is computed client-side from the displayed Greek
        // (variant-switcher.js: syncGematriaOnLoad). Seed with zeros.
        $w['gem_std'] = 0;
        $w['gem_ord'] = 0;
        $w['gem_red'] = 0;
        $words[] = $w;
    }

    return ['verse' => $vrow, 'words' => $words, 'summaries' => []];
}

// Walk LXX verses in book_order/chapter/verse/subverse order to find
// the previous or next LXX verse. Returns ['osis_code', 'chapter',
// 'verse', 'subverse'] or null at canon ends.
function lxx_neighbor(string $lxx_osis_code, int $chapter, int $verse,
                      string $subverse, string $direction): ?array {
    if (should_use_remote_api()) {
        return remote_lxx_neighbor($lxx_osis_code, $chapter, $verse, $subverse, $direction);
    }

    $pdo = bible_pdo();
    if ($direction === 'next') {
        $sql = "SELECT b.osis_code, v.chapter, v.verse, v.subverse
                  FROM verse_lxx v JOIN book_lxx b ON b.id = v.book_id
                 WHERE (b.book_order, v.chapter, v.verse, v.subverse) > (
                       (SELECT book_order FROM book_lxx WHERE osis_code = ?),
                       ?, ?, ?)
                 ORDER BY b.book_order, v.chapter, v.verse, v.subverse
                 LIMIT 1";
    } else {
        $sql = "SELECT b.osis_code, v.chapter, v.verse, v.subverse
                  FROM verse_lxx v JOIN book_lxx b ON b.id = v.book_id
                 WHERE (b.book_order, v.chapter, v.verse, v.subverse) < (
                       (SELECT book_order FROM book_lxx WHERE osis_code = ?),
                       ?, ?, ?)
                 ORDER BY b.book_order DESC, v.chapter DESC, v.verse DESC,
                          v.subverse DESC
                 LIMIT 1";
    }
    $stmt = $pdo->prepare($sql);
    $stmt->execute([$lxx_osis_code, $chapter, $verse, $subverse]);
    return $stmt->fetch() ?: null;
}
