<?php
// Bible Browser — main page (biblehub-style interlinear).

require __DIR__ . '/db.php';
require __DIR__ . '/book_aliases.php';
require __DIR__ . '/helpers.php';
require __DIR__ . '/render_context.php';

// ---------- Visitor counter (verse_views table) ----------
function is_bot(): bool {
    $ua = strtolower($_SERVER['HTTP_USER_AGENT'] ?? '');
    if ($ua === '') return true;
    $patterns = ['bot','crawler','spider','slurp','mediapartners','python','curl','wget',
                 'libwww','scrapy','httpclient','go-http','java/','ruby','perl','php/',
                 'scan','zgrab','semrush','ahrefsbot','dotbot','mj12bot','petalbot',
                 'yandex','baiduspider','duckduck','facebookexternalhit','twitterbot',
                 'linkedinbot','whatsapp','applebot','ia_archiver'];
    foreach ($patterns as $p) {
        if (str_contains($ua, $p)) return true;
    }
    return false;
}

function record_verse_view(string $book, int $chapter, int $verse): array {
    if (is_bot()) return ['verse' => 0, 'total' => 0];

    // In remote API mode we don't track visits against the remote server
    if (should_use_remote_api()) {
        return ['verse' => 0, 'total' => 0];
    }

    try {
        $pdo = bible_pdo();
        $pdo->prepare("CALL record_verse_view(?, ?, ?, @verse_count, @total)")
            ->execute([$book, $chapter, $verse]);
        $row = $pdo->query("SELECT @verse_count AS verse_count, @total AS total")->fetch();
        return [
            'verse' => (int)($row['verse_count'] ?? 0),
            'total' => (int)($row['total']        ?? 0),
        ];
    } catch (Throwable $e) {
        error_log('verse_views error: ' . $e->getMessage());
        if (!empty($_GET['debug'])) echo '<pre style="color:red">verse_views: ' . htmlspecialchars($e->getMessage()) . '</pre>';
        return ['verse' => 0, 'total' => 0];
    }
}

// ---------- AJAX endpoints for dropdown chaining ----------
if (isset($_GET['api'])) { require __DIR__ . '/api.php'; }

// ---------- normal page render ----------
// Resolve book / chapter / verse from URL (reference text overrides).
$book_code = null; $chapter = null; $verse = null;
if (!empty($_GET['ref'])) {
    $r = parse_reference($_GET['ref']);
    if ($r) { $book_code = $r['osis_code']; $chapter = $r['chapter']; $verse = $r['verse']; }
}
if (!$book_code) {
    $book_code = $_GET['book']        ?? 'Gen';
    $chapter   = (int)($_GET['chapter'] ?? 1);
    $verse     = (int)($_GET['verse']   ?? 1);
}
$subverse = (string)($_GET['subverse'] ?? '');

// Record visit and fetch counts (silently fails if DB unavailable)
$view_counts = record_verse_view($book_code, (int)$chapter, (int)$verse);

// Edition dropdown. OT Hebrew books get BHS + LXX-Rahlfs; NT + LXX books
// get NA28 + TR + LXX-Rahlfs. LXX-Rahlfs is a mode switch that routes
// lookups to the book_lxx / verse_lxx / word_lxx tables.
const OT_BOOK_CODES = [
    'Gen','Exo','Lev','Num','Deu','Jos','Jdg','Rut',
    '1Sa','2Sa','1Ki','2Ki','1Ch','2Ch','Ezr','Neh','Est',
    'Job','Psa','Pro','Ecc','Sng','Isa','Jer','Lam','Ezk',
    'Dan','Hos','Jol','Amo','Oba','Jon','Mic','Nam','Hab',
    'Zep','Hag','Zec','Mal',
];

$current_is_lxx_book = (strpos($book_code, 'Lxx') === 0);
$is_ot_book  = !$current_is_lxx_book && in_array($book_code, OT_BOOK_CODES, true);
$is_lxx_ot   = $current_is_lxx_book && in_array(substr($book_code, 3), OT_BOOK_CODES, true);

if ($is_ot_book || $is_lxx_ot) {
    $editions        = [
        ['code' => 'BHS',        'name' => 'Biblia Hebraica Stuttgartensia'],
        ['code' => 'LXX-Rahlfs', 'name' => 'Rahlfs LXX 1935'],
    ];
    $default_edition = $is_lxx_ot ? 'LXX-Rahlfs' : 'BHS';
} else {
    $editions        = bible_greek_editions(); // NA28, TR, LXX-Rahlfs
    $default_edition = $current_is_lxx_book ? 'LXX-Rahlfs' : 'NA28';
}
$valid_codes  = array_column($editions, 'code');
$edition_code = $_GET['edition'] ?? $default_edition;
if (!in_array($edition_code, $valid_codes, true)) $edition_code = $default_edition;

$lxx_mode = ($edition_code === 'LXX-Rahlfs');

// Auto-jump when book + edition disagree. The user flipped the Edition
// dropdown but the book is from the other tradition — keep the chapter
// and verse, swap the book to the parallel.
if ($lxx_mode && !$current_is_lxx_book) {
    $par = lxx_book_by_mt_osis($book_code);
    if ($par) {
        $book_code = $par['osis_code'];
    } else {
        // No LXX parallel (NT book or unknown) — land on LXX Genesis.
        $book_code = 'LxxGen';
        $chapter = 1; $verse = 1;
    }
    $current_is_lxx_book = true;
} elseif (!$lxx_mode && $current_is_lxx_book) {
    // Switching from LXX to BHS → land on the OT MT parallel (or Gen 1:1).
    // Switching from LXX to NA28/TR → land on Matthew 1:1 (NT edition, OT not available).
    if ($edition_code === 'BHS') {
        $lxx_row = lxx_book_by_osis($book_code);
        if ($lxx_row && !empty($lxx_row['mt_parallel_osis'])) {
            $book_code = $lxx_row['mt_parallel_osis'];
        } else {
            $book_code = 'Gen';
            $chapter = 1; $verse = 1;
        }
    } else {
        $book_code = 'Mat';
        $chapter = 1; $verse = 1;
    }
    $current_is_lxx_book = false;
}

// After any auto-jump the $book_code may have changed (e.g. LxxGen → Gen or
// Gen → LxxGen). Recompute the edition list so the dropdown reflects the
// ACTUAL book being displayed, not the one that was in the URL.
$current_is_lxx_book = (strpos($book_code, 'Lxx') === 0);
$is_ot_book          = !$current_is_lxx_book && in_array($book_code, OT_BOOK_CODES, true);
$is_lxx_ot           = $current_is_lxx_book && in_array(substr($book_code, 3), OT_BOOK_CODES, true);
if ($is_ot_book || $is_lxx_ot) {
    $editions = [
        ['code' => 'BHS',        'name' => 'Biblia Hebraica Stuttgartensia'],
        ['code' => 'LXX-Rahlfs', 'name' => 'Rahlfs LXX 1935'],
    ];
} elseif ($current_is_lxx_book) {
    $editions = bible_greek_editions(); // NT LXX books: NA28, TR, LXX-Rahlfs
}
// (else: NT book — $editions is already correct from the block above)
$valid_codes  = array_column($editions, 'code');
if (!in_array($edition_code, $valid_codes, true)) {
    $edition_code = $is_ot_book ? 'BHS' : ($current_is_lxx_book ? 'LXX-Rahlfs' : 'NA28');
}
$lxx_mode = ($edition_code === 'LXX-Rahlfs');

// Books list, chapters, verses come from the right tables for this mode.
$books    = $lxx_mode ? lxx_books() : bible_books();
$chapters = $lxx_mode ? lxx_chapters($book_code) : bible_chapters($book_code);

if ($lxx_mode) {
    // lxx_verses returns rows with subverse — collapse to unique verse
    // numbers for the dropdown. Subverse stepping is reachable via
    // prev/next once you're on a subverse-bearing verse.
    $verse_rows = $chapters ? lxx_verses($book_code, $chapter ?: $chapters[0]) : [];
    $verses = [];
    foreach ($verse_rows as $vr) {
        $vn = (int)$vr['verse'];
        if (!in_array($vn, $verses, true)) $verses[] = $vn;
    }
} else {
    $verses = $chapters ? bible_verses($book_code, $chapter ?: $chapters[0]) : [];
}

// How many consecutive verses to display, starting at $verse.
$max_count = max(1, count($verses));
$count     = max(1, min($max_count, (int)($_GET['count'] ?? 1)));

// Track the current book's MT language for the (now-edge-case) Hebrew
// disable rule. With LXX in the dropdown we generally leave Edition
// enabled, so the Hebrew user can flip to LXX. NT books still see only
// NA28/TR meaningfully — but the dropdown stays clickable.
$current_book_lang = 'Greek';
if (!$lxx_mode) {
    foreach ($books as $b_chk) {
        if ($b_chk['osis_code'] === $book_code) {
            $current_book_lang = $b_chk['language'];
            break;
        }
    }
}
// Fetch each verse in the range. Stop at chapter end.
$verses_data = [];
for ($i = 0; $i < $count; $i++) {
    $vd = $lxx_mode
        ? lxx_verse_full($book_code, $chapter, $verse + $i, $i === 0 ? $subverse : '')
        : bible_verse_full($book_code, $chapter, $verse + $i, $edition_code);
    if (!$vd) break;
    $verses_data[] = $vd;
}
$actual_count   = count($verses_data);
$last_verse_num = $actual_count > 0 ? ($verse + $actual_count - 1) : $verse;

$prev = $lxx_mode
    ? lxx_neighbor($book_code, $chapter, $verse,          $subverse, 'prev')
    : bible_neighbor($book_code, $chapter, $verse,        'prev');
$next = $lxx_mode
    ? lxx_neighbor($book_code, $chapter, $last_verse_num, $subverse, 'next')
    : bible_neighbor($book_code, $chapter, $last_verse_num, 'next');

?>
<?php bible_render_layout_header(); ?>

<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#f7f8f5">
<meta name="author" content="Richard Amiel McGough">
<title>Bible Browser — <?= h($book_code) ?> <?= (int)$chapter ?>:<?= (int)$verse ?><?= $actual_count > 1 ? '-' . (int)$last_verse_num : '' ?></title>
<?php bible_render_layout_styles(); ?>
</head>
<body class="bible-mobile-ready">

<?php bible_render_layout_banner(); ?>
<div class="bible-layout">
<main class="bible-main">
<div class="selector">
<?php
ob_start(); ?>
    <label class="sel-label sel-count-label">Range</label>
    <select name="count" id="sel-count" data-max="<?= (int)$max_count ?>" title="Additional verses to display after the selected verse">
    <?php for ($cn = 1; $cn <= $max_count; $cn++): ?>
        <option value="<?= $cn ?>" <?= $cn === (int)$count ? 'selected' : '' ?>><?= $cn === 1 ? 'None' : (($cn - 1) === 1 ? '1 vs' : ($cn - 1) . ' vss') ?></option>
    <?php endfor; ?>
    </select>
    <label class="sel-label">Source</label>
    <select name="edition" id="sel-edition" title="Edition">
    <?php foreach ($editions as $ed): ?>
        <option value="<?= h($ed['code']) ?>" <?= $ed['code'] === $edition_code ? 'selected' : '' ?> title="<?= h($ed['name']) ?>"><?= h($ed['code'] === 'LXX-Rahlfs' ? 'LXX' : $ed['code']) ?></option>
    <?php endforeach; ?>
    </select>
<?php $selector_extra_fields = ob_get_clean();
require __DIR__ . '/verse_selector.inc.php'; ?>
    <button type="button" id="gear-btn" class="gear" aria-expanded="false" aria-controls="options-panel" title="Display options" aria-label="Display options">
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
            <path fill="currentColor" d="M19.14 12.94a7.49 7.49 0 0 0 0-1.88l2.03-1.58a.5.5 0 0 0 .12-.64l-1.92-3.32a.5.5 0 0 0-.61-.22l-2.39.96a7.4 7.4 0 0 0-1.62-.94l-.36-2.54a.5.5 0 0 0-.5-.42h-3.84a.5.5 0 0 0-.5.42l-.36 2.54c-.59.24-1.13.56-1.62.94l-2.39-.96a.5.5 0 0 0-.61.22L2.71 8.84a.5.5 0 0 0 .12.64L4.86 11.06a7.5 7.5 0 0 0 0 1.88l-2.03 1.58a.5.5 0 0 0-.12.64l1.92 3.32c.14.24.43.34.68.24l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.26.42.5.42h3.84c.24 0 .45-.18.5-.42l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.25.1.54 0 .68-.24l1.92-3.32a.5.5 0 0 0-.12-.64l-2.03-1.58zM12 15.5A3.5 3.5 0 1 1 12 8.5a3.5 3.5 0 0 1 0 7z"/>
        </svg>
    </button>
</div>

<div id="options-panel" class="options-panel" hidden>
    <div class="options-title">Display</div>
    <div class="options-group">
        <span class="options-grouplabel">Gematria</span>
        <label><input type="checkbox" data-opt="gem-std" checked> Standard</label>
        <label><input type="checkbox" data-opt="gem-ord" checked> Ordinal</label>
        <label><input type="checkbox" data-opt="gem-red" checked> Reduced</label>
    </div>
    <div class="options-divider"></div>
    <label><input type="checkbox" data-opt="translit" checked> Transliteration</label>
    <label><input type="checkbox" data-opt="english"  checked> English</label>
    <label><input type="checkbox" data-opt="strongs"  checked> Strong's</label>
    <label><input type="checkbox" data-opt="grammar"  checked> Grammar</label>
    <label><input type="checkbox" data-opt="full-width"> Full width</label>
    <div class="options-divider"></div>
    <div class="options-group">
        <span class="options-grouplabel">Verse text</span>
        <label><input type="checkbox" data-opt="verse-original" checked> Original</label>
        <label><input type="checkbox" data-opt="verse-english" checked> English</label>
        <label><input type="checkbox" data-opt="verse-newlines"> Newlines</label>
    </div>
    <div class="options-size-section">
        <span class="options-grouplabel">Font sizes</span>
        <label class="size-ctrl">Verse orig (Heb) <input type="number" data-size="verse-orig-heb" value="22" min="8" max="72" step="1"> px</label>
        <label class="size-ctrl">Verse orig (Grk) <input type="number" data-size="verse-orig-grk" value="18" min="8" max="72" step="1"> px</label>
        <label class="size-ctrl">Verse eng        <input type="number" data-size="verse-eng"       value="16" min="8" max="48" step="1"> px</label>
        <div class="options-divider"></div>
        <label class="size-ctrl">Orig (Heb) <input type="number" data-size="word-orig-heb" value="26" min="8" max="72" step="1"> px</label>
        <label class="size-ctrl">Orig (Grk) <input type="number" data-size="word-orig-grk" value="18" min="8" max="72" step="1"> px</label>
        <label class="size-ctrl">Translit  <input type="number" data-size="translit"  value="13" min="8" max="36" step="1"> px</label>
        <label class="size-ctrl">English   <input type="number" data-size="word-eng"   value="13" min="8" max="36" step="1"> px</label>
        <label class="size-ctrl">Strong's  <input type="number" data-size="strongs"    value="12" min="8" max="36" step="1"> px</label>
        <label class="size-ctrl">Grammar   <input type="number" data-size="grammar"    value="11" min="8" max="36" step="1"> px</label>
        <label class="size-ctrl">Gematria  <input type="number" data-size="gematria"   value="12" min="8" max="36" step="1"> px</label>
        <label class="size-ctrl">Gematria color  <input type="color" data-color="gematria" value="#1e40af"></label>
    </div>
    <div class="options-reset-row">
        <button type="button" id="opts-reset-btn" class="opts-reset-btn">Reset to defaults</button>
    </div>
</div>

<?php
// Detect "verse exists but no words in this edition" -- the verse row is
// fetched OK but the filter empties the words array.
$all_empty_in_edition = false;
if ($actual_count > 0) {
    $all_empty_in_edition = true;
    foreach ($verses_data as $vd_chk) {
        if (!empty($vd_chk['words'])) { $all_empty_in_edition = false; break; }
    }
}
?>
<?php if ($actual_count === 0): ?>
    <div class="verse-card empty">
        Verse <?= h($book_code) ?> <?= (int)$chapter ?>:<?= (int)$verse ?> not found.
    </div>
<?php elseif ($all_empty_in_edition): ?>
    <div class="verse-card empty">
        <?= h($book_code) ?> <?= (int)$chapter ?>:<?= (int)$verse ?><?= $count > 1 ? '-' . ($verse + $count - 1) : '' ?>
        is not present in edition <strong><?= h($edition_code) ?></strong>.
        <div style="margin-top:8px; font-size:0.9em">
            <?php
            $alt_qs = '?book=' . h($book_code) . '&amp;chapter=' . (int)$chapter . '&amp;verse=' . (int)$verse;
            if ($count > 1) $alt_qs .= '&amp;count=' . (int)$count;
            ?>
            Try <a href="<?= $alt_qs ?>&amp;edition=NA28">NA28</a>
            &nbsp;or&nbsp; <a href="<?= $alt_qs ?>&amp;edition=TR">TR</a>.
        </div>
    </div>
<?php else:
    // Build the render-context (per-word JS payload + range-level scalars).
    // See web/render_context.php for the full contract.
    extract(build_render_context(
        $verses_data, $chapter, $verse, $count,
        $edition_code, $actual_count, $last_verse_num
    ));

    $words_to_original_text = function (array $vd_list): string {
        $parts = [];
        foreach ($vd_list as $vd_cmp) {
            $lang_cmp = $vd_cmp['verse']['language'];
            foreach ($vd_cmp['words'] as $w_cmp) {
                if ($lang_cmp === 'Greek') {
                    [$orig_cmp] = split_greek_word($w_cmp['text_original'] ?? '');
                    $parts[] = $orig_cmp ?? '';
                } else {
                    $parts[] = clean_inline($w_cmp['text_original'] ?? '');
                }
            }
        }
        return trim(preg_replace('/\s+/u', ' ', implode(' ', array_filter($parts, fn($p) => trim((string)$p) !== ''))));
    };

    $comparison_rows = [];
    $current_original = $words_to_original_text($verses_data);
    if ($current_original !== '') {
        $comparison_rows[] = [
            'label' => $edition_code,
            'meta'  => $primary_lang . ' text',
            'class' => $primary_lcls,
            'html'  => h($current_original),
        ];
    }

    if (!$lxx_mode && $primary_lang === 'Greek') {
        foreach (bible_greek_editions() as $cmp_ed) {
            $cmp_code = $cmp_ed['code'];
            if ($cmp_code === 'LXX-Rahlfs' || $cmp_code === $edition_code) continue;
            $cmp_vds = [];
            for ($ci = 0; $ci < $actual_count; $ci++) {
                $cmp_vd = bible_verse_full($book_code, $chapter, $verse + $ci, $cmp_code);
                if ($cmp_vd) $cmp_vds[] = $cmp_vd;
            }
            $cmp_text = $words_to_original_text($cmp_vds);
            if ($cmp_text !== '') {
                $comparison_rows[] = [
                    'label' => $cmp_code,
                    'meta'  => 'Greek text',
                    'class' => 'grk',
                    'html'  => h($cmp_text),
                ];
            }
        }
    }

    if (!$lxx_mode && $primary_lang === 'Hebrew') {
        try {
            $par_lxx = lxx_book_by_mt_osis($book_code);
            if ($par_lxx) {
                $cmp_lxx_vds = [];
                for ($ci = 0; $ci < $actual_count; $ci++) {
                    $cmp_lxx_vd = lxx_verse_full($par_lxx['osis_code'], $chapter, $verse + $ci, '');
                    if ($cmp_lxx_vd) $cmp_lxx_vds[] = $cmp_lxx_vd;
                }
                $cmp_lxx_text = $words_to_original_text($cmp_lxx_vds);
                if ($cmp_lxx_text !== '') {
                    $comparison_rows[] = [
                        'label' => 'LXX',
                        'meta'  => 'Greek text',
                        'class' => 'grk',
                        'html'  => h($cmp_lxx_text),
                    ];
                }
            }
        } catch (Throwable $e) {
            // LXX tables are optional during local development.
        }
    }

    if ($lxx_mode) {
        $lxx_row = lxx_book_by_osis($book_code);
        if ($lxx_row && !empty($lxx_row['mt_parallel_osis'])) {
            $cmp_mt_vds = [];
            for ($ci = 0; $ci < $actual_count; $ci++) {
                $cmp_mt_vd = bible_verse_full($lxx_row['mt_parallel_osis'], $chapter, $verse + $ci, 'BHS');
                if ($cmp_mt_vd) $cmp_mt_vds[] = $cmp_mt_vd;
            }
            $cmp_mt_text = $words_to_original_text($cmp_mt_vds);
            if ($cmp_mt_text !== '') {
                $comparison_rows[] = [
                    'label' => 'BHS',
                    'meta'  => 'Hebrew text',
                    'class' => 'heb',
                    'html'  => h($cmp_mt_text),
                ];
            }
        }
    }

    $english_bits = [];
    foreach ($verses_data as $vd_cmp) {
        $v_cmp = $vd_cmp['verse'];
        $kjv_cmp = null;
        if (!$lxx_mode) {
            $kjv_raw_cmp = kjv_verse_text((int)$v_cmp['book_id'], (int)$v_cmp['chapter'], (int)$v_cmp['verse']);
            if ($kjv_raw_cmp !== null && $kjv_raw_cmp !== '') {
                $kjv_cmp = render_kjv_tagged($kjv_raw_cmp, (string)$v_cmp['testament']);
            }
        }
        if ($kjv_cmp !== null) {
            $english_bits[] = $kjv_cmp;
        } else {
            $english_bits[] = h(trim($v_cmp['language'] === 'Hebrew'
                ? clean_inline($v_cmp['text_english'] ?? '')
                : ($v_cmp['text_english'] ?? '')));
        }
    }
    $english_html = trim(implode(' ', array_filter($english_bits)));
    if ($english_html !== '') {
        $comparison_rows[] = [
            'label' => $lxx_mode ? 'English' : 'KJV',
            'meta'  => 'full verse translation',
            'class' => 'eng',
            'html'  => $english_html,
        ];
    }
?>
<div class="verse-card">
    <div class="ref-line">
        <h2>
            <span class="ref-full"><?= $range_title ?></span>
            <span class="ref-abbr"><?= h(preg_replace('/^Lxx/', '', $book_code)) ?>&nbsp;<?= (int)$chapter ?>:<?= (int)$verse ?><?= $actual_count > 1 ? '-'.(int)$last_verse_num : '' ?></span>
        </h2>
        <div class="meta" hidden>
            <?= $actual_count ?> verse<?= $actual_count > 1 ? 's' : '' ?> &nbsp;·&nbsp;
            <?= $total_words ?> words
            <?php if ($any_sig_variant): ?>&nbsp;·&nbsp;<span style="color:var(--variant)">significant variant</span><?php endif; ?>
        </div>
        <div class="nav">
            <div id="word-search-bar" class="word-search-bar">
                <input type="text" id="search-input" placeholder="Jhn 3:16, word, phrase, or H0430" size="28">
                <label id="search-phrase-label" class="search-phrase-label" hidden>
                    <input type="checkbox" id="search-phrase" checked> Phrase
                </label>
                <button type="button" id="search-clear" class="search-clear" title="Clear" aria-label="Clear search" hidden>&#10005;</button>
                <button type="button" id="search-btn" aria-label="Search"><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="currentColor" d="M21 19.59l-5.4-5.4a7 7 0 1 0-1.41 1.41L19.59 21 21 19.59zM11 16a5 5 0 1 1 0-10 5 5 0 0 1 0 10z"/></svg></button>
            </div>
            <?php if ($prev): ?>
                <a href="?book=<?= h($prev['osis_code']) ?>&amp;chapter=<?= (int)$prev['chapter'] ?>&amp;verse=<?= (int)$prev['verse'] ?><?= $count_qs ?>">&#8249;<span class="nav-label"> prev</span></a>
            <?php endif; ?>
            <?php if ($next): ?>
                <a href="?book=<?= h($next['osis_code']) ?>&amp;chapter=<?= (int)$next['chapter'] ?>&amp;verse=<?= (int)$next['verse'] ?><?= $count_qs ?>"><span class="nav-label">next </span>&#8250;</a>
            <?php endif; ?>
        </div>
    </div>

    <!-- Combined Original / English text for the whole range -->
    <div class="assembled">
        <div class="label verse-orig-label">Original</div>
        <div class="original <?= $primary_lcls ?>">
            <?php foreach ($verses_data as $vd):
                $v_a    = $vd['verse'];
                $lang_a = $v_a['language'];
                $text_a = $lang_a === 'Hebrew' ? clean_inline($v_a['text_original']) : strip_greek_parens($v_a['text_original']);
                $text_a = trim($text_a);
            ?><span class="assembled-verse"><?php if ($actual_count > 1): ?><sup class="vno"><?= (int)$v_a['verse'] === 0 ? 'title' : (int)$v_a['verse'] ?></sup> <?php endif; ?><?= h($text_a) ?></span> <?php endforeach; ?>
        </div>
        <div class="label verse-eng-label">English<?php if (!$lxx_mode): ?> <span class="english-source">(KJV)</span><?php endif; ?></div>
        <div class="english">
            <?php foreach ($verses_data as $vd):
                $v_e    = $vd['verse'];
                $lang_e = $v_e['language'];
                // Prefer the tagged KJV text for Hebrew OT / Greek NT verses
                // (mt_pa MT/NT books). LXX mode falls through to the
                // STEPBible-supplied text_english (KJV doesn't cover the
                // deuterocanonical / LXX-only material).
                $kjv_html = null;
                if (!$lxx_mode) {
                    $kjv_raw = kjv_verse_text((int)$v_e['book_id'], (int)$v_e['chapter'], (int)$v_e['verse']);
                    if ($kjv_raw !== null && $kjv_raw !== '') {
                        $kjv_html = render_kjv_tagged($kjv_raw, (string)$v_e['testament']);
                    }
                }
                if ($kjv_html === null) {
                    $text_e = $lang_e === 'Hebrew' ? clean_inline($v_e['text_english']) : $v_e['text_english'];
                    $text_e = trim($text_e);
                }
            ?><span class="assembled-verse"><?php if ($actual_count > 1): ?><sup class="vno"><?= (int)$v_e['verse'] === 0 ? 'title' : (int)$v_e['verse'] ?></sup> <?php endif; ?><?php if ($kjv_html !== null): ?><?= $kjv_html ?><?php else: ?><?= h($text_e) ?><?php endif; ?></span> <?php endforeach; ?>
        </div>
    </div>

    <div id="gematria-panel" class="gematria-panel" hidden>
        <div id="gem-rows" class="gem-rows"></div>
        <button id="gem-clear" class="gem-clear" title="Clear selection" style="display:none">× clear</button>
        <button id="gem-link-btn" class="gem-link-btn" title="Copy deep link to clipboard" style="display:none">&#128279; copy link</button>
    </div>

    <div class="study-panel" id="study-panel" data-ref="<?= h($range_ref_str) ?>" data-edition="<?= h($edition_code) ?>">
        <div class="study-tabs" role="tablist" aria-label="Study tools">
            <button type="button" class="active" data-study-tab="audit">Audit</button>
            <button type="button" data-study-tab="compare">Compare</button>
            <button type="button" data-study-tab="export">Export</button>
        </div>

        <section class="study-section active" data-study-panel="audit">
            <div class="analysis-head">
                <div>
                    <div class="analysis-kicker">Selection</div>
                    <h3 id="selection-scope">Whole verse</h3>
                </div>
                <div id="selection-chip" class="selection-chip">Live</div>
            </div>
            <div id="selection-summary" class="metric-grid"></div>
            <div class="selection-reading">
                <div>
                    <div class="analysis-label">Original</div>
                    <p id="selection-original" class="<?= $primary_lcls ?>"></p>
                </div>
                <div>
                    <div class="analysis-label">Meaning</div>
                    <p id="selection-meaning"></p>
                </div>
            </div>
            <div id="analysis-word-list" class="analysis-word-list"></div>
        </section>

        <section class="study-section" data-study-panel="compare" hidden>
            <div class="comparison-grid">
                <?php foreach ($comparison_rows as $cmp): ?>
                    <article class="comparison-card">
                        <div class="comparison-top">
                            <strong><?= h($cmp['label']) ?></strong>
                            <span><?= h($cmp['meta']) ?></span>
                        </div>
                        <div class="comparison-text <?= h($cmp['class']) ?>"><?= $cmp['html'] ?></div>
                    </article>
                <?php endforeach; ?>
            </div>
        </section>

        <section class="study-section" data-study-panel="export" hidden>
            <div class="export-grid">
                <button type="button" data-export="copy">Copy</button>
                <button type="button" data-export="txt">TXT</button>
                <button type="button" data-export="csv">CSV</button>
                <button type="button" data-export="json">JSON</button>
                <button type="button" data-export="pdf">PDF</button>
            </div>
            <div id="export-status" class="export-status" aria-live="polite"></div>
        </section>
    </div>

    <!-- Single continuous interlinear across the whole range -->
    <div class="interlinear <?= $primary_lcls ?>" id="interlinear" data-edition="<?= h($edition_code) ?>">
    <?php $word_pos = 0; foreach ($verses_data as $vd):
        $v      = $vd['verse'];
        $words  = $vd['words'];
        $lang   = $v['language'];
        $lcls   = lang_class($lang);
        $is_title = ((int)$v['verse'] === 0);
        $vorder = (!$lxx_mode && !$is_title)
                    ? kjv_verse_order((int)$v['book_id'], (int)$v['chapter'], (int)$v['verse'])
                    : null;
    ?>
        <div class="verse-block">
        <div class="verse-num"><?= $is_title ? '<span class="verse-num-title">title</span>' : (int)$v['verse'] ?><?php if ($vorder !== null): ?><span class="verse-order">#<?= $vorder ?></span><?php endif; ?></div>
        <?php foreach ($words as $w): $word_pos++;
            if ($lang === 'Greek') {
                [$orig_display, $translit] = split_greek_word($w['text_original']);
                $english_display = $w['translation'] ?? '';
                $grammar_display = $w['grammar'] ?? '';
            } else {
                $orig_display    = clean_inline($w['text_original']);
                $translit        = clean_inline($w['transliteration']);
                $english_display = clean_inline($w['translation']);
                $grammar_display = format_hebrew_grammar($w['grammar'], $w['morphemes']);
            }
            $sd_num            = strongs_display($w['strongs']);
            $sd_full           = strongs_full_code($w['strongs'], $lang);
            $has_variant_class = !empty($w['variants']) ? ' has-variant' : '';
            // If db.php substituted a variant onto this canonical word, find
            // its index in $w['variants'] so variant-switcher can start
            // cycling from the correct state. 'base' = canonical text shown.
            $active_variant = 'base';
            if (!empty($w['source_variant_id']) && !empty($w['variants'])) {
                foreach ($w['variants'] as $vi => $vt_chk) {
                    if ((int)($vt_chk['id'] ?? 0) === (int)$w['source_variant_id']) {
                        $active_variant = (string)$vi;
                        break;
                    }
                }
            }
        ?>
            <div class="word-cell<?= $has_variant_class ?>"
                 data-pos="<?= $word_pos ?>"
                 data-word-id="<?= (int)$w['id'] ?>"
                 data-verse-num="<?= (int)$v['verse'] ?>"
                 data-active-variant="<?= h($active_variant) ?>"
                 data-gem-std="<?= (int)$w['gem_std'] ?>"
                 data-gem-ord="<?= (int)$w['gem_ord'] ?>"
                 data-gem-red="<?= (int)$w['gem_red'] ?>"
                 data-letter-count="<?= (int)letter_count($w['text_original'] ?? '', $lang) ?>">
                <div class="gematria"></div>
                <div class="original <?= $lcls ?>"><?= h($orig_display ?? '') ?></div>
                <div class="translit"><?= h($translit ?? '') ?></div>
                <div class="english"><?= h($english_display) ?></div>
                <div class="strongs<?= $sd_full ? ' strongs-link' : '' ?>" data-strongs="<?= h($sd_full) ?>"><?= h($sd_num) ?></div>
                <div class="grammar" data-lang="<?= $lcls ?>"><?= h($grammar_display) ?></div>
                <?php if ((int)$w['chunk_num'] > 1): ?>
                    <div class="chunk-badge">chunk <?= (int)$w['chunk_num'] ?></div>
                <?php endif; ?>
                <?php if (!empty($w['variants'])): ?>
                    <button class="variant-btn" title="<?= count($w['variants']) ?> variant<?= count($w['variants']) > 1 ? 's' : '' ?> — click to switch" tabindex="-1"></button>
                <?php endif; ?>
            </div>
        <?php endforeach; ?>
        </div>
    <?php endforeach; ?>
    </div>

    <div class="word-detail" id="word-detail">
        <div class="wd-head">
            <h3 id="wd-title"></h3>
            <button class="wd-close" onclick="hideDetail()">close ×</button>
        </div>
        <div id="wd-body"></div>
    </div>

    <?php
    // Combined source-file summaries across the range, collapsed by default.
    $all_sums = [];
    foreach ($verses_data as $vd):
        if (!empty($vd['summaries'])) {
            $all_sums[(int)$vd['verse']['verse']] = $vd['summaries'];
        }
    endforeach;
    ?>
</div>

<script id="word-data" type="application/json"><?= json_encode($detail_payload, JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT) ?></script>
<script>
const VERSE_LANG = <?= json_encode($primary_lang) ?>;
const VERSE_REF  = <?= json_encode($range_ref_str) ?>;
</script>

<?php endif; ?>

<div class="view-counter" id="view-counter"
     data-book="<?= htmlspecialchars($book_code) ?>"
     data-chapter="<?= (int)$chapter ?>"
     data-verse="<?= (int)$verse ?>"
     <?= $view_counts['total'] > 0 ? '' : 'hidden' ?>>
    This verse viewed <?= number_format($view_counts['verse']) ?> time<?= $view_counts['verse'] === 1 ? '' : 's' ?> &nbsp;·&nbsp;
    <a href="stats.php"><?= number_format($view_counts['total']) ?> total Bible page view<?= $view_counts['total'] === 1 ? '' : 's' ?></a>
</div>
<script>
(function () {
    var el = document.getElementById('view-counter');
    if (!el) return;
    function fmtN(n) { return n.toLocaleString(); }
    function refresh() {
        // Relative URL — works whether the page is served at /bible/ or root.
        fetch(`api.php?api=viewcount`
            + '&book='    + encodeURIComponent(el.dataset.book)
            + '&chapter=' + el.dataset.chapter
            + '&verse='   + el.dataset.verse)
        .then(function(r){ return r.json(); })
        .then(function(d){
            if (!d.total) return;
            el.innerHTML =
                'This verse viewed ' + fmtN(d.verse) + ' time' + (d.verse===1?'':'s') +
                ' &nbsp;&middot;&nbsp; ' +
                '<a href="stats.php">' + fmtN(d.total) + ' total Bible page view' + (d.total===1?'':'s') + '</a>';
            el.removeAttribute('hidden');
        });
    }
    window.addEventListener('pageshow', function(e) { if (e.persisted) refresh(); });
})();
</script>
</main>

<script src="js/options.js"></script>
<script src="js/gematria.js"></script>
<script src="js/word-selection.js"></script>
<script src="js/variant-switcher.js"></script>
<script src="js/analysis.js"></script>
<script src="js/dropdowns.js"></script>
<script src="js/search-trigger.js"></script>
<script src="js/strongs-tooltip.js"></script>
<script src="js/grammar-tooltip.js"></script>
<script src="js/deep-link.js"></script>
<script>
(function () {
    var sel = document.getElementById('sel-book');
    if (!sel) return;
    var mq = window.matchMedia('(max-width: 768px)');
    function applyBookNames(e) {
        var abbr = e.matches;
        for (var i = 0; i < sel.options.length; i++) {
            var opt = sel.options[i];
            opt.textContent = abbr ? opt.dataset.abbr : opt.dataset.full;
        }
    }
    applyBookNames(mq);
    mq.addEventListener('change', applyBookNames);
})();
</script>
<?php require __DIR__ . '/bible_sidebar.php'; ?>
</div>
</body>
</html>
