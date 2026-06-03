<?php
// els_lib.php — Letter-stream helpers for the ELS grid page.
//
// Extracted from els.php so the same code can be reached two ways:
//   • Local mode: els.php calls these directly and renders the grid.
//   • Remote API mode: els.php receives a JSON payload from
//     api.php?api=els_fetch (which calls these on the remote server) and
//     renders it identically. The render side is therefore unchanged.

require_once __DIR__ . '/db.php';

// -----------------------------------------------------------------------
// Letter-only stripping per language. Pure string manipulation — no DB.
// Hebrew : keep consonants U+05D0–U+05EA only (niqqud/cantillation drop).
// Greek  : strip parens, NFD, replace U+0345 with ι, keep base Greek letters.
// English: strip <NNNN> Strong's tags, keep A-Z only, uppercase.
// -----------------------------------------------------------------------
function els_strip(string $text, string $lang): string {
    if ($lang === 'Hebrew') {
        preg_match_all('/[\x{05D0}-\x{05EA}]/u', $text, $m);
        return implode('', $m[0]);
    }

    if ($lang === 'Greek') {
        // Strip parenthesised transliteration added by the DB import:
        // "Ἐν (En)" → "Ἐν"
        $text = preg_replace('/\s*\([^)]+\)/u', '', $text);
        if (class_exists('Normalizer')) {
            // NFD so combining diacritics separate from base letters.
            // U+0345 (iota subscript) is a real letter — promote to ι first.
            $text = \Normalizer::normalize($text, \Normalizer::FORM_D);
            $text = preg_replace('/\x{0345}/u', "\u{03B9}", $text);
            preg_match_all('/[\x{0391}-\x{03A9}\x{03B1}-\x{03C9}]/u', $text, $m);
            return implode('', $m[0]);
        }
        // Fallback without intl: expand iota-subscript precomposed chars
        // back to base-vowel + ι.
        preg_match_all('/[\x{0391}-\x{03C9}\x{1F00}-\x{1FFF}]/u', $text, $m);
        $result = '';
        foreach ($m[0] as $ch) {
            $cp = mb_ord($ch);
            if ($cp >= 0x1F80 && $cp <= 0x1F8F) {
                $result .= ($cp <= 0x1F87 ? 'α' : 'Α') . 'ι';
            } elseif ($cp >= 0x1F90 && $cp <= 0x1F9F) {
                $result .= ($cp <= 0x1F97 ? 'η' : 'Η') . 'ι';
            } elseif ($cp >= 0x1FA0 && $cp <= 0x1FAF) {
                $result .= ($cp <= 0x1FA7 ? 'ω' : 'Ω') . 'ι';
            } elseif (in_array($cp, [0x1FB2, 0x1FB3, 0x1FB4, 0x1FB7], true)) {
                $result .= 'αι';
            } elseif ($cp === 0x1FBC) {
                $result .= 'Αι';
            } elseif (in_array($cp, [0x1FC2, 0x1FC3, 0x1FC4, 0x1FC7], true)) {
                $result .= 'ηι';
            } elseif ($cp === 0x1FCC) {
                $result .= 'Ηι';
            } elseif (in_array($cp, [0x1FF2, 0x1FF3, 0x1FF4, 0x1FF7], true)) {
                $result .= 'ωι';
            } elseif ($cp === 0x1FFC) {
                $result .= 'Ωι';
            } else {
                $result .= $ch;
            }
        }
        return $result;
    }

    // English (KJV): strip Strong's tags then keep only A-Z.
    $text = preg_replace('/<\d+>/', '', $text);
    $text = preg_replace('/[^A-Za-z]/', '', $text);
    return strtoupper($text);
}

// -----------------------------------------------------------------------
// Fetch at least $max_letters bare letters starting at (book, chapter, verse)
// and continuing across chapter/book breaks.
//
// Returns:
//   [
//     'letters'  => string  — stripped letter string, possibly truncated to max
//     'lang'     => 'Hebrew' | 'Greek' | 'English'
//     'is_rtl'   => bool
//     'from_ref' => ['book'=>osis_code, 'chapter'=>int, 'verse'=>int] | null
//     'to_ref'   => ['book'=>osis_code, 'chapter'=>int, 'verse'=>int] | null
//   ]
//
// In remote API mode, delegates to remote_api_call('els_fetch', ...).
// -----------------------------------------------------------------------
function els_fetch(string $book_code, int $chapter, int $verse,
                   string $edition_code, int $max_letters): array {

    if (should_use_remote_api()) {
        $resp = remote_api_call('els_fetch', [
            'book'     => $book_code,
            'chapter'  => $chapter,
            'verse'    => $verse,
            'edition'  => $edition_code,
            'letters'  => $max_letters,
        ]);
        if (!is_array($resp)) {
            return ['letters' => '', 'lang' => 'English', 'is_rtl' => false,
                    'from_ref' => null, 'to_ref' => null];
        }
        // Coerce types after JSON round-trip.
        return [
            'letters'  => (string)($resp['letters'] ?? ''),
            'lang'     => (string)($resp['lang']    ?? 'English'),
            'is_rtl'   => !empty($resp['is_rtl']),
            'from_ref' => $resp['from_ref'] ?? null,
            'to_ref'   => $resp['to_ref']   ?? null,
        ];
    }

    $pdo  = bible_pdo();
    $lang = match ($edition_code) {
        'BHS'         => 'Hebrew',
        'NA28', 'TR'  => 'Greek',
        'KJV'         => 'English',
        default       => 'English',
    };

    // ---- KJV: query verse-level text from bible_kjv via Verse_Order ----
    if ($edition_code === 'KJV') {
        // Resolve book_id once so we can check kjv_alt_ref() if the direct
        // lookup misses (cross-tradition versification, e.g. Rev 12:18).
        $bk = $pdo->prepare("SELECT id FROM book WHERE osis_code = ? LIMIT 1");
        $bk->execute([$book_code]);
        $start_book_id = (int)($bk->fetchColumn() ?: 0);

        $sv = $pdo->prepare(
            "SELECT Verse_Order FROM bible_kjv
              WHERE Book = ? AND Chapter = ? AND Verse = ? LIMIT 1"
        );
        $sv->execute([$start_book_id, $chapter, $verse]);
        $start_order = (int)$sv->fetchColumn();
        if (!$start_order && $start_book_id
            && ($alt = kjv_alt_ref($start_book_id, $chapter, $verse)) !== null) {
            $sv->execute([$start_book_id, $alt['chapter'], $alt['verse']]);
            $start_order = (int)$sv->fetchColumn();
        }
        if (!$start_order) $start_order = 1;

        // One KJV verse averages ~120 letters; fetch generously.
        $v_limit = max(100, (int)ceil($max_letters / 80) + 10);
        $sv2 = $pdo->prepare(
            "SELECT Verse_Text, Book, Chapter, Verse
               FROM bible_kjv
              WHERE Verse_Order >= ?
              ORDER BY Verse_Order
              LIMIT $v_limit"
        );
        $sv2->execute([$start_order]);
        $rows = $sv2->fetchAll();

        $letters  = '';
        $from_ref = $to_ref = null;
        foreach ($rows as $r) {
            $stripped = els_strip((string)$r['Verse_Text'], 'English');
            if ($stripped === '') continue;
            if ($from_ref === null) {
                $bk = $pdo->prepare("SELECT osis_code FROM book WHERE id = ? LIMIT 1");
                $bk->execute([(int)$r['Book']]);
                $from_ref = [
                    'book'    => (string)($bk->fetchColumn() ?: ''),
                    'chapter' => (int)$r['Chapter'],
                    'verse'   => (int)$r['Verse'],
                ];
            }
            $letters .= $stripped;
            if (mb_strlen($letters) >= $max_letters) break;
            $to_ref = [
                'book'    => $from_ref['book'],
                'chapter' => (int)$r['Chapter'],
                'verse'   => (int)$r['Verse'],
            ];
        }
        if ($to_ref === null) $to_ref = $from_ref;

        return [
            'letters'  => mb_substr($letters, 0, $max_letters),
            'lang'     => 'English',
            'is_rtl'   => false,
            'from_ref' => $from_ref,
            'to_ref'   => $to_ref,
        ];
    }

    // ---- BHS / NA28 / TR: query word.text_original ----
    $bo_stmt = $pdo->prepare("SELECT book_order FROM book WHERE osis_code = ? LIMIT 1");
    $bo_stmt->execute([$book_code]);
    $start_bo = (int)($bo_stmt->fetchColumn() ?: 0);

    // Hebrew words average ~5 letters, Greek ~5, so letters/3 + buffer is safe.
    $w_limit = max(300, (int)ceil($max_letters / 3) + 50);

    if ($edition_code === 'BHS') {
        $sql =
            "SELECT w.text_original, b.osis_code, v.chapter, v.verse
               FROM word w
               JOIN verse v ON v.id = w.verse_id
               JOIN book b  ON b.id = v.book_id
              WHERE b.language = 'Hebrew'
                AND (   b.book_order > :sbo
                     OR (b.book_order = :sbo2 AND v.chapter > :sc)
                     OR (b.book_order = :sbo3 AND v.chapter = :sc2 AND v.verse >= :sv))
              ORDER BY b.book_order, v.chapter, v.verse, w.position
              LIMIT $w_limit";
        $stmt = $pdo->prepare($sql);
        $stmt->execute([
            ':sbo'  => $start_bo, ':sbo2' => $start_bo, ':sc'  => $chapter,
            ':sbo3' => $start_bo, ':sc2'  => $chapter,  ':sv'  => $verse,
        ]);
    } else {
        $edition_id = bible_edition_id($edition_code);
        if ($edition_id === null) {
            return ['letters' => '', 'lang' => 'Greek', 'is_rtl' => false,
                    'from_ref' => null, 'to_ref' => null];
        }
        $sql =
            "SELECT w.text_original, b.osis_code, v.chapter, v.verse
               FROM word w
               JOIN verse v         ON v.id = w.verse_id
               JOIN book b          ON b.id = v.book_id
               JOIN word_edition we ON we.word_id = w.id AND we.edition_id = :eid
              WHERE (   b.book_order > :sbo
                     OR (b.book_order = :sbo2 AND v.chapter > :sc)
                     OR (b.book_order = :sbo3 AND v.chapter = :sc2 AND v.verse >= :sv))
              ORDER BY b.book_order, v.chapter, v.verse, w.position
              LIMIT $w_limit";
        $stmt = $pdo->prepare($sql);
        $stmt->execute([
            ':eid'  => $edition_id,
            ':sbo'  => $start_bo, ':sbo2' => $start_bo, ':sc'  => $chapter,
            ':sbo3' => $start_bo, ':sc2'  => $chapter,  ':sv'  => $verse,
        ]);
    }

    $rows     = $stmt->fetchAll();
    $letters  = '';
    $from_ref = $to_ref = null;

    foreach ($rows as $r) {
        $stripped = els_strip((string)$r['text_original'], $lang);
        if ($stripped === '') continue;
        if ($from_ref === null) {
            $from_ref = [
                'book'    => (string)$r['osis_code'],
                'chapter' => (int)$r['chapter'],
                'verse'   => (int)$r['verse'],
            ];
        }
        $letters .= $stripped;
        $to_ref = [
            'book'    => (string)$r['osis_code'],
            'chapter' => (int)$r['chapter'],
            'verse'   => (int)$r['verse'],
        ];
        if (mb_strlen($letters) >= $max_letters) break;
    }

    return [
        'letters'  => mb_substr($letters, 0, $max_letters),
        'lang'     => $lang,
        'is_rtl'   => ($lang === 'Hebrew'),
        'from_ref' => $from_ref,
        'to_ref'   => $to_ref,
    ];
}
