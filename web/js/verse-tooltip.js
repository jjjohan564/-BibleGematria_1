// verse-tooltip.js — hover a .verse-ref link to preview the KJV text.
// Uses event delegation so dynamically-inserted links are handled too.
(function () {
    const HOVER_DELAY_MS = 300;
    const HIDE_DELAY_MS  = 200;
    const cache = new Map(); // "book|ch|vs" -> text or null

    let showTimer  = null;
    let hideTimer  = null;
    let currentGen = 0;   // prevents stale fetch responses from showing

    // ── Tooltip element ────────────────────────────────────────────────────────
    const tip = document.createElement('div');
    tip.className = 'verse-tooltip';
    tip.setAttribute('hidden', '');
    document.body.appendChild(tip);

    function hide() {
        tip.setAttribute('hidden', '');
    }

    function positionTooltip(anchorEl) {
        const rect   = anchorEl.getBoundingClientRect();
        const margin = 8;

        // Pre-render hidden at origin to measure actual size.
        tip.style.left = '0px';
        tip.style.top  = '0px';
        tip.removeAttribute('hidden');

        const tipW    = tip.offsetWidth;
        const tipH    = tip.offsetHeight;
        const viewW   = document.documentElement.clientWidth;
        const viewBot = window.scrollY + document.documentElement.clientHeight;

        // Default: below the anchor, left-aligned.
        let left = rect.left + window.scrollX;
        let top  = rect.bottom + window.scrollY + margin;

        // Clamp horizontally.
        if (left + tipW + margin > viewW + window.scrollX) {
            left = viewW + window.scrollX - tipW - margin;
        }
        if (left < margin) left = margin;

        // Flip above if it would run off the bottom.
        if (top + tipH + margin > viewBot) {
            top = rect.top + window.scrollY - tipH - margin;
        }

        tip.style.left = left + 'px';
        tip.style.top  = top  + 'px';
    }

    function escapeHtml(s) {
        return String(s || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    async function show(anchorEl) {
        const gen     = ++currentGen;
        const book    = anchorEl.dataset.book;
        const chapter = anchorEl.dataset.chapter;
        const verse   = anchorEl.dataset.verse;
        const key     = book + '|' + chapter + '|' + verse;

        if (cache.has(key)) {
            const text = cache.get(key);
            tip.innerHTML = text
                ? '<span class="vt-ref">' + escapeHtml(book.replace(/([A-Z])/g, ' $1').trim())
                  + ' ' + chapter + ':' + verse + '</span>'
                  + escapeHtml(text)
                : '<span class="vt-miss">KJV text unavailable</span>';
            positionTooltip(anchorEl);
            return;
        }

        // Show loading state immediately.
        tip.innerHTML = '<span class="vt-loading">Loading\u2026</span>';
        positionTooltip(anchorEl);

        try {
            const r    = await fetch('search.php?api=kjv_verse'
                + '&book='    + encodeURIComponent(book)
                + '&chapter=' + encodeURIComponent(chapter)
                + '&verse='   + encodeURIComponent(verse));
            const data = r.ok ? await r.json() : null;
            const text = (data && data.text) ? String(data.text) : null;
            cache.set(key, text);
            // Only update if this response is still the current one and
            // the tooltip hasn't been hidden while the fetch was in flight.
            if (gen === currentGen && !tip.hasAttribute('hidden')) {
                tip.innerHTML = text
                    ? '<span class="vt-ref">' + escapeHtml(book.replace(/([A-Z])/g, ' $1').trim())
                      + ' ' + chapter + ':' + verse + '</span>'
                      + escapeHtml(text)
                    : '<span class="vt-miss">KJV text unavailable</span>';
                positionTooltip(anchorEl); // reposition with final size
            }
        } catch (e) {
            cache.set(key, null);
        }
    }

    // ── Event delegation ───────────────────────────────────────────────────────
    document.addEventListener('mouseover', function (ev) {
        const target = ev.target.closest('.verse-ref');
        if (!target) return;
        if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
        if (showTimer) return;
        showTimer = setTimeout(function () {
            showTimer = null;
            show(target);
        }, HOVER_DELAY_MS);
    });

    document.addEventListener('mouseout', function (ev) {
        const target = ev.target.closest('.verse-ref');
        if (!target) return;
        if (showTimer) { clearTimeout(showTimer); showTimer = null; }
        if (hideTimer) clearTimeout(hideTimer);
        hideTimer = setTimeout(hide, HIDE_DELAY_MS);
    });

    // Keep tooltip visible if the cursor moves onto it.
    tip.addEventListener('mouseenter', function () {
        if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
    });
    tip.addEventListener('mouseleave', function () {
        if (hideTimer) clearTimeout(hideTimer);
        hideTimer = setTimeout(hide, HIDE_DELAY_MS);
    });

    window.addEventListener('scroll', hide, { passive: true });
    window.addEventListener('resize', hide);
})();
