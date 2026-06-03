// options.js — display options panel (gear button) and font-size controls.
(function () {
    const KEY       = 'bible-display-opts-v2';
    const SIZE_KEY  = 'bible-display-sizes';
    const COLOR_KEY = 'bible-display-colors';

    const defaults = {
        'gem-std': true, 'gem-ord': true, 'gem-red': true,
        strongs: true, translit: true, english: true, grammar: true,
        'verse-original': true, 'verse-english': true,
        'verse-newlines': false,
        'full-width': false,
    };
    let opts = Object.assign({}, defaults);
    try {
        const saved = JSON.parse(localStorage.getItem(KEY) || 'null');
        if (saved && typeof saved === 'object') opts = Object.assign({}, defaults, saved);
    } catch (e) { /* ignore */ }

    const sizeDefaults = {
        'verse-orig-heb': 22, 'verse-orig-grk': 18, 'verse-eng': 16,
        'word-orig-heb': 26, 'word-orig-grk': 18,
        translit: 13, 'word-eng': 13, strongs: 12, grammar: 11, gematria: 12,
    };
    const cssVarMap = {
        'verse-orig-heb': '--fsz-verse-orig-heb', 'verse-orig-grk': '--fsz-verse-orig-grk',
        'verse-eng':      '--fsz-verse-eng',
        'word-orig-heb':  '--fsz-word-orig-heb',  'word-orig-grk':  '--fsz-word-orig-grk',
        translit:         '--fsz-translit',        'word-eng':       '--fsz-word-eng',
        strongs:          '--fsz-strongs',         grammar:          '--fsz-grammar',
        gematria:         '--fsz-gematria',
    };
    let sizes = Object.assign({}, sizeDefaults);
    try {
        const savedSizes = JSON.parse(localStorage.getItem(SIZE_KEY) || 'null');
        if (savedSizes && typeof savedSizes === 'object') sizes = Object.assign({}, sizeDefaults, savedSizes);
    } catch (e) { /* ignore */ }

    const colorDefaults = { gematria: '#1e40af' };
    const colorVarMap   = { gematria: '--gematria' };
    let colors = Object.assign({}, colorDefaults);
    try {
        const savedColors = JSON.parse(localStorage.getItem(COLOR_KEY) || 'null');
        if (savedColors && typeof savedColors === 'object') colors = Object.assign({}, colorDefaults, savedColors);
    } catch (e) { /* ignore */ }

    const interlinear = document.getElementById('interlinear');
    const panel       = document.getElementById('options-panel');
    const btn         = document.getElementById('gear-btn');
    const boxes       = panel ? panel.querySelectorAll('input[type=checkbox][data-opt]') : [];
    const sizeInputs  = panel ? panel.querySelectorAll('input[type=number][data-size]') : [];
    const colorInputs = panel ? panel.querySelectorAll('input[type=color][data-color]') : [];

    // Rebuild gematria text in every word cell based on current options.
    function updateGematria() {
        if (!interlinear) return;
        const keys = [
            ['gem-std', 'gemStd'],
            ['gem-ord', 'gemOrd'],
            ['gem-red', 'gemRed'],
        ];
        interlinear.querySelectorAll('.word-cell').forEach(cell => {
            const div = cell.querySelector('.gematria');
            if (!div) return;
            const parts = [];
            for (const [opt, attr] of keys) {
                if (opts[opt] && cell.dataset[attr]) {
                    const v = cell.dataset[attr];
                    if (opt === 'gem-std' && parseInt(v, 10) > 0) {
                        parts.push(`<span class="gem-value">${v}</span>`);
                    } else {
                        parts.push(v);
                    }
                }
            }
            div.innerHTML = parts.join(', ');
            const empty = parts.length === 0;
            div.style.visibility   = empty ? 'hidden' : '';
            div.style.height       = empty ? '0'      : '';
            div.style.marginBottom = empty ? '0'      : '';
        });
    }

    const assembled = document.querySelector('.assembled');

    function showSizeCtrl(sizeKey, visible) {
        const inp = panel && panel.querySelector(`input[data-size="${sizeKey}"]`);
        if (inp) inp.closest('.size-ctrl').style.display = visible ? '' : 'none';
    }

    function applyAll() {
        if (interlinear) {
            for (const key of ['strongs', 'translit', 'english', 'grammar']) {
                interlinear.classList.toggle('hide-' + key, !opts[key]);
            }
            updateGematria();
        }
        if (assembled) {
            assembled.classList.toggle('hide-verse-original', !opts['verse-original']);
            assembled.classList.toggle('hide-verse-english',  !opts['verse-english']);
            assembled.classList.toggle('verse-newlines',      !!opts['verse-newlines']);
        }
        if (interlinear) {
            interlinear.classList.toggle('verse-newlines', !!opts['verse-newlines']);
        }
        document.body.classList.toggle('full-width', !!opts['full-width']);
        showSizeCtrl('verse-orig-heb', opts['verse-original']);
        showSizeCtrl('verse-orig-grk', opts['verse-original']);
        showSizeCtrl('verse-eng',      opts['verse-english']);
        showSizeCtrl('translit',   opts['translit']);
        showSizeCtrl('word-eng',   opts['english']);
        showSizeCtrl('strongs',    opts['strongs']);
        showSizeCtrl('grammar',    opts['grammar']);
        showSizeCtrl('gematria',   opts['gem-std'] || opts['gem-ord'] || opts['gem-red']);
    }

    function applySizes() {
        for (const [key, varName] of Object.entries(cssVarMap)) {
            document.documentElement.style.setProperty(varName, sizes[key] + 'px');
        }
    }

    function applyColors() {
        for (const [key, varName] of Object.entries(colorVarMap)) {
            document.documentElement.style.setProperty(varName, colors[key]);
        }
    }

    // Wire up gear button FIRST so it works even if applyAll() below throws.
    if (btn && panel) {
        btn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            const open = panel.hasAttribute('hidden');
            if (open) {
                panel.removeAttribute('hidden');
                btn.setAttribute('aria-expanded', 'true');
                btn.classList.add('active');
            } else {
                panel.setAttribute('hidden', '');
                btn.setAttribute('aria-expanded', 'false');
                btn.classList.remove('active');
            }
        });
        document.addEventListener('click', (ev) => {
            if (panel.hasAttribute('hidden')) return;
            if (panel.contains(ev.target)) return;
            panel.setAttribute('hidden', '');
            btn.setAttribute('aria-expanded', 'false');
            btn.classList.remove('active');
        });
    }

    boxes.forEach(box => {
        box.checked = !!opts[box.dataset.opt];
        box.addEventListener('change', () => {
            opts[box.dataset.opt] = box.checked;
            try { localStorage.setItem(KEY, JSON.stringify(opts)); } catch (e) {}
            applyAll();
        });
    });

    sizeInputs.forEach(inp => {
        const key = inp.dataset.size;
        inp.value = sizes[key] ?? inp.value;
        inp.addEventListener('change', () => {
            const min = parseInt(inp.min, 10);
            const max = parseInt(inp.max, 10);
            const val = Math.max(min, Math.min(max, parseInt(inp.value, 10) || sizeDefaults[key]));
            inp.value = val;
            sizes[key] = val;
            try { localStorage.setItem(SIZE_KEY, JSON.stringify(sizes)); } catch (e) {}
            applySizes();
        });
    });

    colorInputs.forEach(inp => {
        const key = inp.dataset.color;
        inp.value = colors[key] ?? inp.value;
        inp.addEventListener('input', () => {
            colors[key] = inp.value;
            try { localStorage.setItem(COLOR_KEY, JSON.stringify(colors)); } catch (e) {}
            applyColors();
        });
    });

    window._updateGematria = updateGematria;

    const resetBtn = document.getElementById('opts-reset-btn');
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            // Reset all three stores to defaults
            opts   = Object.assign({}, defaults);
            sizes  = Object.assign({}, sizeDefaults);
            colors = Object.assign({}, colorDefaults);
            try { localStorage.removeItem(KEY);       } catch (e) {}
            try { localStorage.removeItem(SIZE_KEY);  } catch (e) {}
            try { localStorage.removeItem(COLOR_KEY); } catch (e) {}
            // Sync checkboxes
            boxes.forEach(box => { box.checked = !!opts[box.dataset.opt]; });
            // Sync size inputs
            sizeInputs.forEach(inp => { inp.value = sizes[inp.dataset.size] ?? inp.value; });
            // Sync color inputs
            colorInputs.forEach(inp => { inp.value = colors[inp.dataset.color] ?? inp.value; });
            applyAll();
            applySizes();
            applyColors();
        });
    }

    try { applyAll();    } catch (e) { console.error('applyAll error:', e); }
    try { applySizes();  } catch (e) { console.error('applySizes error:', e); }
    try { applyColors(); } catch (e) { console.error('applyColors error:', e); }
})();
