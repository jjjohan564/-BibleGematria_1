<?php
// Parse a free-form reference like "Jhn 3:16", "John 3 16", "1Co 13:13",
// "1 Cor 13.13" into (osis_code, chapter, verse). Returns null on miss.
//
// All book aliases live in BOOK_ALIASES below -- one hand-curated table
// keyed by lowercased no-whitespace input forms. To add a new alias for
// a book, drop it into that book's line. Keys must be lowercase already.
function parse_reference(string $input): ?array {
    $input = trim($input);
    if ($input === '') return null;
    // Full reference: [optional 1/2/3] [letters] chapter [:|.|space] verse
    if (preg_match('/^([1-3]?\s*[A-Za-z]+)\s*(\d+)\s*[:.\s]\s*(\d+)$/u', $input, $m)) {
        $book_in = preg_replace('/\s+/', '', strtolower($m[1]));
        $osis    = BOOK_ALIASES[$book_in] ?? null;
        if ($osis === null) return null;
        return ['osis_code' => $osis, 'chapter' => (int)$m[2], 'verse' => (int)$m[3]];
    }
    // Chapter-only: "Book Chapter" with no verse → default to verse 1
    if (preg_match('/^([1-3]?\s*[A-Za-z]+)\s+(\d+)$/u', $input, $m)) {
        $book_in = preg_replace('/\s+/', '', strtolower($m[1]));
        $osis    = BOOK_ALIASES[$book_in] ?? null;
        if ($osis === null) return null;
        return ['osis_code' => $osis, 'chapter' => (int)$m[2], 'verse' => 1];
    }
    return null;
}

// ----- BOOK_ALIASES: every accepted input form -> OSIS code --------------
// One line per book, OT then NT in canonical order. Every key MUST be
// lowercase with no whitespace -- parse_reference() normalizes input that
// way before lookup. The OSIS code itself is always included as an alias.
const BOOK_ALIASES = [
    // ---- Old Testament ----
    'gen'=>'Gen', 'genesis'=>'Gen',
    'exo'=>'Exo', 'exod'=>'Exo', 'exodus'=>'Exo',
    'lev'=>'Lev', 'leviticus'=>'Lev',
    'num'=>'Num', 'numbers'=>'Num',
    'deu'=>'Deu', 'deut'=>'Deu', 'deuteronomy'=>'Deu',
    'jos'=>'Jos', 'josh'=>'Jos', 'joshua'=>'Jos',
    'jdg'=>'Jdg', 'judg'=>'Jdg', 'judges'=>'Jdg',
    'rut'=>'Rut', 'ruth'=>'Rut',
    '1sa'=>'1Sa', '1sam'=>'1Sa', '1samuel'=>'1Sa',
    '2sa'=>'2Sa', '2sam'=>'2Sa', '2samuel'=>'2Sa',
    '1ki'=>'1Ki', '1kgs'=>'1Ki', '1kings'=>'1Ki',
    '2ki'=>'2Ki', '2kgs'=>'2Ki', '2kings'=>'2Ki',
    '1ch'=>'1Ch', '1chr'=>'1Ch', '1chron'=>'1Ch', '1chronicles'=>'1Ch',
    '2ch'=>'2Ch', '2chr'=>'2Ch', '2chron'=>'2Ch', '2chronicles'=>'2Ch',
    'ezr'=>'Ezr', 'ezra'=>'Ezr',
    'neh'=>'Neh', 'nehemiah'=>'Neh',
    'est'=>'Est', 'esth'=>'Est', 'esther'=>'Est',
    'job'=>'Job',
    'psa'=>'Psa', 'ps'=>'Psa', 'psalm'=>'Psa', 'psalms'=>'Psa',
    'pro'=>'Pro', 'prov'=>'Pro', 'proverbs'=>'Pro',
    'ecc'=>'Ecc', 'eccl'=>'Ecc', 'ecclesiastes'=>'Ecc', 'qoh'=>'Ecc',
    'sng'=>'Sng', 'song'=>'Sng', 'songofsolomon'=>'Sng', 'songofsongs'=>'Sng', 'ss'=>'Sng', 'canticles'=>'Sng',
    'isa'=>'Isa', 'isaiah'=>'Isa',
    'jer'=>'Jer', 'jeremiah'=>'Jer',
    'lam'=>'Lam', 'lamentations'=>'Lam',
    'ezk'=>'Ezk', 'ezek'=>'Ezk', 'ezekiel'=>'Ezk',
    'dan'=>'Dan', 'daniel'=>'Dan',
    'hos'=>'Hos', 'hosea'=>'Hos',
    'jol'=>'Jol', 'joel'=>'Jol',
    'amo'=>'Amo', 'amos'=>'Amo',
    'oba'=>'Oba', 'obad'=>'Oba', 'obadiah'=>'Oba',
    'jon'=>'Jon', 'jonah'=>'Jon',
    'mic'=>'Mic', 'micah'=>'Mic',
    'nam'=>'Nam', 'nah'=>'Nam', 'nahum'=>'Nam',
    'hab'=>'Hab', 'habakkuk'=>'Hab',
    'zep'=>'Zep', 'zeph'=>'Zep', 'zephaniah'=>'Zep',
    'hag'=>'Hag', 'haggai'=>'Hag',
    'zec'=>'Zec', 'zech'=>'Zec', 'zechariah'=>'Zec',
    'mal'=>'Mal', 'malachi'=>'Mal',
    // ---- New Testament ----
    'mat'=>'Mat', 'matt'=>'Mat', 'mt'=>'Mat', 'matthew'=>'Mat',
    'mrk'=>'Mrk', 'mar'=>'Mrk', 'mk'=>'Mrk', 'mark'=>'Mrk',
    'luk'=>'Luk', 'lk'=>'Luk', 'luke'=>'Luk',
    'jhn'=>'Jhn', 'jn'=>'Jhn', 'joh'=>'Jhn', 'john'=>'Jhn',
    'act'=>'Act', 'acts'=>'Act',
    'rom'=>'Rom', 'romans'=>'Rom',
    '1co'=>'1Co', '1cor'=>'1Co', '1corinthians'=>'1Co',
    '2co'=>'2Co', '2cor'=>'2Co', '2corinthians'=>'2Co',
    'gal'=>'Gal', 'galatians'=>'Gal',
    'eph'=>'Eph', 'ephesians'=>'Eph',
    'php'=>'Php', 'phil'=>'Php', 'philippians'=>'Php',
    'col'=>'Col', 'colossians'=>'Col',
    '1th'=>'1Th', '1thes'=>'1Th', '1thess'=>'1Th', '1thessalonians'=>'1Th',
    '2th'=>'2Th', '2thes'=>'2Th', '2thess'=>'2Th', '2thessalonians'=>'2Th',
    '1ti'=>'1Ti', '1tim'=>'1Ti', '1timothy'=>'1Ti',
    '2ti'=>'2Ti', '2tim'=>'2Ti', '2timothy'=>'2Ti',
    'tit'=>'Tit', 'titus'=>'Tit',
    'phm'=>'Phm', 'phlm'=>'Phm', 'philemon'=>'Phm',
    'heb'=>'Heb', 'hebrews'=>'Heb',
    'jas'=>'Jas', 'jam'=>'Jas', 'james'=>'Jas',
    '1pe'=>'1Pe', '1pet'=>'1Pe', '1peter'=>'1Pe',
    '2pe'=>'2Pe', '2pet'=>'2Pe', '2peter'=>'2Pe',
    '1jn'=>'1Jn', '1jo'=>'1Jn', '1john'=>'1Jn',
    '2jn'=>'2Jn', '2jo'=>'2Jn', '2john'=>'2Jn',
    '3jn'=>'3Jn', '3jo'=>'3Jn', '3john'=>'3Jn',
    'jud'=>'Jud', 'jude'=>'Jud',
    'rev'=>'Rev', 'revelation'=>'Rev', 'revelations'=>'Rev', 'apocalypse'=>'Rev',
];
