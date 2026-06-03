<?php
// helpers.php — PHP helper functions for the Bible Browser template.
// Included by index.php; must not produce any output.

function h($s) { return htmlspecialchars((string)$s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
function lang_class($lang) { return $lang === 'Hebrew' ? 'heb' : 'grk'; }

// Strip parenthesised Romanisation from a Greek string that may contain
// multiple words, e.g. 'Ἐν (En) ἀρχῇ (archēa) ἦν (ēn)' → 'Ἐν ἀρχῇ ἦν'.
function strip_greek_parens(?string $s): string {
    if ($s === null) return '';
    $s = preg_replace('/\s*\([^)]+\)/u', '', $s);
    return trim(preg_replace('/\s+/u', ' ', $s));
}

// Split a Greek word like 'Ἐν (En)' into [original, transliteration].
function split_greek_word(?string $orig): array {
    if ($orig === null) return [null, null];
    if (preg_match('/^(.*?)\s+\((.+?)\)\s*$/u', $orig, $m)) {
        return [trim($m[1]), trim($m[2])];
    }
    return [trim($orig), null];
}

// Pick the Strong's number to display (prefer root word in {} brackets).
function strongs_display(?string $strongs): string {
    if (!$strongs) return '';
    if (preg_match('/\{[HG](\d{3,5})[A-Za-z]?\}/', $strongs, $m)) return $m[1];
    if (preg_match('/[HG](\d{3,5})[A-Za-z]?/',     $strongs, $m)) return $m[1];
    return $strongs;
}

// Build the canonical Strong's lookup key for the `strongs` DB table, where
// entries are stored unpadded as 'H1', 'H430', 'G851' etc. The word.strongs
// column carries padded forms like '{H0430}' or 'G0851/G1234'; this helper
// extracts the primary code (prefers the root word in {} brackets, same as
// strongs_display) and strips leading zeros. Falls back to deriving the
// H/G prefix from $language if the source has bare digits.
function strongs_full_code(?string $strongs, string $language): string {
    if (!$strongs) return '';
    if (preg_match('/\{([HG])(\d{3,5})[A-Za-z]?\}/', $strongs, $m)
        || preg_match('/([HG])(\d{3,5})[A-Za-z]?/',     $strongs, $m)) {
        return $m[1] . (ltrim($m[2], '0') ?: '0');
    }
    if (preg_match('/(\d{3,5})/', $strongs, $m)) {
        $prefix = $language === 'Hebrew' ? 'H' : 'G';
        return $prefix . (ltrim($m[1], '0') ?: '0');
    }
    return '';
}

// Hebrew morphology decoder lives in its own file. hebrew_letter_translit(),
// _decode_noun_suffix(), _decode_verb_suffix(), and format_hebrew_grammar()
// are all defined there. Required here so any caller that includes helpers.php
// gets them transparently.
require_once __DIR__ . '/hebrew_grammar.php';

// ----------------------------------------------------------------------
// Page layout helpers.
// ----------------------------------------------------------------------
// The web UI is normally embedded inside biblewheel.com's external
// header/banner includes. When those files aren't present (standalone
// dev mode, e.g. `php -S localhost:8080` from the web/ directory), we
// fall back to minimal local_header.inc.php / local_banner.inc.php.
//
// These helpers centralise the file_exists() check so every page calls
// the same code path. Pages should:
//   bible_render_layout_header();   // before <html>
//   bible_render_layout_styles();   // inside <head>
//   bible_render_layout_banner();   // first thing inside <body>

function bible_is_local_layout(): bool {
    static $cache = null;
    if ($cache !== null) return $cache;
    return $cache = !file_exists(__DIR__ . '/../include/bwHeader.inc');
}

function bible_render_layout_header(): void {
    if (bible_is_local_layout()) {
        require __DIR__ . '/local_header.inc.php';
    } else {
        require __DIR__ . '/../include/bwHeader.inc';
    }
}

function bible_render_layout_banner(): void {
    if (bible_is_local_layout()) {
        require __DIR__ . '/local_banner.inc.php';
    } else {
        require __DIR__ . '/../include/bwBanner.php';
    }
}

// Emit the page's stylesheet <link> tags. Hrefs are RELATIVE so the page
// renders correctly whether served at /bible/ (Apache/IIS) or at the
// origin root (php -S localhost:8080). Cache-busted by file mtime.
function bible_render_layout_styles(): void {
    if (!bible_is_local_layout()) {
        // Production: also pull biblewheel.com's shared bw.css.
        $bw = $_SERVER['DOCUMENT_ROOT'] . '/include/bw.css';
        if (file_exists($bw)) {
            echo '<link href="/include/bw.css?v=' . filemtime($bw)
               . '" rel="stylesheet" type="text/css">' . "\n";
        }
    }
    $local_css = __DIR__ . '/style.css';
    $v = file_exists($local_css) ? filemtime($local_css) : '';
    echo '<link rel="stylesheet" href="style.css?v=' . h($v) . '">' . "\n";
}

// ----------------------------------------------------------------------
// KJV inline-Strong's-tag renderer.
// ----------------------------------------------------------------------
// Source text looks like:
//   "In the beginning <07225> God <0430> created <01254> <0853> the heaven
//    <08064> and <0853> the earth <0776>."
// Each <NNNN> tag attaches to the immediately preceding English word.
// Multiple tags can follow one word ("created <01254> <0853>" → both
// codes attach to "created"). [bracketed] words are KJV-supplied
// insertions and become <em> italics; they do NOT consume tags.
//
// The output is sanitized HTML: hoverable spans for tagged words plus
// plain text / italics elsewhere. Class .kjv-tag is the hover hook for
// strongs-tooltip.js; data-strongs carries one or more space-separated
// canonical Strong's codes ("H430" or "G3056") for it to fetch.
//
// $testament must be 'OT' (→ H-prefix) or 'NT' (→ G-prefix).
function render_kjv_tagged(?string $raw, string $testament): string {
    if ($raw === null || $raw === '') return '';
    $prefix = $testament === 'NT' ? 'G' : 'H';

    // Tokenize. The five alternatives match in order:
    //   1) <NNNN>          inline Strong's tag (digits only)
    //   2) [text]          KJV-supplied insertion (rendered italic)
    //   3) {text}          STEPBible alt-marker (rare; show in braces)
    //   4) A word          letters + internal apostrophe
    //   5) Whitespace      collapsed later
    //   6) Everything else punctuation, kept verbatim
    // Note the trailing /u for Unicode safety.
    $pattern = '/<(\d+)>|\[([^\]]*)\]|\{([^}]*)\}|([A-Za-z][A-Za-z\']*)|(\s+)|([^\s<\[\{A-Za-z]+)/u';
    if (!preg_match_all($pattern, $raw, $matches, PREG_SET_ORDER)) {
        return h($raw);
    }

    // Pass 1: build a flat list of tokens, deferring tag attachment.
    // We branch on the first character of the whole match ($m[0]) — that
    // unambiguously identifies which alternative fired and avoids leaning
    // on cross-PHP-version differences in how unmatched capture groups
    // are filled in by preg_match_all.
    $tokens = [];
    $lastWordIdx = -1;
    foreach ($matches as $m) {
        $whole = $m[0];
        if ($whole === '') continue;
        $c0 = $whole[0];
        if ($c0 === '<') {
            // <NNNN> — append to the most recent word token, if any.
            $num  = ltrim((string)($m[1] ?? ''), '0');
            $code = $prefix . ($num === '' ? '0' : $num);
            if ($lastWordIdx >= 0) {
                $tokens[$lastWordIdx]['codes'][] = $code;
            } // else: tag with no preceding word — silently drop
        } elseif ($c0 === '[') {
            // [supplied] — italic, does not become a tag target.
            $tokens[] = ['type' => 'bracket', 'text' => (string)($m[2] ?? '')];
        } elseif ($c0 === '{') {
            // {brace} — rare alt marker; render literally.
            $tokens[] = ['type' => 'text', 'text' => '{' . (string)($m[3] ?? '') . '}'];
        } elseif (ctype_alpha($c0)) {
            $tokens[] = ['type' => 'word', 'text' => $whole, 'codes' => []];
            $lastWordIdx = count($tokens) - 1;
        } elseif (ctype_space($c0)) {
            $tokens[] = ['type' => 'space'];
        } else {
            $tokens[] = ['type' => 'text', 'text' => $whole];
        }
    }

    // Pass 2: emit HTML.
    $out = '';
    foreach ($tokens as $t) {
        switch ($t['type']) {
            case 'word':
                if (!empty($t['codes'])) {
                    $codes = implode(' ', $t['codes']);
                    $out .= '<span class="kjv-tag strongs-link" data-strongs="' . h($codes) . '">'
                          . h($t['text']) . '</span>';
                } else {
                    $out .= h($t['text']);
                }
                break;
            case 'bracket':
                $out .= '<em class="kjv-supplied">' . h($t['text']) . '</em>';
                break;
            case 'space':
                $out .= ' ';
                break;
            case 'text':
                $out .= h($t['text']);
                break;
        }
    }

    // Tidy up runs of whitespace left behind where tags were stripped, and
    // remove the space we'd otherwise leave between a word and trailing
    // punctuation (e.g. "void <0922>;" → "void ;" → "void;").
    $out = preg_replace('/ {2,}/', ' ', $out);
    $out = preg_replace('/ ([,.;:!?])/', '$1', $out);
    return trim($out);
}


// Remove STEPBible morpheme separators ('/' and '\') for inline display.
function clean_inline(?string $s): string {
    if ($s === null) return '';
    $s = str_replace(['/', '\\'], '', $s);
    $s = preg_replace('/\s+/u', ' ', $s);
    return trim($s);
}

// Count letters in a word's original text. For Hebrew this strips the
// section markers \פ (Petuhah) and \ס (Setumah) BEFORE counting --
// otherwise the bare peh/samek would inflate the letter total. Mirrors
// the logic in compute_gematria.py's clean_hebrew().
function letter_count(?string $text, string $language): int {
    if (!$text) return 0;
    if ($language === 'Hebrew') {
        // Strip Petuhah \פ and Setumah \ס section markers in BOTH formats:
        //   1. STEPBible's backslash form: \פ or \ס
        //   2. Trailing space form: ' פ' / ' ס' (common after sof passuq ׃)
        // Without (2) the samek/peh would be counted as a real letter,
        // producing inconsistent counts when the same logical word stores
        // its section marker in different formats across rows.
        $text = preg_replace('/\\\\[\x{05E4}\x{05E1}]/u',     '', $text);
        // Standalone parashah markers (פ Petuhah / ס Setumah) — only ones
        // bracketed by whitespace or string-end. Won't touch a samek/peh
        // that's part of a real Hebrew word like כּוֹס.
        $text = preg_replace('/(?<=\s)[\x{05E4}\x{05E1}](?=\s|$)/u', '', $text);
        $text = str_replace(['/', '\\'], '', $text);
        return preg_match_all('/[\x{05D0}-\x{05EA}]/u', $text);
    }
    $text = preg_replace('/\s*\([^)]+\)/u', '', $text);
    return preg_match_all(
        '/[\x{0345}\x{0391}-\x{03A9}\x{03B1}-\x{03C9}' .
        '\x{0386}\x{0388}-\x{038A}\x{038C}\x{038E}\x{038F}' .
        '\x{03AC}-\x{03CE}\x{1F00}-\x{1FBC}\x{1FBE}\x{1FC0}-\x{1FFD}]/u',
        $text
    );
}
