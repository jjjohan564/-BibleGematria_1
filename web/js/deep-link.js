// deep-link.js — restore word selection from ?selected= URL param,
// and wire the "copy link" button in the gematria panel.
// Runs after all other modules so _gemRebuild / _refreshFromCells are wired up.
(function () {

    // ── 1. Restore selection from URL ────────────────────────────────────────
    var raw = new URLSearchParams(location.search).get('selected');
    if (raw) {
        var positions = raw.split(',').map(function (s) { return parseInt(s.trim(), 10); })
                           .filter(function (n) { return !isNaN(n) && n > 0; });
        var interlinear = document.getElementById('interlinear');
        if (interlinear && positions.length) {
            positions.forEach(function (pos) {
                var cell = interlinear.querySelector('.word-cell[data-pos="' + pos + '"]');
                if (cell) cell.classList.add('selected');
            });
            if (window._gemRebuild) window._gemRebuild();
            if (window._refreshFromCells) window._refreshFromCells();
        }
    }

    // ── 2. Deep-link copy button ──────────────────────────────────────────────
    var linkBtn     = document.getElementById('gem-link-btn');
    var interlinear = interlinear || document.getElementById('interlinear');
    if (!linkBtn || !interlinear) return;

    linkBtn.addEventListener('click', function () {
        // Collect positions of selected cells
        var selected = Array.from(interlinear.querySelectorAll('.word-cell.selected'));
        if (!selected.length) return;

        var positions = selected.map(function (c) { return c.dataset.pos; }).join(',');

        // Build URL: keep all existing params, force resolved edition, append selected raw
        var params = new URLSearchParams(location.search);
        params.set('edition', interlinear.dataset.edition || '');
        params.delete('selected');
        var qs = params.toString();
        var url = location.origin + location.pathname + '?' + (qs ? qs + '&' : '') + 'selected=' + positions;

        navigator.clipboard.writeText(url).then(function () {
            linkBtn.textContent = '✓ copied';
            linkBtn.classList.add('copied');
            setTimeout(function () {
                linkBtn.innerHTML = '&#128279; copy link';
                linkBtn.classList.remove('copied');
            }, 2000);
        });
    });

})();
