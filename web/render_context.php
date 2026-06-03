<?php
// render_context.php
//
// Pure data prep for index.php's verse-card template. Given the result of
// one or more bible_verse_full() / lxx_verse_full() calls plus the URL
// state (chapter / verse / count / edition_code), returns an associative
// array of all the variables the template needs:
//
//   detail_payload    — keyed by word id, the per-word JSON payload that
//                       variant-switcher.js and gematria.js consume.
//   first_verse_row   — verse + book row for the first verse in the range.
//   primary_lang      — 'Hebrew' or 'Greek'; drives styling and gematria.
//   primary_lcls      — lang_class($primary_lang); CSS class for the run.
//   is_heb_overall    — convenience boolean.
//   range_title       — e.g. 'Genesis 1:1' or 'Genesis 1:1-3' (HTML-safe).
//   range_ref_str     — same string, RAW (not HTML-encoded) for JS payload.
//   total_words       — sum of word counts across displayed verses.
//   any_sig_variant   — TRUE if any displayed verse has has_significant_variant.
//   count_qs          — '&amp;count=N&amp;edition=CODE' for prev/next links.
//
// Depends on helpers.php for: format_hebrew_grammar, clean_inline,
// strip_greek_parens, split_greek_word, lang_class, h.
//
// The caller is expected to `extract($ctx)` so the template's variable
// names stay unchanged.

function build_render_context(array $verses_data,
                              int $chapter,
                              int $verse,
                              int $count,
                              string $edition_code,
                              int $actual_count,
                              int $last_verse_num): array
{
    // ---- per-word JS payload (keyed by word id) --------------------
    $detail_payload = [];
    foreach ($verses_data as $vd_pl) {
        $lang_pl = $vd_pl['verse']['language'];
        foreach ($vd_pl['words'] as $w) {
            $is_heb = $lang_pl === 'Hebrew';
            // Prefer canonical_* fields when present (set by db.php when a
            // variant substituted the cell). That way the payload's
            // `original` / `translit` / etc. always describe the TRUE
            // canonical word, so variant-switcher can cycle base→variant
            // and back correctly.
            $payload_text_original   = $w['canonical_text_original']   ?? $w['text_original'];
            $payload_transliteration = $w['canonical_transliteration'] ?? $w['transliteration'];
            $payload_translation     = $w['canonical_translation']     ?? $w['translation'];
            $payload_strongs         = $w['canonical_strongs']         ?? $w['strongs'];
            $payload_grammar         = $w['canonical_grammar']         ?? $w['grammar'];

            $word_grammar  = $is_heb ? format_hebrew_grammar($payload_grammar, $w['morphemes']) : $payload_grammar;
            $word_orig     = $is_heb ? clean_inline($payload_text_original)   : strip_greek_parens($payload_text_original);
            $word_translit = $is_heb ? clean_inline($payload_transliteration) : (split_greek_word($payload_text_original)[1] ?? '');
            $word_english  = $is_heb ? clean_inline($payload_translation)     : $payload_translation;

            $detail_payload[(int)$w['id']] = [
                'lang'        => $lang_pl,
                'position'    => (int)$w['position'],
                'word_num'    => (int)$w['word_num'],
                'chunk_num'   => (int)$w['chunk_num'],
                'source'      => $w['source_type'],
                'strongs'     => $payload_strongs,
                'grammar'     => $word_grammar,
                'grammar_raw' => $w['grammar'],
                'lemma'       => $w['dictionary_form'],
                'sub'         => $w['submeaning'],
                'sst_inst'    => $w['sstrong_instance'],
                'editions'    => array_map(fn($e) => [
                    'code'  => $e['code'],
                    'name'  => $e['name'],
                    'minor' => (bool)$e['is_minor'],
                ], $w['editions']),
                'alts'        => $w['alts'],
                'morphemes'   => array_map(fn($m) => [
                    'role'   => $m['role'],
                    'strong' => $m['strong_code'],
                    'hebrew' => $m['hebrew'],
                    'gloss'  => $m['gloss'],
                    'sub'    => $m['submeaning'],
                ], $w['morphemes']),
                'links'       => array_map(fn($l) => [
                    'direction'  => $l['direction'],
                    'tgt_num'    => (int)$l['target_word_num'],
                    'tgt_text'   => $is_heb ? clean_inline($l['target_text']) : $l['target_text'],
                    'tgt_strong' => $l['target_strong'],
                ], $w['links']),
                'variants'    => array_map(function($vt) use ($is_heb) {
                    return [
                        'kind'     => $vt['kind'],
                        'text'     => $is_heb ? clean_inline($vt['text_original'])   : $vt['text_original'],
                        'translit' => $is_heb ? clean_inline($vt['transliteration']) : $vt['transliteration'],
                        'trans'    => $is_heb ? clean_inline($vt['translation'])     : $vt['translation'],
                        'strongs'  => $vt['strongs'],
                        'grammar'  => $is_heb ? format_hebrew_grammar($vt['grammar'], []) : $vt['grammar'],
                        'note'     => $vt['note'],
                        'editions' => array_map(fn($e) => [
                            'code'  => $e['code'],
                            'name'  => $e['name'],
                            'minor' => (bool)$e['is_minor'],
                        ], $vt['editions'] ?? []),
                    ];
                }, $w['variants']),
                'original'    => $word_orig,
                'translit'    => $word_translit,
                'english'     => $word_english,
                'gem_std'     => (int)$w['gem_std'],
                'gem_ord'     => (int)$w['gem_ord'],
                'gem_red'     => (int)$w['gem_red'],
            ];
        }
    }

    // ---- range-level scalars consumed by the template --------------
    $first_verse_row = $verses_data[0]['verse'];
    $primary_lang    = $first_verse_row['language'];
    $primary_lcls    = lang_class($primary_lang);
    $is_heb_overall  = $primary_lang === 'Hebrew';

    $range_suffix    = $actual_count > 1 ? '-' . (int)$last_verse_num : '';
    $range_title     = h($first_verse_row['book_name']) . ' ' . (int)$chapter . ':' . (int)$verse . $range_suffix;
    $range_ref_str   =     $first_verse_row['book_name']  . ' ' . (int)$chapter . ':' . (int)$verse . $range_suffix;

    $total_words     = 0;
    $any_sig_variant = false;
    foreach ($verses_data as $vd_meta) {
        $total_words += count($vd_meta['words']);
        if ((int)$vd_meta['verse']['has_significant_variant']) $any_sig_variant = true;
    }

    // Preserve count and edition in prev/next links.
    $count_qs  = $count > 1 ? '&amp;count=' . (int)$count : '';
    $count_qs .= '&amp;edition=' . h($edition_code);

    return [
        'detail_payload'   => $detail_payload,
        'first_verse_row'  => $first_verse_row,
        'primary_lang'     => $primary_lang,
        'primary_lcls'     => $primary_lcls,
        'is_heb_overall'   => $is_heb_overall,
        'range_title'      => $range_title,
        'range_ref_str'    => $range_ref_str,
        'total_words'      => $total_words,
        'any_sig_variant'  => $any_sig_variant,
        'count_qs'         => $count_qs,
    ];
}
