// variant-switcher.js — cycles word cells through textual variants,
// and syncs per-cell gematria on initial page load.
(function () {
    const el = document.getElementById('word-data');
    if (!el) return;
    let DATA = {};
    try { DATA = JSON.parse(el.textContent); } catch (e) { return; }

    const FALLBACK_HEB = (typeof VERSE_LANG !== 'undefined' && VERSE_LANG === 'Hebrew');

    // ---- Hebrew gematria maps (sofit forms map to base-letter values
    // for standard / reduced; ordinal uses the same position as the base letter). ----
    const HEB_STD = {
        'א':1,'ב':2,'ג':3,'ד':4,'ה':5,'ו':6,'ז':7,'ח':8,'ט':9,
        'י':10,'כ':20,'ל':30,'מ':40,'נ':50,'ס':60,'ע':70,'פ':80,'צ':90,
        'ק':100,'ר':200,'ש':300,'ת':400,
        'ך':20,'ם':40,'ן':50,'ף':80,'ץ':90
    };
    const HEB_ORD = {
        'א':1,'ב':2,'ג':3,'ד':4,'ה':5,'ו':6,'ז':7,'ח':8,'ט':9,'י':10,
        'כ':11,'ל':12,'מ':13,'נ':14,'ס':15,'ע':16,'פ':17,'צ':18,'ק':19,'ר':20,'ש':21,'ת':22,
        'ך':11,'ם':13,'ן':14,'ף':17,'ץ':18
    };
    const HEB_RED = {
        'א':1,'ב':2,'ג':3,'ד':4,'ה':5,'ו':6,'ז':7,'ח':8,'ט':9,
        'י':1,'כ':2,'ל':3,'מ':4,'נ':5,'ס':6,'ע':7,'פ':8,'צ':9,
        'ק':1,'ר':2,'ש':3,'ת':4,
        'ך':2,'ם':4,'ן':5,'ף':8,'ץ':9
    };

    // ---- Greek isopsephy maps ----
    // GRK_STD: classical isopsephy. ζ=7 (digamma/stigma fills the 6 slot
    // in the archaic ordering used for numeric values).
    // GRK_ORD: modern 24-letter ordinal — ζ is the 6th letter.
    const GRK_STD = {
        'α':1,'β':2,'γ':3,'δ':4,'ε':5,'ζ':7,'η':8,'θ':9,
        'ι':10,'κ':20,'λ':30,'μ':40,'ν':50,'ξ':60,'ο':70,'π':80,
        'ρ':100,'σ':200,'ς':200,'τ':300,'υ':400,'φ':500,'χ':600,'ψ':700,'ω':800
    };
    const GRK_ORD = {
        'α':1,'β':2,'γ':3,'δ':4,'ε':5,'ζ':6,'η':7,'θ':8,
        'ι':9,'κ':10,'λ':11,'μ':12,'ν':13,'ξ':14,'ο':15,'π':16,
        'ρ':17,'σ':18,'ς':18,'τ':19,'υ':20,'φ':21,'χ':22,'ψ':23,'ω':24
    };

    const IOTA_SUB = 'ͅ';   // combining iota subscript (ypogegrammeni)

    function digitalRoot(n) {
        if (n <= 0) return 0;
        while (n > 9) {
            let s = 0;
            while (n > 0) { s += n % 10; n = Math.floor(n / 10); }
            n = s;
        }
        return n;
    }

    function hebGemVal(text, map) {
        if (!text) return 0;
        let s = 0;
        for (const ch of text) s += map[ch] || 0;
        return s;
    }

    // Decompose Greek to NFD, strip combining diacritics EXCEPT iota subscript
    // (U+0345), lowercase. Iota subscript is preserved because it represents
    // a semantic iota — counted as ι in both standard and ordinal isopsephy.
    function grkClean(text) {
        return (text || '')
            .normalize('NFD')
            .replace(/[̀-̈́͆-ͯ]/g, '')
            .toLowerCase();
    }
    function grkGemVal(text) {
        if (!text) return 0;
        let s = 0;
        for (const ch of grkClean(text)) {
            if (ch === IOTA_SUB) s += GRK_STD['ι'];
            else                  s += GRK_STD[ch] || 0;
        }
        return s;
    }
    function grkGemOrd(text) {
        if (!text) return 0;
        let s = 0;
        for (const ch of grkClean(text)) {
            if (ch === IOTA_SUB) s += GRK_ORD['ι'];
            else                  s += GRK_ORD[ch] || 0;
        }
        return s;
    }

    function computeGematriaForText(text, isHeb) {
        if (isHeb) {
            return {
                std: hebGemVal(text, HEB_STD),
                ord: hebGemVal(text, HEB_ORD),
                red: hebGemVal(text, HEB_RED),
            };
        }
        const std = grkGemVal(text);
        return { std: std, ord: grkGemOrd(text), red: digitalRoot(std) };
    }

    function strongsDisplay(s) {
        if (!s) return '';
        let m = s.match(/\{[HG](\d{3,5})[A-Za-z]?\}/);
        if (m) return m[1];
        m = s.match(/[HG](\d{3,5})[A-Za-z]?/);
        return m ? m[1] : s;
    }

    function applyVariant(cell, wordId, idx) {
        const d = DATA[wordId];
        if (!d) return;
        const v = idx === 'base' ? null : d.variants[idx];

        const isHeb = d.lang ? (d.lang === 'Hebrew') : FALLBACK_HEB;
        const lcls  = isHeb ? 'heb' : 'grk';
        const isAbsent = v && v.kind === 'absent';

        const text     = isAbsent ? '' : (v ? (v.text ?? '') : (d.original ?? ''));
        const translit = isAbsent ? '' : ((v && v.translit) ? v.translit : (d.translit ?? ''));
        const english  = isAbsent ? '' : ((v && v.trans)    ? v.trans    : (d.english  ?? ''));
        const strongs  = isAbsent ? '' : strongsDisplay(v ? v.strongs : d.strongs);
        const grammar  = isAbsent ? '' : ((v && v.grammar)  ? v.grammar  : (d.grammar  ?? ''));

        const q = sel => cell.querySelector(sel);
        const origEl = q('.original');
        if (origEl) { origEl.textContent = text; origEl.className = 'original ' + lcls; }
        const te = q('.translit'); if (te) te.textContent = translit || ' ';
        const ee = q('.english');  if (ee) ee.textContent = english;
        const se = q('.strongs');  if (se) se.textContent = strongs;
        const ge = q('.grammar');  if (ge) ge.textContent = grammar;

        cell.classList.toggle('cell-absent', !!isAbsent);

        if (isAbsent) {
            cell.dataset.gemStd = 0;
            cell.dataset.gemOrd = 0;
            cell.dataset.gemRed = 0;
        } else {
            const g = computeGematriaForText(text, isHeb);
            cell.dataset.gemStd = g.std;
            cell.dataset.gemOrd = g.ord;
            cell.dataset.gemRed = g.red;
        }

        cell.dataset.activeVariant = idx;

        if (window._updateGematria) window._updateGematria();
        if (window._gemRebuild)     window._gemRebuild();
        if (window._analysisRebuild) window._analysisRebuild();
    }

    // Click cycles: base → v[0] → v[1] → ... → base
    document.addEventListener('click', function (ev) {
        const btn = ev.target.closest('.variant-btn');
        if (!btn) return;
        ev.stopPropagation();

        const cell   = btn.closest('.word-cell');
        if (!cell) return;
        const wordId = cell.dataset.wordId;
        const d      = DATA[wordId];
        if (!d || !d.variants || !d.variants.length) return;

        const current = cell.dataset.activeVariant ?? 'base';
        let next;
        if (current === 'base') {
            next = 0;
        } else {
            const i = parseInt(current, 10);
            next = (i + 1 >= d.variants.length) ? 'base' : i + 1;
        }
        applyVariant(cell, wordId, next);

        const label = next === 'base' ? 'Base text'
                    : (d.variants[next].kind || 'Variant ' + (next + 1));
        const total = d.variants.length;
        btn.title = next === 'base'
            ? `${total} variant${total > 1 ? 's' : ''} — click to cycle`
            : `Now: ${label} — click to cycle`;
    });

    // On initial page load, recompute every Greek word cell's gematria
    // from its displayed text. The precomputed gem_std/ord/red attributes
    // are keyed to the canonical word.id; when an edition substitutes the
    // slot (e.g. John 1:18 θεος → υἱός in TR), the precomputed values are
    // stale.
    //
    // HEBREW IS DELIBERATELY SKIPPED: there's no Hebrew edition dropdown
    // (NA28 and TR are both Greek), so Hebrew cells always show canonical
    // text and the precomputed gematria_word values are authoritative.
    // The precomputation in compute_gematria.py strips Petuhah \פ and
    // Setumah \ס section markers, but the displayed text has the
    // backslash removed by clean_inline() in helpers.php, so recomputing
    // in JS would wrongly count פ=80 and ס=60 for those section markers.
    function syncGematriaOnLoad() {
        document.querySelectorAll('.word-cell').forEach(cell => {
            const wordId = cell.dataset.wordId;
            const d      = DATA[wordId] || null;
            const origEl = cell.querySelector('.original');
            if (!origEl) return;
            const isHeb = (d && d.lang) ? (d.lang === 'Hebrew') : FALLBACK_HEB;
            if (isHeb) return;   // trust precomputed values; see comment above
            const displayed = origEl.textContent.trim();
            const g = computeGematriaForText(displayed, isHeb);
            cell.dataset.gemStd = g.std;
            cell.dataset.gemOrd = g.ord;
            cell.dataset.gemRed = g.red;
        });
        if (window._updateGematria) window._updateGematria();
        if (window._gemRebuild)     window._gemRebuild();
        if (window._analysisRebuild) window._analysisRebuild();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', syncGematriaOnLoad);
    } else {
        syncGematriaOnLoad();
    }
})();
