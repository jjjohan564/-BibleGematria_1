<?php
/**
 * Remote API client for the Bible Database.
 *
 * When 'use_remote_api' is true in config.php, the functions in db.php
 * will delegate to these remote versions instead of hitting the local DB.
 *
 * This allows developers to work on the UI without having the full
 * stepbible database installed locally.
 */

function remote_api_base(): string {
    static $base = null;
    if ($base !== null) return $base;

    $cfg_path = __DIR__ . '/config.php';
    if (!file_exists($cfg_path)) {
        die("Missing config.php for remote API base URL.");
    }
    $cfg = require $cfg_path;
    $base = rtrim($cfg['remote_api_base'] ?? '', '/');

    if ($base === '') {
        die("remote_api_base is not set in config.php");
    }
    return $base;
}

function remote_api_call(string $endpoint, array $params = []): ?array {
    $url = remote_api_base() . '/api.php?' . http_build_query(array_merge(['api' => $endpoint], $params));

    $context = stream_context_create([
        'http' => [
            'timeout' => 10,
            'ignore_errors' => true,
        ]
    ]);

    $response = @file_get_contents($url, false, $context);

    if ($response === false) {
        error_log("Remote API call failed: $url");
        return null;
    }

    $data = json_decode($response, true);
    if (json_last_error() !== JSON_ERROR_NONE) {
        error_log("Remote API returned invalid JSON: $url");
        return null;
    }

    if (isset($data['error'])) {
        error_log("Remote API error: " . $data['error']);
        return null;
    }

    return $data;
}

/**
 * Remote version of bible_verse_full
 */
function remote_bible_verse_full(string $osis_code, int $chapter, int $verse,
                                 ?string $edition_code = null): ?array {
    $params = [
        'book'    => $osis_code,
        'chapter' => $chapter,
        'verse'   => $verse,
    ];
    if ($edition_code) {
        $params['edition'] = $edition_code;
    }

    return remote_api_call('verse_full', $params);
}

/**
 * Remote version of lxx_verse_full
 */
function remote_lxx_verse_full(string $lxx_osis_code, int $chapter, int $verse,
                               string $sub = '', ?string $edition_code = null): ?array {
    $params = [
        'book'     => $lxx_osis_code,
        'chapter'  => $chapter,
        'verse'    => $verse,
        'subverse' => $sub,
    ];
    if ($edition_code) {
        $params['edition'] = $edition_code;
    }

    return remote_api_call('verse_full', $params);
}

// You can add more remote_* functions here as needed (bible_books, chapters, etc.)

function remote_bible_books(): array {
    return remote_api_call('books') ?? [];
}

function remote_bible_chapters(string $osis_code): array {
    return remote_api_call('chapters', ['book' => $osis_code]) ?? [];
}

function remote_bible_verses(string $osis_code, int $chapter): array {
    return remote_api_call('verses', ['book' => $osis_code, 'chapter' => $chapter]) ?? [];
}

function remote_bible_neighbor(string $osis_code, int $chapter, int $verse, string $direction): ?array {
    return remote_api_call('neighbor', [
        'book'      => $osis_code,
        'chapter'   => $chapter,
        'verse'     => $verse,
        'direction' => $direction,
    ]);
}

function remote_lxx_neighbor(string $lxx_osis_code, int $chapter, int $verse, string $subverse, string $direction): ?array {
    return remote_api_call('lxx_neighbor', [
        'book'      => $lxx_osis_code,
        'chapter'   => $chapter,
        'verse'     => $verse,
        'subverse'  => $subverse,
        'direction' => $direction,
    ]);
}

// Search helpers. These are thin wrappers over remote_api_call; the
// callers in db.php / search_lib.php can also call remote_api_call
// directly. Both styles coexist in this file.

function remote_bible_strongs_lookup(string $code): ?array {
    return remote_api_call('strongs', ['code' => $code]);
}

function remote_bible_kjv_verse_clean(string $osis_code, int $chapter, int $verse): ?array {
    return remote_api_call('kjv_verse', [
        'book'    => $osis_code,
        'chapter' => $chapter,
        'verse'   => $verse,
    ]);
}

function remote_bible_search_gematria(int $value): ?array {
    return remote_api_call('search_gematria', ['value' => $value]);
}

function remote_bible_search_verses(string $mode, string $q_raw, string $lang = ''): ?array {
    return remote_api_call('search_verses', [
        'mode' => $mode,
        'q'    => $q_raw,
        'lang' => $lang,
    ]);
}

function remote_els_fetch(string $book, int $chapter, int $verse, string $edition, int $letters): ?array {
    return remote_api_call('els_fetch', [
        'book'    => $book,
        'chapter' => $chapter,
        'verse'   => $verse,
        'edition' => $edition,
        'letters' => $letters,
    ]);
}
