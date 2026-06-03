// gematria.js — gematria analysis panel with prime factorization.
(function () {
    const gemPanel    = document.getElementById('gematria-panel');
    const rowsEl      = document.getElementById('gem-rows');
    const interlinear = document.getElementById('interlinear');
    if (!gemPanel || !rowsEl || !interlinear) return;

    function factorize(n) {
        const factors = [];
        for (let d = 2; d * d <= n; d++) {
            while (n % d === 0) { factors.push(d); n = Math.floor(n / d); }
        }
        if (n > 1) factors.push(n);
        return factors;
    }

    function formatFactors(n) {
        if (n <= 1) return String(n);
        const f = factorize(n);
        if (f.length === 1) return 'prime';
        const parts = [];
        let i = 0;
        while (i < f.length) {
            let exp = 1;
            while (i + exp < f.length && f[i + exp] === f[i]) exp++;
            parts.push(exp > 1 ? `${f[i]}<sup>${exp}</sup>` : String(f[i]));
            i += exp;
        }
        return parts.join(' × ');
    }

    // Like formatFactors but wraps each prime in a search link.
    function formatFactorsLinked(n) {
        if (n <= 1) return String(n);
        const f = factorize(n);
        if (f.length === 1) return 'prime';
        const parts = [];
        let i = 0;
        while (i < f.length) {
            let exp = 1;
            while (i + exp < f.length && f[i + exp] === f[i]) exp++;
            const link = `<a href="search.php?mode=gematria&amp;standard=${f[i]}" class="gem-factor-link">${f[i]}</a>`;
            parts.push(exp > 1 ? `${link}<sup>${exp}</sup>` : link);
            i += exp;
        }
        return parts.join(' × ');
    }

    // Count how many primes are ≤ n (i.e. n's 1-based position in the primes).
    function primeIndex(n) {
        if (n < 2) return 0;
        let count = 0;
        outer: for (let i = 2; i <= n; i++) {
            for (let d = 2; d * d <= i; d++) { if (i % d === 0) continue outer; }
            count++;
        }
        return count;
    }

    function ordinal(n) {
        const v = n % 100;
        const s = (v >= 11 && v <= 13) ? 'th'
                : (n % 10 === 1) ? 'st'
                : (n % 10 === 2) ? 'nd'
                : (n % 10 === 3) ? 'rd' : 'th';
        return n + s;
    }

    const typeLabels = { std: 'Standard', ord: 'Ordinal', red: 'Reduced' };
    const dataAttrs  = { std: 'gemStd',   ord: 'gemOrd',  red: 'gemRed'  };

    // ---- letter-counting helpers ----
    // Greek diacritic-strip regex preserves iota subscript (U+0345) so it
    // gets counted as one iota. Hebrew counts only consonants in U+05D0-05EA
    // (alef-tav + sofit forms).
    const _GREEK_DIA = /[\u0300-\u0344\u0346-\u036F]/g;
    const _SECTION_MARKERS = new Set(['פ', 'ס']);

    function isSectionMarkerCell(cell) {
        const orig = cell.querySelector('.original');
        if (!orig) return false;
        return _SECTION_MARKERS.has(orig.textContent.trim());
    }

    function countLetters(text, isHeb) {
        if (!text) return 0;
        let n = 0;
        if (isHeb) {
            for (const ch of text) {
                const cp = ch.codePointAt(0);
                if (cp >= 0x05D0 && cp <= 0x05EA) n++;
            }
            return n;
        }
        // Greek: NFD-strip diacritics (keep U+0345), then count letters
        const clean = text.normalize('NFD').replace(_GREEK_DIA, '');
        for (const ch of clean) {
            const cp = ch.codePointAt(0);
            if (cp === 0x0345)                        { n++; continue; }
            if (cp >= 0x0391 && cp <= 0x03A9)         { n++; continue; }
            if (cp >= 0x03B1 && cp <= 0x03C9)         { n++; continue; }
        }
        return n;
    }

    function activeTypes() {
        const types = [];
        for (const t of ['std', 'ord', 'red']) {
            const box = document.querySelector(`input[data-opt="gem-${t}"]`);
            if (box && box.checked) types.push(t);
        }
        return types;
    }

    function sumCells(t, cells) {
        let total = 0;
        cells.forEach(cell => {
            total += parseInt(cell.dataset[dataAttrs[t]] || 0, 10);
        });
        return total;
    }

    function rebuild() {
        const types = activeTypes();
        if (types.length === 0) { gemPanel.setAttribute('hidden', ''); return; }
        gemPanel.removeAttribute('hidden');

        const allCells      = Array.from(interlinear.querySelectorAll('.word-cell'));
        const selectedCells = allCells.filter(c => c.classList.contains('selected'));
        const useAll        = selectedCells.length === 0 || selectedCells.length === allCells.length;
        const cells         = useAll ? allCells : selectedCells;

        const clearBtn   = document.getElementById('gem-clear');
        const linkBtn    = document.getElementById('gem-link-btn');
        if (clearBtn) clearBtn.style.display = selectedCells.length > 0 ? '' : 'none';
        if (linkBtn)  linkBtn.style.display  = selectedCells.length > 0 ? '' : 'none';

        // Word and letter counts. Letter count comes from PHP-computed
        // data-letter-count attribute (set in index.php via letter_count()
        // in helpers.php) so Hebrew section markers \פ and \ס are
        // correctly excluded -- something JS can't reliably do post-display
        // because clean_inline() has already stripped the leading backslash.
        // Synthetic 'addition' cells (negative ids) fall back to JS counting.
        const realCells = cells.filter(c => !isSectionMarkerCell(c));
        let wordCount = realCells.length;
        let letterCount = 0;
        realCells.forEach(c => {
            const attr = c.dataset.letterCount;
            if (attr !== undefined && attr !== '') {
                letterCount += parseInt(attr, 10) || 0;
            } else {
                const origEl = c.querySelector('.original');
                if (!origEl) return;
                const isHeb = origEl.classList.contains('heb');
                letterCount += countLetters(origEl.textContent.trim(), isHeb);
            }
        });

        rowsEl.innerHTML = '';

        // Prepend a counts row (Words · Letters)
        const countsRow = document.createElement('div');
        countsRow.className = 'gem-row gem-counts';
        countsRow.innerHTML =
            `<span class="gem-row-type">Words</span>` +
            `<span class="gem-row-value">${wordCount}</span>` +
            `<span class="gem-row-sep">·</span>` +
            `<span class="gem-row-type">Letters</span>` +
            `<span class="gem-row-value">${letterCount}</span>`;
        rowsEl.appendChild(countsRow);

        for (const t of types) {
            const val     = sumCells(t, cells);
            const fStr    = t === 'std' ? formatFactorsLinked(val) : formatFactors(val);
            const isPrime = fStr === 'prime';
            const idx     = isPrime ? ordinal(primeIndex(val)) : 'not prime';
            const valStr  = t === 'std'
                ? `<a href="search.php?mode=gematria&amp;standard=${val}" class="gem-link">${val}</a>`
                : String(val);
            const row     = document.createElement('div');
            row.className = 'gem-row';
            row.innerHTML =
                `<span class="gem-row-type">${typeLabels[t]}</span>` +
                `<span class="gem-row-value">${valStr}</span>` +
                `<span class="gem-row-factors${isPrime ? ' is-prime' : ''}">Factors ${fStr} · Prime index ${idx}</span>`;
            rowsEl.appendChild(row);
        }
    }

    document.querySelectorAll('input[data-opt^="gem-"]').forEach(box => {
        box.addEventListener('change', rebuild);
    });

    window._gemRebuild = rebuild;
    rebuild();
})();
