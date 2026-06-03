<?php
// search_lib.php — Search data-gathering helpers.
//
// Pulled out of search.php so the same code can be reached two ways:
//   • Local mode: search.php calls these directly and renders the result.
//   • Remote API mode: search.php receives a raw row payload from
//     api.php (which calls these on the remote server) and renders it
//     identically. The render side is therefore unchanged.
//
// All helpers return plain PHP arrays that JSON-serialise cleanly.

require_once __DIR__ . '/db.php';

const SEARCH_RESULT_LIMIT       = 6001;   // verse-list LIMIT (search.php trims to 6000)
const SEARCH_GEMATRIA_OCC_LIMIT = 6000;   // gematria total-occurrence cap

// Escape LIKE special characters in a user-supplied string so that '%' and '_'
// are treated as literals, not wildcards. Duplicated here from search.php so
// callers of these helpers don't need search.php's locals.
function search_escape_like(string $s): string {
    return str_replace(['\\', '%', '_'], ['\\\\', '\\%', '\\_'], $s);
}

// Normalise a Hebrew/Greek query string for comparison against word.text_search
// / verse.text_search (which are stored already-normalised). The rules match
// add_text_search.py / add_verse_search.py on the import side.
function search_normalize_query(string $text, string $lang): string {
    $text = preg_replace('/\s*\([^)]+\)/u', '', $text);   // strip transliteration parens
    $text = str_replace(['/', '\\'], '', $text);           // strip STEPBible separators
    $text = trim($text);

    if (strtolower($lang) === 'hebrew') {
        if (function_exists('normalizer_normalize')) {
            $text = normalizer_normalize($text, Normalizer::NFD);
        }
        // Strip Hebrew vowel points and cantillation (U+0591–U+05C7, U+FB1E)
        $text = preg_replace('/[\x{0591}-\x{05C7}\x{FB1E}]/u', '', $text);
        return trim($text);
    }

    // Greek: NFD → strip combining diacritics (preserve U+0345 iota subscript)
    //        → dedupe stray U+0345 → NFC → lowercase → explicit ι-subscript compose.
    if (function_exists('normalizer_normalize')) {
        $text = normalizer_normalize($text, Normalizer::NFD);
        $text = preg_replace('/[\x{0300}-\x{0344}\x{0346}-\x{036F}]/u', '', $text);
        $text = preg_replace('/\x{0345}{2,}/u', "\u{0345}", $text);
        $text = normalizer_normalize($text, Normalizer::NFC);
    }
    $text = mb_strtolower(trim($text));
    return str_replace(
        ["\u{03B1}\u{0345}", "\u{03B7}\u{0345}", "\u{03C9}\u{0345}"],
        ["\u{1FB3}",         "\u{1FC3}",         "\u{1FF3}"],
        $text
    );
}

// ------------------------------------------------------------------
// Gematria search: every word with the given standard gematria value.
// Returns:
//   [
//     'groups'    => [ <text_search-keyed group>, ... ],
//     'truncated' => bool,
//     'form_count'=> int,   // number of distinct word forms (groups)
//     'total_occ' => int,   // total verse occurrences across all groups
//   ]
// Each group:
//   [
//     'text_original'   => string,
//     'transliteration' => ?string,
//     'translation'     => ?string,
//     'strongs_primary' => ?string,
//     'language'        => 'Hebrew'|'Greek',
//     'verses'          => [
//         ['book_name' => ..., 'osis_code' => ..., 'chapter' => int, 'verse' => int],
//         ...
//     ],
//   ]
// ------------------------------------------------------------------
function bible_search_gematria(int $gem_value): array {
    if ($gem_value <= 0) {
        return ['groups' => [], 'truncated' => false, 'form_count' => 0, 'total_occ' => 0];
    }

    if (should_use_remote_api()) {
        $resp = remote_api_call('search_gematria', ['value' => $gem_value]);
        if (!is_array($resp)) {
            return ['groups' => [], 'truncated' => false, 'form_count' => 0, 'total_occ' => 0];
        }
        return [
            'groups'     => $resp['groups']     ?? [],
            'truncated'  => !empty($resp['truncated']),
            'form_count' => (int)($resp['form_count'] ?? count($resp['groups'] ?? [])),
            'total_occ'  => (int)($resp['total_occ']  ?? 0),
        ];
    }

    $pdo = bible_pdo();

    // Pre-fetch book id → name/osis_code lookup
    $books = [];
    foreach ($pdo->query('SELECT id, name, osis_code FROM book ORDER BY book_order') as $b) {
        $books[(int)$b['id']] = $b;
    }

    $stmt = $pdo->prepare('CALL GetGematriaWords(?)');
    $stmt->execute([$gem_value]);
    $gem_rows = $stmt->fetchAll();
    $stmt->closeCursor();

    $groups        = [];
    $gem_occ_count = 0;
    $truncated     = false;
    foreach ($gem_rows as $row) {
        if ($truncated) break;
        // Strip Unicode punctuation so λόγῳ, / λόγω. / λόγῳ all bucket together.
        $ts = preg_replace('/\p{P}+/u', '', $row['text_search']);
        if (!isset($groups[$ts])) {
            $groups[$ts] = [
                'text_original'   => $row['text_original'],
                'transliteration' => $row['transliteration'],
                'translation'     => $row['translation'],
                'strongs_primary' => $row['strongs_primary'],
                'language'        => $row['language'],
                'seen'            => [],
                'verses'          => [],
            ];
        }
        $book = $books[(int)$row['book_id']] ?? null;
        if (!$book) continue;
        $vkey = $row['book_id'] . ':' . $row['chapter'] . ':' . $row['verse'];
        if (isset($groups[$ts]['seen'][$vkey])) continue;
        $groups[$ts]['seen'][$vkey] = true;
        $groups[$ts]['verses'][] = [
            'book_name' => $book['name'],
            'osis_code' => $book['osis_code'],
            'chapter'   => (int)$row['chapter'],
            'verse'     => (int)$row['verse'],
        ];
        $gem_occ_count++;
        if ($gem_occ_count >= SEARCH_GEMATRIA_OCC_LIMIT) $truncated = true;
    }
    foreach ($groups as &$g) unset($g['seen']);
    unset($g);

    // Use array_values so JSON-encoded output is an ordered list, not a map.
    $groups_list = array_values($groups);

    return [
        'groups'     => $groups_list,
        'truncated'  => $truncated,
        'form_count' => count($groups_list),
        'total_occ'  => array_sum(array_map(fn($g) => count($g['verses']), $groups_list)),
    ];
}

// ------------------------------------------------------------------
// Verse search: Strong's / text / phrase modes.
// Returns:
//   [
//     'rows'       => [ ['book_name','osis_code','testament','book_order',
//                        'chapter','verse'], ... ],   // sorted, truncated to 6000
//     'truncated'  => bool,
//     'not_found'  => bool,   // a supplied Strong's code wasn't in `strongs`
//     'norms'      => [ string, ... ],  // display terms for the results header
//   ]
// Inputs:
//   $mode  = 'strongs' | 'text' | 'phrase'
//   $q_raw = the raw query string (e.g. "H430, G3056" or "logos" or
//            "weeping and wailing")
//   $lang  = 'Hebrew' | 'Greek' | 'English' (lower/upper case both accepted)
// ------------------------------------------------------------------
function bible_search_verses(string $mode, string $q_raw, string $lang = ''): array {
    $mode  = strtolower(trim($mode));
    $q_raw = trim($q_raw);

    if ($q_raw === '') {
        return ['rows' => [], 'truncated' => false, 'not_found' => false, 'norms' => []];
    }

    if (should_use_remote_api()) {
        $resp = remote_api_call('search_verses', [
            'mode' => $mode,
            'q'    => $q_raw,
            'lang' => $lang,
        ]);
        if (!is_array($resp)) {
            return ['rows' => [], 'truncated' => false, 'not_found' => false, 'norms' => []];
        }
        return [
            'rows'      => $resp['rows']      ?? [],
            'truncated' => !empty($resp['truncated']),
            'not_found' => !empty($resp['not_found']),
            'norms'     => $resp['norms']     ?? [],
        ];
    }

    // Split on commas, drop empties, re-index.
    $terms = array_values(array_filter(array_map('trim', explode(',', $q_raw))));
    if (empty($terms)) {
        return ['rows' => [], 'truncated' => false, 'not_found' => false, 'norms' => []];
    }

    $pdo        = bible_pdo();
    $norms      = [];
    $params     = [];
    $where_sql  = '';
    $not_found  = false;

    if ($mode === 'phrase' && strtolower($lang) === 'english') {
        // English KJV phrase search — bible_kjv.Verse_Text_Clean LIKE.
        // Strip sentence punctuation from both sides; lowercase via LOWER().
        $needle  = trim(preg_replace('/\s+/u', ' ', $q_raw));
        $needle  = preg_replace('/[,;:.!?]/u', '', $needle);
        $needle  = mb_strtolower(trim(preg_replace('/\s+/u', ' ', $needle)));
        $norms[] = $q_raw;
        $where_sql = "EXISTS (
                        SELECT 1
                          FROM bible_kjv k
                         WHERE k.Book    = b.id
                           AND k.Chapter = v.chapter
                           AND k.Verse   = v.verse
                           AND LOWER(REGEXP_REPLACE(k.Verse_Text_Clean, '[,;:.!?]', '')) LIKE ?)";
        $params[] = '%' . search_escape_like($needle) . '%';
    } elseif ($mode === 'phrase') {
        // Hebrew/Greek whole-phrase search against verse.text_search.
        $norm = search_normalize_query($q_raw, $lang);
        // Strip iota-subscript forms (utf8mb4_unicode_ci treats U+0345 as
        // zero-weight; verse.text_search is stored with the same stripping).
        if (strtolower($lang) !== 'hebrew') {
            $norm = str_replace(
                ["\u{1FB3}", "\u{1FC3}", "\u{1FF3}", "\u{0345}"],
                ["\u{03B1}", "\u{03B7}", "\u{03C9}", ''],
                $norm
            );
        }
        $norms[]   = $norm ?: $q_raw;
        $where_sql = "v.text_search LIKE ?";
        $params[]  = '%' . search_escape_like($norm) . '%';
    } else {
        $exists_clauses = [];
        if ($mode === 'strongs') {
            // Strong's: comma-separated codes, AND logic across the verse.
            foreach ($terms as $term) {
                $search_term = $term;
                if (preg_match('/^([HG])(\d{1,5})([A-Za-z]?)$/', $term, $sm)) {
                    $search_term = $sm[1] . str_pad($sm[2], 4, '0', STR_PAD_LEFT) . $sm[3];
                }
                $lookup_key = $term;
                if (preg_match('/^([HG])0*(\d+)([A-Za-z]?)$/', $term, $sm)) {
                    $lookup_key = $sm[1] . $sm[2] . $sm[3];
                }
                if (bible_strongs_lookup($lookup_key) === null) {
                    $norms     = [$term];
                    $not_found = true;
                    break;
                }
                $exists_clauses[] =
                    "EXISTS (SELECT 1 FROM word w\n"
                  . "         WHERE w.verse_id = v.id AND w.strongs LIKE ?)";
                $params[] = '%' . search_escape_like($search_term) . '%';
                $norms[]  = $term;
            }
        } else {
            // 'text' mode — split on commas and whitespace, AND each term.
            $text_terms = array_values(array_filter(
                array_map('trim', preg_split('/[\s,]+/u', $q_raw))
            ));
            if (strtolower($lang) === 'english') {
                foreach ($text_terms as $term) {
                    $needle = mb_strtolower(preg_replace('/[,;:.!?]/u', '', $term));
                    $exists_clauses[] =
                        "EXISTS (\n"
                      . "  SELECT 1 FROM bible_kjv k\n"
                      . "   WHERE k.Book = b.id AND k.Chapter = v.chapter AND k.Verse = v.verse\n"
                      . "     AND LOWER(REGEXP_REPLACE(k.Verse_Text_Clean, '[,;:.!?]', '')) LIKE ?)";
                    $params[] = '%' . search_escape_like($needle) . '%';
                    $norms[]  = $term;
                }
            } else {
                foreach ($text_terms as $term) {
                    $norm = search_normalize_query($term, $lang);
                    $exists_clauses[] =
                        "EXISTS (SELECT 1 FROM word w\n"
                      . "         WHERE w.verse_id = v.id AND w.text_search LIKE ?)";
                    $params[] = '%' . search_escape_like($norm) . '%';
                    $norms[]  = $norm ?: $term;
                }
            }
        }
        $where_sql = implode("\n  AND ", $exists_clauses);
    }

    $rows      = [];
    $truncated = false;
    if (!$not_found && $where_sql !== '') {
        try {
            $stmt = $pdo->prepare(
                "SELECT b.name AS book_name, b.osis_code, b.testament,
                        b.book_order, v.chapter, v.verse
                   FROM verse v
                   JOIN book b ON b.id = v.book_id
                  WHERE $where_sql
                  ORDER BY b.book_order, v.chapter, v.verse
                  LIMIT " . SEARCH_RESULT_LIMIT
            );
            $stmt->execute($params);
            $rows = $stmt->fetchAll();
            if (count($rows) === SEARCH_RESULT_LIMIT) {
                $truncated = true;
                array_pop($rows);
            }
        } catch (Throwable $e) {
            error_log('Bible search error: ' . $e->getMessage());
            // Surface the error message inside not_found-style envelope so the
            // caller can decide what to render. Keeping the old behaviour
            // (string $error) would have broken JSON shape.
            return [
                'rows'      => [],
                'truncated' => false,
                'not_found' => false,
                'norms'     => $norms,
                'error'     => $e->getMessage(),
            ];
        }
    }

    return [
        'rows'      => $rows,
        'truncated' => $truncated,
        'not_found' => $not_found,
        'norms'     => $norms,
    ];
}
