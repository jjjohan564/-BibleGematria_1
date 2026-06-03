<?php
// hebrew_grammar.php — STEPBible Hebrew morphology decoder.
//
// Turns STEPBible's compact Hebrew morph codes (e.g. "HVqp3ms" or
// "HC/Td/Vqp3ms") into readable shorthand (e.g. "V-Qal-Perf-3ms" or
// "Conj-w | Art-h | V-Qal-Perf-3ms"). All four functions live here
// because they're tightly coupled: format_hebrew_grammar() orchestrates
// hebrew_letter_translit() + _decode_noun_suffix() + _decode_verb_suffix().
//
// Only format_hebrew_grammar() is called from outside this file
// (see index.php). The other three are internal building blocks.
//
// Included by helpers.php so any caller that already requires helpers.php
// gets these for free without a separate include.

// Transliterate a Hebrew string (consonants only, vowel points/cantillation
// marks stripped first via the U+0591-U+05C7 range).
function hebrew_letter_translit(?string $heb): string {
    if (!$heb) return '';
    $heb = preg_replace('/[\x{0591}-\x{05BD}\x{05BF}\x{05C1}-\x{05C7}]/u', '', $heb);
    $map = [
        'א'=>"'", 'ב'=>'b', 'ג'=>'g', 'ד'=>'d', 'ה'=>'h', 'ו'=>'w',
        'ז'=>'z', 'ח'=>'ch','ט'=>'t', 'י'=>'y', 'כ'=>'k', 'ך'=>'k',
        'ל'=>'l', 'מ'=>'m', 'ם'=>'m', 'נ'=>'n', 'ן'=>'n', 'ס'=>'s',
        'ע'=>"`", 'פ'=>'p', 'ף'=>'p', 'צ'=>'ts','ץ'=>'ts','ק'=>'q',
        'ר'=>'r', 'ש'=>'sh','ת'=>'t',
    ];
    $len = mb_strlen($heb);
    $out = '';
    for ($i = 0; $i < $len; $i++) {
        $ch = mb_substr($heb, $i, 1);
        $out .= $map[$ch] ?? $ch;
    }
    return $out;
}

// Decode the noun-suffix portion of a STEPBible morph code.
// Position layout: [type][gender][number][state]
//   type   p=proper noun, g=gentilic
//   gender m/f/c/b
//   number s/p/d  (singular/plural/dual)
//   state  c=construct
function _decode_noun_suffix(string $rest): string {
    $type = substr($rest, 0, 1);
    $gen  = substr($rest, 1, 1);
    $num  = substr($rest, 2, 1);
    $stat = substr($rest, 3, 1);
    $parts = [];
    if ($type === 'p') $parts[] = 'pr';
    elseif ($type === 'g') $parts[] = 'gent';
    $gn = '';
    if (in_array($gen, ['m','f','c','b'], true)) $gn .= $gen;
    if (in_array($num, ['s','p','d'],     true)) $gn .= $num;
    if ($gn !== '') $parts[] = $gn;
    if ($stat === 'c') $parts[] = 'c';
    return $parts ? '-' . implode('-', $parts) : '';
}

// Decode the verb-suffix portion of a STEPBible morph code.
// Position layout: [stem][aspect][person/gender/number] ...
//   stem    Qal/Nifal/Piel/Pual/Hifil/Hofal/Hith/etc.
//   aspect  Perf/ConsecPerf/Imperf/ConsecImperf/Cohort/Juss/Imp/Part/etc.
//   tail    any remaining person-gender-number characters (e.g. '3ms')
function _decode_verb_suffix(string $rest): string {
    static $stems = [
        'q'=>'Qal','n'=>'Nifal','p'=>'Piel','P'=>'Pual','h'=>'Hifil','H'=>'Hofal',
        't'=>'Hith','D'=>'Pulpal','o'=>'Polel','r'=>'Polal','m'=>'Pilpel','k'=>'Pilpel',
        'Q'=>'QalPass','N'=>'NifalPass','v'=>'Hitpolel','T'=>'Hitpalpel',
    ];
    static $aspects = [
        'p'=>'Perf','q'=>'ConsecPerf','i'=>'Imperf','w'=>'ConsecImperf',
        'h'=>'Cohort','j'=>'Juss','v'=>'Imp','r'=>'Part','s'=>'PartPass',
        'a'=>'InfAbs','c'=>'InfCons',
    ];
    if (strlen($rest) < 2) return $rest === '' ? '' : '-' . $rest;
    $st = substr($rest, 0, 1);
    $as = substr($rest, 1, 1);
    $pieces = [$stems[$st] ?? $st, $aspects[$as] ?? $as];
    $tail = substr($rest, 2);
    if ($tail !== '') $pieces[] = $tail;
    return '-' . implode('-', $pieces);
}

// Format a raw STEPBible Hebrew morphology code into readable notation.
// $code:      e.g. 'HC/Td/Vqp3ms' (segments separated by '/')
// $morphemes: the word's morpheme array (used to pull the connecting letter
//             for prefixes like Conj, Prep, Art -- e.g. 'Conj-w').
function format_hebrew_grammar(?string $code, array $morphemes): string {
    if (!$code) return '';
    $non_punct = array_values(array_filter($morphemes,
        fn($m) => ($m['role'] ?? '') !== 'punctuation'));
    $segs = explode('/', $code);
    $out = [];
    foreach ($segs as $i => $seg) {
        if ($seg === '') continue;
        $seg  = ltrim($seg, 'H');           // strip the leading 'H' tag
        if ($seg === '') continue;
        $pos  = substr($seg, 0, 1);
        $rest = substr($seg, 1);
        $morph  = $non_punct[$i] ?? null;
        $letter = $morph ? hebrew_letter_translit($morph['hebrew'] ?? '') : '';
        $piece  = '';
        switch ($pos) {
            case 'A': $piece = 'Adj' . _decode_noun_suffix($rest); break;
            case 'C': $piece = 'Conj' . ($letter ? '-' . $letter : ''); break;
            case 'D': $piece = 'Adv'; break;
            case 'N': $piece = 'N'   . _decode_noun_suffix($rest); break;
            case 'P': $piece = 'Pro' . ($rest !== '' ? '-' . $rest : ''); break;
            case 'R': $piece = 'Prep' . ($letter ? '-' . $letter : ''); break;
            case 'S': $piece = 'Suf'  . ($letter ? '-' . $letter : '') . ($rest !== '' ? '-' . $rest : ''); break;
            case 'T':
                // Particle subtypes
                $sub  = substr($rest, 0, 1);
                $tmap = ['d'=>'Art','n'=>'Neg','c'=>'Conj','j'=>'Adv','i'=>'Inter',
                         'a'=>'Acc','e'=>'Excl','m'=>'Cond','o'=>'DirObj','r'=>'Rel'];
                $piece = $tmap[$sub] ?? 'Part';
                if ($letter) $piece .= '-' . $letter;
                break;
            case 'V': $piece = 'V' . _decode_verb_suffix($rest); break;
            default:  $piece = $seg;
        }
        $out[] = $piece;
    }
    return implode(' | ', $out);
}
