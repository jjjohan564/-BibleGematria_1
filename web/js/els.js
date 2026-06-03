// els.js — ELS grid page interactivity.
// Width preset quick-picks · mobile book abbreviation · color highlighting · gematria sums.
(function () {
    'use strict';

    // ── Width presets ────────────────────────────────────────────────────
    const widthInput = document.getElementById('els-width');
    const presets    = document.querySelectorAll('.els-preset');

    if (!widthInput) return;

    function syncPresets() {
        const cur = widthInput.value;
        presets.forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.width === cur);
        });
    }
    presets.forEach(function (btn) {
        btn.addEventListener('click', function () {
            widthInput.value = this.dataset.width;
            syncPresets();
        });
    });
    widthInput.addEventListener('input', syncPresets);
    syncPresets();

    // ── Mobile book abbreviation ─────────────────────────────────────────
    var selBook = document.getElementById('sel-book');
    if (selBook) {
        var mq = window.matchMedia('(max-width: 768px)');
        function applyBookNames(e) {
            var abbr = e.matches;
            for (var i = 0; i < selBook.options.length; i++) {
                var opt = selBook.options[i];
                opt.textContent = abbr ? opt.dataset.abbr : opt.dataset.full;
            }
        }
        applyBookNames(mq);
        mq.addEventListener('change', applyBookNames);
    }

    // ── Color picker & cell highlighting ─────────────────────────────────
    const grid      = document.querySelector('.els-grid');
    const palette   = document.getElementById('els-palette');
    const colorPick = document.getElementById('els-color-pick');
    const clearBtn  = document.getElementById('els-clear-all');
    const sumsDiv   = document.getElementById('els-sums');
    if (!grid || !palette) return;

    const cells = Array.from(grid.querySelectorAll('.els-cell'));

    var currentColor = '#3b82f6'; // active paint colour
    var dragOp       = null;      // 'paint' | 'erase' | null (active drag operation)

    // Convert a 6-digit hex colour to an "r,g,b" string for rgba().
    function hexRgb(hex) {
        var m = hex.match(/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
        return m ? parseInt(m[1],16)+','+parseInt(m[2],16)+','+parseInt(m[3],16) : '59,130,246';
    }

    // Apply the current colour to a cell.
    function paintCell(cell) {
        cell.style.background   = 'rgba(' + hexRgb(currentColor) + ',0.30)';
        cell.style.borderColor  = currentColor;
        cell.style.outline      = '1px solid ' + currentColor;
        cell.dataset.cc         = currentColor;
        cell.classList.add('els-hi');
    }

    // Remove any highlight from a cell.
    function eraseCell(cell) {
        cell.style.background  = '';
        cell.style.borderColor = '';
        cell.style.outline     = '';
        delete cell.dataset.cc;
        cell.classList.remove('els-hi');
    }

    // ── Palette: preset swatches + custom colour input ────────────────────
    function setColor(color) {
        currentColor = color;
        if (colorPick) colorPick.value = color;
        palette.querySelectorAll('.els-swatch').forEach(function (sw) {
            sw.classList.toggle('els-swatch-active', sw.dataset.color === color);
        });
    }

    palette.querySelectorAll('.els-swatch').forEach(function (sw) {
        sw.addEventListener('click', function () { setColor(this.dataset.color); });
    });

    if (colorPick) {
        colorPick.addEventListener('input', function () {
            currentColor = this.value;
            palette.querySelectorAll('.els-swatch').forEach(function (sw) {
                sw.classList.remove('els-swatch-active');
            });
        });
    }

    setColor(currentColor); // activate first swatch on load

    // ── Font-size slider ──────────────────────────────────────────────────
    const fsInput = document.getElementById('els-font-size');
    const fsOut   = document.getElementById('els-font-size-val');
    const FS_KEY  = 'els-font-size';

    function applyFontSize(px) {
        grid.style.fontSize = px + 'px';
        if (fsOut) fsOut.textContent = px + 'px';
        if (fsInput) fsInput.value = px;
    }

    if (fsInput) {
        var savedFs = parseInt(localStorage.getItem(FS_KEY), 10);
        applyFontSize(savedFs > 0 ? savedFs : parseInt(fsInput.value, 10));
        fsInput.addEventListener('input', function () {
            var px = parseInt(this.value, 10);
            applyFontSize(px);
            localStorage.setItem(FS_KEY, px);
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', function () {
            cells.forEach(eraseCell);
            updateSums();
            updateUrl();
        });
    }

    // ── Cell interaction: left-drag = paint/toggle · right-drag = erase ──
    grid.addEventListener('mousedown', function (e) {
        if (!e.target.classList.contains('els-cell')) return;
        if (e.button === 2) {
            // Right button → always erase.
            dragOp = 'erase';
            eraseCell(e.target);
        } else if (e.button === 0) {
            // Left button → toggle: erase if already this colour, else paint.
            if (e.target.dataset.cc === currentColor) {
                dragOp = 'erase';
                eraseCell(e.target);
            } else {
                dragOp = 'paint';
                paintCell(e.target);
            }
        }
        updateSums();
        updateUrl();
        e.preventDefault(); // prevent accidental text selection
    });

    grid.addEventListener('mouseover', function (e) {
        if (!dragOp || !(e.buttons & (1|2))) return; // no button held
        if (!e.target.classList.contains('els-cell')) return;
        if (dragOp === 'paint') paintCell(e.target);
        else eraseCell(e.target);
        updateSums();
        updateUrl();
    });

    document.addEventListener('mouseup', function () { dragOp = null; });

    // Suppress the browser context menu inside the grid.
    grid.addEventListener('contextmenu', function (e) { e.preventDefault(); });

    // ── Gematria / isopsephy / ordinal sums ──────────────────────────────
    function updateSums() {
        if (!sumsDiv) return;
        // Collect {sum, count} per colour.
        var byColor = {};
        cells.forEach(function (cell) {
            var cc = cell.dataset.cc;
            if (!cc) return;
            var val = parseInt(cell.dataset.val, 10) || 0;
            if (!byColor[cc]) byColor[cc] = { sum: 0, count: 0 };
            byColor[cc].sum   += val;
            byColor[cc].count += 1;
        });

        var colors = Object.keys(byColor);
        if (colors.length === 0) {
            sumsDiv.innerHTML = '';
            return;
        }

        var html = '<span class="els-sums-label">Sums\u00a0\u2014</span>';
        colors.forEach(function (color) {
            var d = byColor[color];
            html += '<span class="els-sum-badge">'
                  + '<span class="els-sum-dot" style="background:' + color + '"></span>'
                  + '<strong>' + d.sum.toLocaleString() + '</strong>'
                  + '<span class="els-sum-count">\u00d7' + d.count + '</span>'
                  + '</span>';
        });
        sumsDiv.innerHTML = html;
    }

    // ── URL deep-linking: encode/restore cell highlights in ?hl= ─────────
    //   Format: "idx:rrggbb,idx:rrggbb,..."  (# stripped from hex)

    function hlToString() {
        var pairs = [];
        cells.forEach(function (cell) {
            if (cell.dataset.cc) {
                pairs.push(cell.dataset.idx + ':' + cell.dataset.cc.replace('#', ''));
            }
        });
        return pairs.join(',');
    }

    function hlFromString(str) {
        if (!str) return;
        str.split(',').forEach(function (pair) {
            var parts = pair.split(':');
            if (parts.length < 2) return;
            var idx   = parseInt(parts[0], 10);
            var color = '#' + parts[1];
            var cell  = grid.querySelector('.els-cell[data-idx="' + idx + '"]');
            if (!cell) return;
            var prev = currentColor;
            currentColor = color;
            paintCell(cell);
            currentColor = prev;
        });
    }

    function updateUrl() {
        var params = new URLSearchParams(location.search);
        var hl = hlToString();
        if (hl) params.set('hl', hl); else params.delete('hl');
        history.replaceState(null, '', location.pathname + '?' + params.toString());
        var hlInput = document.getElementById('els-hl-input');
        if (hlInput) hlInput.value = hl;
    }

    // Restore highlights from URL on page load.
    (function () {
        var initHl = new URLSearchParams(location.search).get('hl');
        if (initHl) { hlFromString(initHl); updateSums(); }
    }());

    // ── Named presets (saved in localStorage) ────────────────────────────
    var PRESETS_KEY   = 'els-named-presets';
    var selPreset     = document.getElementById('els-preset-select');
    var btnPresetLoad = document.getElementById('els-preset-load');
    var btnPresetDel  = document.getElementById('els-preset-del');
    var nameInput     = document.getElementById('els-preset-name');
    var btnPresetSave = document.getElementById('els-preset-save');

    function getPresets()  { return JSON.parse(localStorage.getItem(PRESETS_KEY) || '[]'); }
    function putPresets(a) { localStorage.setItem(PRESETS_KEY, JSON.stringify(a)); }

    function renderPresetList() {
        if (!selPreset) return;
        var saved = getPresets();
        selPreset.innerHTML = '<option value="">— saved presets —</option>';
        saved.forEach(function (p, i) {
            var opt = document.createElement('option');
            opt.value = i;
            opt.textContent = p.name;
            selPreset.appendChild(opt);
        });
    }

    if (btnPresetSave) {
        btnPresetSave.addEventListener('click', function () {
            var name = nameInput ? nameInput.value.trim() : '';
            if (!name) { if (nameInput) nameInput.focus(); return; }
            updateUrl(); // make sure ?hl is current
            var saved = getPresets();
            var idx   = saved.findIndex(function (p) { return p.name === name; });
            var entry = { name: name, url: location.href };
            if (idx >= 0) saved[idx] = entry; else saved.push(entry);
            putPresets(saved);
            renderPresetList();
            // Select the just-saved entry.
            if (selPreset) {
                for (var i = 0; i < selPreset.options.length; i++) {
                    if (selPreset.options[i].textContent === name) {
                        selPreset.selectedIndex = i; break;
                    }
                }
            }
        });
    }

    if (btnPresetLoad) {
        btnPresetLoad.addEventListener('click', function () {
            var idx = parseInt(selPreset ? selPreset.value : '', 10);
            if (isNaN(idx)) return;
            var saved = getPresets();
            if (saved[idx]) location.href = saved[idx].url;
        });
    }

    if (btnPresetDel) {
        btnPresetDel.addEventListener('click', function () {
            var idx = parseInt(selPreset ? selPreset.value : '', 10);
            if (isNaN(idx)) return;
            var saved = getPresets();
            saved.splice(idx, 1);
            putPresets(saved);
            renderPresetList();
        });
    }

    // Double-click on dropdown = instant load.
    if (selPreset) {
        selPreset.addEventListener('dblclick', function () {
            var idx = parseInt(this.value, 10);
            if (isNaN(idx)) return;
            var saved = getPresets();
            if (saved[idx]) location.href = saved[idx].url;
        });
    }

    renderPresetList();

})();
