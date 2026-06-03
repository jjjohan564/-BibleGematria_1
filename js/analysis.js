// analysis.js -- selected section audit, comparison tabs, and exports.
(function () {
    'use strict';

    const interlinear = document.getElementById('interlinear');
    const studyPanel = document.getElementById('study-panel');
    if (!interlinear || !studyPanel) return;

    const dataEl = document.getElementById('word-data');
    let WORD_DATA = {};
    try { if (dataEl) WORD_DATA = JSON.parse(dataEl.textContent || '{}'); } catch (e) {}

    const scopeEl = document.getElementById('selection-scope');
    const chipEl = document.getElementById('selection-chip');
    const summaryEl = document.getElementById('selection-summary');
    const originalEl = document.getElementById('selection-original');
    const meaningEl = document.getElementById('selection-meaning');
    const wordListEl = document.getElementById('analysis-word-list');
    const exportStatus = document.getElementById('export-status');

    const detailEl = document.getElementById('word-detail');
    const detailTitleEl = document.getElementById('wd-title');
    const detailBodyEl = document.getElementById('wd-body');

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
    const IOTA_SUB = 'ͅ';
    const primeIndexCache = new Map();

    function esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, ch => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[ch]));
    }

    function textOf(cell, selector) {
        const el = cell.querySelector(selector);
        return el ? el.textContent.trim() : '';
    }

    function intAttr(cell, name) {
        return parseInt(cell.dataset[name] || '0', 10) || 0;
    }

    function digitalRoot(n) {
        if (n <= 0) return 0;
        return 1 + ((n - 1) % 9);
    }

    function factorize(n) {
        n = Math.abs(parseInt(n, 10) || 0);
        if (n <= 1) return [];
        const factors = [];
        for (let d = 2; d * d <= n; d++) {
            while (n % d === 0) {
                factors.push(d);
                n = Math.floor(n / d);
            }
        }
        if (n > 1) factors.push(n);
        return factors;
    }

    function isPrime(n) {
        n = parseInt(n, 10) || 0;
        return n > 1 && factorize(n).length === 1;
    }

    function formatFactorsPlain(n) {
        n = parseInt(n, 10) || 0;
        if (n <= 1) return String(n);
        const factors = factorize(n);
        if (factors.length === 1) return 'prime';
        const parts = [];
        for (let i = 0; i < factors.length;) {
            let exp = 1;
            while (i + exp < factors.length && factors[i + exp] === factors[i]) exp++;
            parts.push(exp > 1 ? factors[i] + '^' + exp : String(factors[i]));
            i += exp;
        }
        return parts.join(' x ');
    }

    function primeIndex(n) {
        n = parseInt(n, 10) || 0;
        if (!isPrime(n)) return null;
        if (primeIndexCache.has(n)) return primeIndexCache.get(n);
        let count = 0;
        outer: for (let i = 2; i <= n; i++) {
            for (let d = 2; d * d <= i; d++) {
                if (i % d === 0) continue outer;
            }
            count++;
        }
        primeIndexCache.set(n, count);
        return count;
    }

    function valueNote(n) {
        const idx = primeIndex(n);
        return 'Factors ' + formatFactorsPlain(n) + ' · Prime index ' + (idx || 'not prime');
    }

    function hebrewLetters(text) {
        const letters = [];
        for (const ch of String(text || '')) {
            if (HEB_STD[ch] == null) continue;
            letters.push({
                letter: ch,
                standard: HEB_STD[ch],
                ordinal: HEB_ORD[ch],
                reduced: HEB_RED[ch]
            });
        }
        return letters;
    }

    function greekLetters(text) {
        const letters = [];
        const clean = String(text || '')
            .replace(/\s*\([^)]+\)/g, '')
            .normalize('NFD');
        for (const raw of clean) {
            let ch = raw;
            if (ch === IOTA_SUB) ch = 'ι';
            if (/[\u0300-\u0344\u0346-\u036f]/.test(ch)) continue;
            ch = ch.toLowerCase();
            if (GRK_STD[ch] == null) continue;
            letters.push({
                letter: ch,
                standard: GRK_STD[ch],
                ordinal: GRK_ORD[ch],
                reduced: digitalRoot(GRK_STD[ch])
            });
        }
        return letters;
    }

    function letterAudit(text, lang) {
        return lang === 'Hebrew' ? hebrewLetters(text) : greekLetters(text);
    }

    function isSectionMarkerCell(cell) {
        const text = textOf(cell, '.original');
        return text === 'פ' || text === 'ס';
    }

    function cellsForAnalysis() {
        const all = Array.from(interlinear.querySelectorAll('.word-cell'));
        const selected = all.filter(c => c.classList.contains('selected'));
        const source = selected.length ? selected : all;
        const cells = source.filter(c => !isSectionMarkerCell(c) && !c.classList.contains('cell-absent'));
        return { all, selected, cells, usingSelection: selected.length > 0 };
    }

    function wordFromCell(cell) {
        const id = cell.dataset.wordId || '';
        const d = WORD_DATA[id] || {};
        const lang = d.lang || (cell.querySelector('.original.heb') ? 'Hebrew' : 'Greek');
        const original = textOf(cell, '.original');
        const translit = textOf(cell, '.translit');
        const english = textOf(cell, '.english');
        const strongsEl = cell.querySelector('.strongs');
        const strongs = strongsEl ? (strongsEl.dataset.strongs || strongsEl.textContent.trim()) : '';
        const grammar = textOf(cell, '.grammar');
        const letters = letterAudit(original, lang);
        return {
            position: parseInt(cell.dataset.pos || d.position || '0', 10) || 0,
            verse: parseInt(cell.dataset.verseNum || '0', 10) || 0,
            lang,
            original,
            translit,
            english,
            strongs,
            grammar,
            lemma: d.lemma || '',
            values: {
                standard: intAttr(cell, 'gemStd'),
                ordinal: intAttr(cell, 'gemOrd'),
                reduced: intAttr(cell, 'gemRed')
            },
            letters
        };
    }

    function buildSection() {
        const state = cellsForAnalysis();
        const words = state.cells.map(wordFromCell);
        const totals = words.reduce((acc, word) => {
            acc.standard += word.values.standard;
            acc.ordinal += word.values.ordinal;
            acc.reduced += word.values.reduced;
            acc.letters += word.letters.length;
            return acc;
        }, { standard: 0, ordinal: 0, reduced: 0, letters: 0 });

        return {
            ref: studyPanel.dataset.ref || (typeof VERSE_REF !== 'undefined' ? VERSE_REF : ''),
            edition: studyPanel.dataset.edition || interlinear.dataset.edition || '',
            scope: state.usingSelection ? 'Selected section' : 'Whole verse',
            usingSelection: state.usingSelection,
            selectedCount: state.selected.length,
            wordCount: words.length,
            totals,
            original: words.map(w => w.original).filter(Boolean).join(' '),
            meaning: words.map(w => w.english).filter(Boolean).join(' / '),
            words
        };
    }

    function renderSummary(section) {
        if (!summaryEl) return;
        const cards = [
            ['Words', section.wordCount, section.totals.letters + ' letters'],
            ['Standard', section.totals.standard, valueNote(section.totals.standard)],
            ['Ordinal', section.totals.ordinal, valueNote(section.totals.ordinal)],
            ['Reduced', section.totals.reduced, valueNote(section.totals.reduced)]
        ];
        summaryEl.innerHTML = cards.map(([label, value, note]) => (
            '<div class="metric-card">' +
                '<span>' + esc(label) + '</span>' +
                '<strong>' + esc(value) + '</strong>' +
                '<small>' + esc(note) + '</small>' +
            '</div>'
        )).join('');
    }

    function renderWords(section) {
        if (!wordListEl) return;
        wordListEl.innerHTML = section.words.map(word => {
            const letterHtml = word.letters.map(letter => (
                '<span class="letter-chip">' +
                    '<b>' + esc(letter.letter) + '</b>' +
                    '<span>S ' + esc(letter.standard) + '</span>' +
                    '<span>O ' + esc(letter.ordinal) + '</span>' +
                    '<span>R ' + esc(letter.reduced) + '</span>' +
                '</span>'
            )).join('');
            const meta = [
                'Std ' + word.values.standard,
                'Ord ' + word.values.ordinal,
                'Red ' + word.values.reduced,
                word.strongs,
                word.grammar
            ].filter(Boolean).join(' · ');
            return (
                '<article class="analysis-word-card">' +
                    '<div class="analysis-word-head">' +
                        '<strong class="' + (word.lang === 'Hebrew' ? 'heb' : 'grk') + '">' + esc(word.original) + '</strong>' +
                        '<span>' + esc(word.english || word.translit || word.lemma) + '</span>' +
                    '</div>' +
                    '<div class="analysis-word-meta">' + esc(meta) + '</div>' +
                    '<div class="letter-strip">' + letterHtml + '</div>' +
                '</article>'
            );
        }).join('');
    }

    function renderDetail(section) {
        if (!detailEl || !detailTitleEl || !detailBodyEl) return;
        if (section.selectedCount !== 1 || section.words.length !== 1) {
            detailEl.classList.remove('shown');
            return;
        }
        const word = section.words[0];
        detailTitleEl.textContent = word.original;
        const letters = word.letters.map(l => (
            '<span class="letter-chip">' +
                '<b>' + esc(l.letter) + '</b>' +
                '<span>S ' + esc(l.standard) + '</span>' +
                '<span>O ' + esc(l.ordinal) + '</span>' +
                '<span>R ' + esc(l.reduced) + '</span>' +
            '</span>'
        )).join('');
        detailBodyEl.innerHTML =
            '<div class="wd-row"><span class="k">Meaning</span>' + esc(word.english || word.lemma || '') + '</div>' +
            '<div class="wd-row"><span class="k">Translit</span>' + esc(word.translit) + '</div>' +
            '<div class="wd-row"><span class="k">Strong\'s</span>' + esc(word.strongs) + '</div>' +
            '<div class="wd-row"><span class="k">Grammar</span>' + esc(word.grammar) + '</div>' +
            '<div class="wd-row"><span class="k">Values</span>Standard ' + esc(word.values.standard) +
                ' · Ordinal ' + esc(word.values.ordinal) + ' · Reduced ' + esc(word.values.reduced) + '</div>' +
            '<div class="wd-row"><span class="k">Letters</span><div class="letter-strip">' + letters + '</div></div>';
        detailEl.classList.add('shown');
    }

    function rebuild() {
        const section = buildSection();
        if (scopeEl) scopeEl.textContent = section.scope;
        if (chipEl) chipEl.textContent = section.usingSelection ? 'Selected' : 'Live';
        if (originalEl) originalEl.textContent = section.original;
        if (meaningEl) meaningEl.textContent = section.meaning;
        renderSummary(section);
        renderWords(section);
        renderDetail(section);
        return section;
    }

    function csvEscape(value) {
        const s = String(value ?? '');
        return '"' + s.replace(/"/g, '""') + '"';
    }

    function exportPayload() {
        const section = buildSection();
        return {
            reference: section.ref,
            edition: section.edition,
            scope: section.scope,
            counts: {
                words: section.wordCount,
                letters: section.totals.letters
            },
            values: {
                standard: section.totals.standard,
                standard_factorization: formatFactorsPlain(section.totals.standard),
                standard_prime_index: primeIndex(section.totals.standard),
                ordinal: section.totals.ordinal,
                ordinal_factorization: formatFactorsPlain(section.totals.ordinal),
                ordinal_prime_index: primeIndex(section.totals.ordinal),
                reduced: section.totals.reduced,
                reduced_factorization: formatFactorsPlain(section.totals.reduced),
                reduced_prime_index: primeIndex(section.totals.reduced)
            },
            original: section.original,
            meaning: section.meaning,
            words: section.words
        };
    }

    function asText(payload) {
        const lines = [
            payload.reference + ' (' + payload.edition + ')',
            payload.scope,
            '',
            'Original: ' + payload.original,
            'Meaning: ' + payload.meaning,
            '',
            'Words: ' + payload.counts.words,
            'Letters: ' + payload.counts.letters,
            'Standard: ' + payload.values.standard + ' | factors: ' + payload.values.standard_factorization + ' | prime index: ' + (payload.values.standard_prime_index || 'not prime'),
            'Ordinal: ' + payload.values.ordinal + ' | factors: ' + payload.values.ordinal_factorization + ' | prime index: ' + (payload.values.ordinal_prime_index || 'not prime'),
            'Reduced: ' + payload.values.reduced + ' | factors: ' + payload.values.reduced_factorization + ' | prime index: ' + (payload.values.reduced_prime_index || 'not prime'),
            '',
            'Word audit:'
        ];
        payload.words.forEach(word => {
            lines.push('- ' + word.original + ' | ' + word.english + ' | Std ' + word.values.standard + ', Ord ' + word.values.ordinal + ', Red ' + word.values.reduced);
            lines.push('  Letters: ' + word.letters.map(l => l.letter + '(S' + l.standard + '/O' + l.ordinal + '/R' + l.reduced + ')').join(' '));
        });
        return lines.join('\n');
    }

    function asCsv(payload) {
        const rows = [[
            'reference', 'edition', 'scope', 'verse', 'position', 'original', 'transliteration',
            'meaning', 'strongs', 'grammar', 'standard', 'ordinal', 'reduced', 'letters'
        ]];
        payload.words.forEach(word => {
            rows.push([
                payload.reference,
                payload.edition,
                payload.scope,
                word.verse,
                word.position,
                word.original,
                word.translit,
                word.english,
                word.strongs,
                word.grammar,
                word.values.standard,
                word.values.ordinal,
                word.values.reduced,
                word.letters.map(l => l.letter + ':S' + l.standard + '/O' + l.ordinal + '/R' + l.reduced).join(' ')
            ]);
        });
        return rows.map(row => row.map(csvEscape).join(',')).join('\n');
    }

    function filename(ext) {
        const ref = (studyPanel.dataset.ref || 'bible-gematria').replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-|-$/g, '');
        return (ref || 'bible-gematria') + '-analysis.' + ext;
    }

    function download(name, mime, content) {
        const blob = new Blob([content], { type: mime });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 500);
    }

    function setStatus(text) {
        if (!exportStatus) return;
        exportStatus.textContent = text;
        setTimeout(() => {
            if (exportStatus.textContent === text) exportStatus.textContent = '';
        }, 2400);
    }

    function copyText(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(text);
        }
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
        return Promise.resolve();
    }

    document.querySelectorAll('[data-study-tab]').forEach(button => {
        button.addEventListener('click', () => {
            const tab = button.dataset.studyTab;
            if (tab !== 'audit' && detailEl) detailEl.classList.remove('shown');
            document.querySelectorAll('[data-study-tab]').forEach(b => b.classList.toggle('active', b === button));
            document.querySelectorAll('[data-study-panel]').forEach(panel => {
                const active = panel.dataset.studyPanel === tab;
                panel.classList.toggle('active', active);
                if (active) panel.removeAttribute('hidden');
                else panel.setAttribute('hidden', '');
            });
        });
    });

    document.querySelectorAll('[data-export]').forEach(button => {
        button.addEventListener('click', () => {
            const payload = exportPayload();
            const kind = button.dataset.export;
            if (kind === 'copy') {
                copyText(asText(payload)).then(() => setStatus('Copied'));
            } else if (kind === 'txt') {
                download(filename('txt'), 'text/plain;charset=utf-8', asText(payload));
                setStatus('TXT ready');
            } else if (kind === 'csv') {
                download(filename('csv'), 'text/csv;charset=utf-8', asCsv(payload));
                setStatus('CSV ready');
            } else if (kind === 'json') {
                download(filename('json'), 'application/json;charset=utf-8', JSON.stringify(payload, null, 2));
                setStatus('JSON ready');
            } else if (kind === 'pdf') {
                document.body.classList.add('print-study');
                window.print();
            }
        });
    });

    window.addEventListener('afterprint', () => document.body.classList.remove('print-study'));
    window.hideDetail = function () {
        if (detailEl) detailEl.classList.remove('shown');
    };
    window._analysisRebuild = rebuild;

    rebuild();
})();
