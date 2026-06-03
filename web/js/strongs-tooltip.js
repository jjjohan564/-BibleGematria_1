// strongs-tooltip.js — hover a Strong's number in a word cell to see the
// lemma, transliteration, pronunciation, and description from the `strongs`
// DB table. Results are cached in memory so each Strong's code only fetches
// once per session.
(function () {
    const HOVER_DELAY_MS = 250;   // hover before fetch + show
    const HIDE_DELAY_MS  = 250;   // mouseout grace period — long enough for
                                  // the cursor to traverse from the link
                                  // onto the tooltip without it closing

    const cache = new Map();      // code -> data (or null on miss)
    let activeRequest = null;     // outstanding fetch promise
    let showTimer = null;
    let hideTimer = null;
    let kjvHighlightEls = [];       // .word-cell elements lit up by KJV hover

    // Per-word payload (same source as search-trigger.js): needed to check
    // alternate Strong's codes (word_alt_strong rows) so that KJV words
    // tagged with a secondary code (e.g. G2258 for ἦν whose primary is G1510)
    // still find their interlinear cell.
    const _wdEl = document.getElementById('word-data');
    let WORD_DATA = {};
    try { if (_wdEl) WORD_DATA = JSON.parse(_wdEl.textContent); } catch (e) {}

    // Cross-source Strong's equivalences: some codes are used interchangeably
    // between the STEPBible TAGNT and the KJV Strong's tagging for the same
    // Greek verb forms, but the TAGNT alt_strong column does not list them.
    // G2046 (ῥηθείς aorist/passive forms) ↔ G4483 (ῥέω root/passive stem) is
    // the primary known case — every ῥηθέν/ἐρρέθη in the TAGNT uses G2046
    // while the KJV tags the same words G4483.
    // Systematic KJV↔TAGNT Strong's code discrepancies discovered by find_strongs_equiv.py.
    // Each pair is bidirectional: clicking a KJV word tagged X will match interlinear words
    // tagged Y and vice versa.
    const STRONG_EQUIV = {
        // ῥηθείς/ἐρρέθη passive forms: KJV=G4483, TAGNT=G2046
        'G2046': ['G4483'], 'G4483': ['G2046'],
        // οἶδα "know": KJV=G1492, TAGNT=G6063 (STEPBible split code)  (98.5%, 259 vv)
        'G1492': ['G6063'], 'G6063': ['G1492'],
        // μόνον/μόνος "only": adverb (G3440) vs adjective stem (G3441)  (100%, 64 vv)
        'G3440': ['G3441'], 'G3441': ['G3440'],
        // strong negation: KJV οὐ μή G3364, TAGNT μή G3361  (97.6%, 84 vv)
        'G3364': ['G3361'], 'G3361': ['G3364'],
        // "great": KJV comparative μείζων G3187, TAGNT positive μέγας G3173  (97.6%, 42 vv)
        'G3187': ['G3173'], 'G3173': ['G3187'],
        // "straightway": KJV εὐθύς G2117, TAGNT εὐθέως G2112  (100%, 8 vv)
        'G2117': ['G2112'], 'G2112': ['G2117'],
        // Jerusalem: KJV Ἰερουσαλήμ G2419, TAGNT Ἱεροσόλυμα G2414  (88.9%, 9 vv)
        'G2419': ['G2414'], 'G2414': ['G2419'],
        // "see/appear": KJV ὀπτάνομαι G3700, TAGNT ὁράω G3708  (100%, 5 vv)
        'G3700': ['G3708'], 'G3708': ['G3700'],
        // "more/many": KJV comparative πλείων G4119, TAGNT positive πολύς G4183  (90%, 10 vv)
        'G4119': ['G4183'], 'G4183': ['G4119'],
        // "before/former": KJV πρότερον G4386, TAGNT πρότερος G4387  (100%, 4 vv)
        'G4386': ['G4387'], 'G4387': ['G4386'],
    };

    // Expand a code list with any known equivalents so KJV ↔ interlinear
    // matching works even when they use different but synonymous codes.
    function expandEquiv(codes) {
        const out = codes.slice();
        codes.forEach(function (c) {
            const eq = STRONG_EQUIV[c];
            if (eq) eq.forEach(function (e) { if (out.indexOf(e) === -1) out.push(e); });
        });
        return out;
    }

    // Build the tooltip DOM once and reuse.
    const tip = document.createElement('div');
    tip.className = 'strongs-tooltip';
    tip.setAttribute('hidden', '');
    document.body.appendChild(tip);

    function escapeHtml(s) {
        if (s == null) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function renderOneEntry(code, data) {
        if (!data) {
            return `<div class="st-entry">` +
                     `<div class="st-head">${escapeHtml(code)}</div>` +
                     `<div class="st-miss">No entry in <code>strongs</code> table.</div>` +
                   `</div>`;
        }
        const lemma     = escapeHtml(data.lemma);
        const xlit      = escapeHtml(data.xlit);
        const pronounce = escapeHtml(data.pronounce);
        const desc      = escapeHtml(data.description);
        return `<div class="st-entry">` +
            `<div class="st-head">` +
                `<span class="st-code">${escapeHtml(data.number || code)}</span>` +
                (lemma ? ` <span class="st-lemma">${lemma}</span>` : '') +
            `</div>` +
            (xlit || pronounce
                ? `<div class="st-translit">` +
                    (xlit      ? `<span class="st-xlit">${xlit}</span>` : '') +
                    (pronounce ? ` <span class="st-pron">/${pronounce}/</span>` : '') +
                  `</div>`
                : '') +
            (desc ? `<div class="st-desc">${desc}</div>` : '') +
        `</div>`;
    }

    function renderTooltip(codes, dataArray) {
        // codes: array of 1+ canonical Strong's codes (e.g. ['H1254','H853'])
        // dataArray: same-length array of strongs rows (or null on miss).
        tip.innerHTML = codes.map((c, i) => renderOneEntry(c, dataArray[i])).join('');
    }

    // Split a `data-strongs` attribute into an array of canonical codes.
    // Accepts space- or comma-separated lists; filters out empty entries.
    function splitCodes(raw) {
        if (!raw) return [];
        return String(raw).split(/[\s,]+/).filter(Boolean);
    }

    function positionTooltip(targetEl) {
        const rect = targetEl.getBoundingClientRect();
        const margin = 6;
        // Default: below the cell, left-aligned with it
        let top  = rect.bottom + window.scrollY + margin;
        let left = rect.left   + window.scrollX;
        // Pre-render to measure
        tip.style.left = '0px';
        tip.style.top  = '0px';
        tip.removeAttribute('hidden');
        const tipW = tip.offsetWidth;
        const tipH = tip.offsetHeight;
        // Clamp to viewport width
        const viewW = document.documentElement.clientWidth;
        if (left + tipW + margin > viewW + window.scrollX) {
            left = viewW + window.scrollX - tipW - margin;
        }
        if (left < margin) left = margin;
        // If we'd run off the bottom, flip above the cell
        const viewBottom = window.scrollY + document.documentElement.clientHeight;
        if (top + tipH + margin > viewBottom) {
            top = rect.top + window.scrollY - tipH - margin;
        }
        tip.style.left = left + 'px';
        tip.style.top  = top  + 'px';
    }

    async function fetchStrongs(code) {
        if (cache.has(code)) return cache.get(code);
        try {
            // Relative URL — works whether the page is served at /bible/ or root.
            const r = await fetch(`api.php?api=strongs&code=${encodeURIComponent(code)}`);
            if (!r.ok) { cache.set(code, null); return null; }
            const data = await r.json();
            cache.set(code, data);
            return data;
        } catch (e) {
            cache.set(code, null);
            return null;
        }
    }

    function clearKjvHighlight() {
        kjvHighlightEls.forEach(function (el) { el.classList.remove('kjv-hl'); });
        kjvHighlightEls = [];
    }

    // For a .kjv-tag span, highlight matching interlinear word cells and
    // return the first matching .strongs element to anchor the tooltip.
    // Falls back to the word cell itself if the .strongs row is hidden.
    //
    // When a KJV word carries multiple codes (e.g. "created" → H1254 H853,
    // because the Hebrew object marker אֵת has no English equivalent and is
    // rolled onto the preceding word), only the cells that match the
    // EARLIEST KJV code are highlighted.  This prevents grammatical particles
    // that share a later code from also lighting up.  Alt codes (from
    // word_alt_strong) are still checked, which handles words like "was"
    // (KJV G2258 vs interlinear primary G1510).
    function applyKjvHighlight(kjvEl) {
        clearKjvHighlight();
        const codes = splitCodes(kjvEl.dataset.strongs);
        if (!codes.length) return null;
        const interlinear = document.getElementById('interlinear');
        if (!interlinear) return null;

        // First pass: for each word cell find the index of the earliest
        // KJV code it matches (primary or alt).  The KJV codes are also
        // expanded with known inter-source equivalents (e.g. G4483↔G2046).
        const candidates = [];
        interlinear.querySelectorAll('.word-cell').forEach(function (cell) {
            const strongsEl = cell.querySelector('.strongs');
            const primaryCodes = strongsEl ? splitCodes(strongsEl.dataset.strongs) : [];
            const wdata = WORD_DATA[cell.dataset.wordId];
            const altCodes = (wdata && Array.isArray(wdata.alts)) ? wdata.alts : [];
            const allCodes = expandEquiv(primaryCodes.concat(altCodes));
            let minIdx = -1;
            for (let i = 0; i < codes.length; i++) {
                if (allCodes.indexOf(codes[i]) !== -1) { minIdx = i; break; }
            }
            if (minIdx !== -1) candidates.push({ cell: cell, strongsEl: strongsEl, minIdx: minIdx });
        });

        if (!candidates.length) return null;

        // Second pass: only highlight cells that matched the earliest code
        // position, suppressing cells that only matched on a later code.
        const best = candidates.reduce(function (a, b) { return b.minIdx < a ? b.minIdx : a; }, candidates[0].minIdx);
        let anchor = null;
        candidates.forEach(function (c) {
            if (c.minIdx !== best) return;
            c.cell.classList.add('kjv-hl');
            kjvHighlightEls.push(c.cell);
            if (!anchor) {
                anchor = (c.strongsEl && c.strongsEl.offsetParent !== null) ? c.strongsEl : c.cell;
            }
        });
        return anchor;
    }

    function show(targetEl) {
        // For KJV-tagged words, highlight the matching interlinear cell(s)
        // and anchor the tooltip at the Strong's element in that cell.
        let posTarget = targetEl;
        if (targetEl.classList.contains('kjv-tag')) {
            const anchor = applyKjvHighlight(targetEl);
            if (anchor) posTarget = anchor;
        }

        const raw = targetEl.dataset.strongs;
        const codes = splitCodes(raw);
        if (codes.length === 0) return;

        // Fast path: every code is already cached.
        if (codes.every(c => cache.has(c))) {
            renderTooltip(codes, codes.map(c => cache.get(c)));
            positionTooltip(posTarget);
            return;
        }

        // Optimistic placeholder while fetching.
        tip.innerHTML = codes.map(c =>
            `<div class="st-entry"><div class="st-head">${escapeHtml(c)}</div>` +
            `<div class="st-loading">loading…</div></div>`
        ).join('');
        positionTooltip(posTarget);

        Promise.all(codes.map(c => fetchStrongs(c))).then(results => {
            if (tip.hasAttribute('hidden')) return;
            if (!targetEl.matches(':hover')) return;
            renderTooltip(codes, results);
            positionTooltip(posTarget);
        });
    }

    function hide() {
        tip.setAttribute('hidden', '');
        clearKjvHighlight();
    }

    // Event delegation: any .strongs-link element triggers the tooltip
    document.addEventListener('mouseover', (ev) => {
        const target = ev.target.closest('.strongs-link');
        if (!target) return;
        if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
        if (showTimer) clearTimeout(showTimer);
        showTimer = setTimeout(() => show(target), HOVER_DELAY_MS);
    });

    document.addEventListener('mouseout', (ev) => {
        const target = ev.target.closest('.strongs-link');
        if (!target) return;
        if (showTimer) { clearTimeout(showTimer); showTimer = null; }
        hideTimer = setTimeout(hide, HIDE_DELAY_MS);
    });

    // Sticky tooltip: hovering the tooltip itself cancels the pending
    // close so the user can move onto it to copy text. Leaving the tooltip
    // restarts the close timer.
    tip.addEventListener('mouseenter', () => {
        if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
    });
    tip.addEventListener('mouseleave', () => {
        if (hideTimer) clearTimeout(hideTimer);
        hideTimer = setTimeout(hide, HIDE_DELAY_MS);
    });

    // Hide on scroll/resize (positioning would be wrong)
    window.addEventListener('scroll', hide, { passive: true });
    window.addEventListener('resize', hide);
})();
