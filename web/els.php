<?php
// els.php — Equidistant Letter Sequence grid display.
//
// Fetches scripture text starting from the selected verse and continuing
// across chapter/book boundaries until the requested number of letters is
// reached. Strips every character that is not a plain letter (no vowel
// points, accents, spaces, or punctuation), then lays the letters out in
// an N-column grid with horizontal and vertical scroll bars.

require_once __DIR__ . '/db.php';
require_once __DIR__ . '/book_aliases.php';
require_once __DIR__ . '/helpers.php';
require_once __DIR__ . '/els_lib.php';

// Forward AJAX calls from the verse-selector dropdowns.
if (isset($_GET['api'])) { require __DIR__ . '/api.php'; }

// -----------------------------------------------------------------------
// Parameter resolution
// -----------------------------------------------------------------------

const ELS_OT_CODES = [
    'Gen','Exo','Lev','Num','Deu','Jos','Jdg','Rut',
    '1Sa','2Sa','1Ki','2Ki','1Ch','2Ch','Ezr','Neh','Est',
    'Job','Psa','Pro','Ecc','Sng','Isa','Jer','Lam','Ezk',
    'Dan','Hos','Jol','Amo','Oba','Jon','Mic','Nam','Hab',
    'Zep','Hag','Zec','Mal',
];

$book_code = $_GET['book']    ?? 'Gen';
$chapter   = max(1, (int)($_GET['chapter'] ?? 1));
$verse     = max(1, (int)($_GET['verse']   ?? 1));
$width     = max(1, min(500,   (int)($_GET['width']   ?? 22)));
$max_let   = max(10, min(10000, (int)($_GET['letters'] ?? 500)));
$indent    = max(0, min($width - 1, (int)($_GET['indent']  ?? 0)));

// Edition: BHS (Hebrew OT), NA28/TR (Greek NT), KJV (English, any book).
$is_ot = in_array($book_code, ELS_OT_CODES, true);
$valid_editions = ['BHS', 'NA28', 'TR', 'KJV'];
$default_edition = $is_ot ? 'BHS' : 'NA28';
$edition_code = $_GET['edition'] ?? $default_edition;
if (!in_array($edition_code, $valid_editions, true)) $edition_code = $default_edition;

// Books and dropdown data (ELS only shows MT books; no LXX mode).
$books    = bible_books();
$chapters = bible_chapters($book_code);
if (!$chapters) { $chapters = [1]; }
$chapter  = in_array($chapter, $chapters) ? $chapter : (int)$chapters[0];
$verses   = bible_verses($book_code, $chapter);
if (!$verses)  { $verses  = [1]; }
$verse    = in_array($verse, $verses) ? $verse : (int)$verses[0];

// -----------------------------------------------------------------------
// Letter-stripping helpers
// -----------------------------------------------------------------------
// `els_strip()` lives in els_lib.php so api.php can call it too.

// -----------------------------------------------------------------------
// Gematria / isopsephy / ordinal values
// -----------------------------------------------------------------------

/**
 * Return the numeric value for a single stripped letter.
 * Hebrew : standard gematria    (aleph=1 … tav=400; finals same as regular).
 * Greek  : isopsephy             (alpha=1 … omega=800).
 *          Covers both NFD-reduced basic Greek and Greek Extended precomposed.
 * English: simple ordinal value  (A=1 … Z=26).
 */
function els_letter_value(string $ch, string $lang): int {
    $cp = mb_ord($ch);

    if ($lang === 'Hebrew') {
        static $hv = [
            0x05D0=>1,  0x05D1=>2,  0x05D2=>3,  0x05D3=>4,  0x05D4=>5,
            0x05D5=>6,  0x05D6=>7,  0x05D7=>8,  0x05D8=>9,  0x05D9=>10,
            0x05DA=>20, 0x05DB=>20, 0x05DC=>30, 0x05DD=>40, 0x05DE=>40,
            0x05DF=>50, 0x05E0=>50, 0x05E1=>60, 0x05E2=>70, 0x05E3=>80,
            0x05E4=>80, 0x05E5=>90, 0x05E6=>90,
            0x05E7=>100, 0x05E8=>200, 0x05E9=>300, 0x05EA=>400,
        ];
        return $hv[$cp] ?? 0;
    }

    if ($lang === 'Greek') {
        // Build basic Greek code-point → isopsephy-value map once.
        static $gv = null;
        if ($gv === null) {
            // α β γ δ ε ζ η θ ι κ  λ  μ  ν  ξ  ο  π  ρ   σ/ς  τ   υ   φ   χ   ψ   ω
            $vals = [1,2,3,4,5,7,8,9,10,20,30,40,50,60,70,80,100,200,300,400,500,600,700,800];
            $gv = [];
            // lowercase α(03B1)..ω(03C9): 25 code-points, ς(03C2)=σ(03C3)=200
            $lc = array_keys(array_fill(0x03B1, 25, 0));
            $li = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,17,18,19,20,21,22,23];
            foreach ($lc as $i => $cp2) $gv[$cp2] = $vals[$li[$i]];
            // uppercase Α(0391)..Ρ(03A1), then Σ(03A3)..Ω(03A9) — skip 03A2
            $uc = array_merge(range(0x0391, 0x03A1), range(0x03A3, 0x03A9));
            foreach ($uc as $i => $cp2) $gv[$cp2] = $vals[$i];
        }
        if (isset($gv[$cp])) return $gv[$cp];
        // Greek Extended precomposed (U+1F00–U+1FFF): map range → base-letter value.
        if ($cp >= 0x1F00 && $cp <= 0x1FFF) {
            static $ext = null;
            if ($ext === null) {
                $ext = [];
                foreach ([
                    [0x1F00, 0x1F0F,   1], // α/Α variants
                    [0x1F10, 0x1F1F,   5], // ε/Ε
                    [0x1F20, 0x1F2F,   8], // η/Η
                    [0x1F30, 0x1F3F,  10], // ι/Ι
                    [0x1F40, 0x1F4F,  70], // ο/Ο
                    [0x1F50, 0x1F5F, 400], // υ/Υ
                    [0x1F60, 0x1F6F, 800], // ω/Ω
                    [0x1F70, 0x1F71,   1], // ά forms → α
                    [0x1F72, 0x1F73,   5], // έ forms → ε
                    [0x1F74, 0x1F75,   8], // ή forms → η
                    [0x1F76, 0x1F77,  10], // ί forms → ι
                    [0x1F78, 0x1F79,  70], // ό forms → ο
                    [0x1F7A, 0x1F7B, 400], // ύ forms → υ
                    [0x1F7C, 0x1F7D, 800], // ώ forms → ω
                    [0x1F80, 0x1F8F,   1], // α + iota subscript
                    [0x1F90, 0x1F9F,   8], // η + iota subscript
                    [0x1FA0, 0x1FAF, 800], // ω + iota subscript
                    [0x1FB0, 0x1FBF,   1], // α extended
                    [0x1FC0, 0x1FCF,   8], // η extended
                    [0x1FD0, 0x1FDF,  10], // ι extended
                    [0x1FE0, 0x1FE3, 400], // υ extended
                    [0x1FE4, 0x1FE5, 100], // ῤ ῥ → ρ
                    [0x1FE6, 0x1FEB, 400], // υ extended
                    [0x1FF2, 0x1FF4, 800], // ω + iota subscript
                    [0x1FF6, 0x1FFC, 800], // ω extended
                ] as [$lo, $hi, $val]) {
                    for ($i = $lo; $i <= $hi; $i++) $ext[$i] = $val;
                }
            }
            return $ext[$cp] ?? 0;
        }
        return 0;
    }

    if ($lang === 'English') {
        $o = ord(strtoupper($ch));
        return ($o >= 65 && $o <= 90) ? $o - 64 : 0; // A=1 … Z=26
    }
    return 0;
}

// -----------------------------------------------------------------------
// Cross-boundary text fetch
// -----------------------------------------------------------------------
// `els_fetch()` lives in els_lib.php so api.php can call it too. In remote
// API mode it delegates to remote_api_call('els_fetch', ...).

// -----------------------------------------------------------------------
// Fetch the letters
// -----------------------------------------------------------------------
$els = null;
$fetch_error = null;
try {
    $els = els_fetch($book_code, $chapter, $verse, $edition_code, $max_let);
} catch (Throwable $e) {
    $fetch_error = $e->getMessage();
    error_log('ELS fetch error: ' . $e->getMessage());
}

$letter_count  = $els ? mb_strlen($els['letters']) : 0;
$rows_needed   = $letter_count > 0 ? (int)ceil(($letter_count + $indent) / $width) : 0;

// -----------------------------------------------------------------------
// Edition labels for the dropdown
// -----------------------------------------------------------------------
$all_editions = [
    ['code' => 'BHS',  'name' => 'Biblia Hebraica Stuttgartensia'],
    ['code' => 'NA28', 'name' => 'Nestle-Aland 28th edition'],
    ['code' => 'TR',   'name' => 'Scrivener Textus Receptus 1894'],
    ['code' => 'KJV',  'name' => 'King James Version'],
];

// -----------------------------------------------------------------------
// Build $selector_extra_fields for verse_selector.inc.php
// -----------------------------------------------------------------------
ob_start(); ?>
    <label class="sel-label">Source</label>
    <select name="edition" id="sel-edition" data-static="1" title="Text edition">
    <?php foreach ($all_editions as $ed): ?>
        <option value="<?= h($ed['code']) ?>" <?= $ed['code'] === $edition_code ? 'selected' : '' ?>
                title="<?= h($ed['name']) ?>"><?= h($ed['code']) ?></option>
    <?php endforeach; ?>
    </select>
    <label class="sel-label">Width</label>
    <input type="number" name="width" id="els-width"
           value="<?= (int)$width ?>" min="1" max="500"
           style="width:60px" title="Letters per row">
    <label class="sel-label">Indent</label>
    <input type="number" name="indent" id="els-indent"
           value="<?= (int)$indent ?>" min="0" max="<?= max(0, $width - 1) ?>"
           style="width:55px" title="Empty cells before first letter (0 to width−1)">
    <label class="sel-label">Letters</label>
    <input type="number" name="letters" id="els-letters"
           value="<?= (int)$max_let ?>" min="10" max="10000"
           style="width:75px" title="Total letters to display">
    <input type="hidden" name="hl" id="els-hl-input" value="<?= h($_GET['hl'] ?? '') ?>">
<?php $selector_extra_fields = ob_get_clean();

// -----------------------------------------------------------------------
// Page HTML
// -----------------------------------------------------------------------
?>
<?php bible_render_layout_header(); ?>
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="author" content="Richard Amiel McGough">
<title>ELS Grid — <?= h($book_code) ?> <?= (int)$chapter ?>:<?= (int)$verse ?> (<?= h($edition_code) ?>)</title>
<?php bible_render_layout_styles(); ?>
</head>
<body>
<?php bible_render_layout_banner(); ?>
<div class="bible-layout">
<main class="bible-main">

<!-- ── Selector bar ──────────────────────────────────────────────────── -->
<div class="selector">
<?php require __DIR__ . '/verse_selector.inc.php'; ?>
</div>

<!-- ── Width preset quick-picks + live sums ─────────────────────────── -->
<div class="els-presets">
    <span class="els-presets-label">Quick width:</span>
    <?php foreach ([7, 11, 13, 17, 19, 22, 26, 41, 50] as $pw): ?>
        <button type="button" class="els-preset" data-width="<?= $pw ?>"><?= $pw ?></button>
    <?php endforeach; ?>
    <span class="els-vsep" aria-hidden="true"></span>
    <div id="els-sums" class="els-sums"></div>
</div>

<!-- ── Color palette ────────────────────────────────────────────────── -->
<div class="els-palette" id="els-palette">
    <span class="els-palette-label">Highlight:</span>
    <?php foreach ([
        '#3b82f6' => 'Blue',   '#ef4444' => 'Red',    '#22c55e' => 'Green',
        '#eab308' => 'Gold',   '#a855f7' => 'Purple', '#ec4899' => 'Pink',
        '#f97316' => 'Orange', '#14b8a6' => 'Teal',
    ] as $hex => $name): ?>
    <span class="els-swatch" data-color="<?= h($hex) ?>"
          style="background:<?= h($hex) ?>" title="<?= h($name) ?>"></span>
    <?php endforeach; ?>
    <input type="color" id="els-color-pick" value="#3b82f6" title="Custom color">
    <button type="button" id="els-clear-all" class="els-btn-sm">Clear all</button>
    <span class="els-vsep" aria-hidden="true"></span>
    <label class="els-palette-label" for="els-font-size">Size:</label>
    <input type="range" id="els-font-size" min="12" max="36" step="1" value="17" title="Letter size">
    <output id="els-font-size-val">17</output>
</div>

<!-- ── Preset save / load bar ────────────────────────────────────────── -->
<div class="els-preset-bar" id="els-preset-bar">
    <span class="els-palette-label">Presets:</span>
    <select id="els-preset-select" title="Saved presets">
        <option value="">— saved presets —</option>
    </select>
    <button type="button" id="els-preset-load" class="els-btn-sm" title="Load selected preset">Load</button>
    <button type="button" id="els-preset-del"  class="els-btn-sm els-btn-danger" title="Delete selected preset">Delete</button>
    <span class="els-vsep" aria-hidden="true"></span>
    <input type="text" id="els-preset-name" placeholder="preset name" maxlength="80"
           style="width:130px" title="Name for this preset">
    <button type="button" id="els-preset-save" class="els-btn-sm els-btn-primary" title="Save current view as a named preset">Save</button>
</div>

<!-- ── Info bar ──────────────────────────────────────────────────────── -->
<?php if ($els && $els['from_ref']): ?>
<div class="els-info">
    <?php
    $from = $els['from_ref'];
    $to   = $els['to_ref'];
    $ref_str = h($from['book']) . ' ' . (int)$from['chapter'] . ':' . (int)$from['verse'];
    if ($to && ($to['book'] !== $from['book'] || $to['chapter'] !== $from['chapter'] || $to['verse'] !== $from['verse'])) {
        $ref_str .= ' – ' . h($to['book']) . ' ' . (int)$to['chapter'] . ':' . (int)$to['verse'];
    }
    ?>
    <strong><?= $letter_count ?></strong> letters &nbsp;·&nbsp;
    <?= $rows_needed ?> rows × <?= (int)$width ?> columns
    <?php if ($indent > 0): ?>&nbsp;·&nbsp; indent <?= (int)$indent ?><?php endif; ?> &nbsp;·&nbsp;
    <?= $ref_str ?>
    &nbsp;·&nbsp; <?= h($edition_code) ?>
</div>
<?php endif; ?>

<!-- ── ELS Grid ──────────────────────────────────────────────────────── -->
<div class="els-wrap">
<?php if ($fetch_error): ?>
    <p class="els-error">Error fetching text: <?= h($fetch_error) ?></p>
<?php elseif ($letter_count === 0): ?>
    <p class="els-error">No letters found for <?= h($book_code) ?> <?= (int)$chapter ?>:<?= (int)$verse ?> in <?= h($edition_code) ?>.</p>
<?php else: ?>
    <div class="els-grid <?= $els['is_rtl'] ? 'els-rtl' : '' ?>"
         style="--els-cols:<?= (int)$width ?>">
        <?php
        $letters  = $els['letters'];
        $els_lang = $els['lang'];
        $len      = mb_strlen($letters);
        for ($i = 0; $i < $indent; $i++) {
            echo '<span class="els-cell els-cell-empty"></span>';
        }
        for ($i = 0; $i < $len; $i++) {
            $ch  = mb_substr($letters, $i, 1);
            $val = els_letter_value($ch, $els_lang);
            echo "<span class=\"els-cell\" data-idx=\"{$i}\" data-val=\"{$val}\">" . h($ch) . '</span>';
        }
        ?>
    </div>
<?php endif; ?>
</div><!-- .els-wrap -->

</main>
<?php require __DIR__ . '/bible_sidebar.php'; ?>
</div>

<script src="js/dropdowns.js"></script>
<script src="js/els.js"></script>
</body>
</html>
