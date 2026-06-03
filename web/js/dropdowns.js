// dropdowns.js — chained book/chapter/verse dropdowns.
// Also keeps the "Show N verses" count dropdown in sync with the current
// chapter's verse count (max = number of verses in chapter).
// Repopulates the edition dropdown when the user selects a different book
// (OT Hebrew books get BHS+LXX; NT/LXX books get NA28+TR+LXX).
// Auto-submits the form when the user changes the Edition selection.
(function () {
    const selBook    = document.getElementById('sel-book');
    const selChapter = document.getElementById('sel-chapter');
    const selVerse   = document.getElementById('sel-verse');
    const selCount   = document.getElementById('sel-count');
    const selEdition = document.getElementById('sel-edition');
    if (!selBook || !selChapter || !selVerse) return;

    const OT_EDITIONS = [
        { code: 'BHS',        name: 'Biblia Hebraica Stuttgartensia' },
        { code: 'LXX-Rahlfs', label: 'LXX', name: 'Rahlfs LXX 1935' }
    ];
    const NT_EDITIONS = [
        { code: 'NA28',       name: 'Nestle-Aland 28th edition' },
        { code: 'TR',         name: 'Scrivener Textus Receptus 1894' },
        { code: 'LXX-Rahlfs', label: 'LXX', name: 'Rahlfs LXX 1935' }
    ];

    function populate(sel, items, resetTo) {
        sel.innerHTML = '';
        for (const v of items) {
            const opt = document.createElement('option');
            opt.value = v;
            opt.textContent = v;
            sel.appendChild(opt);
        }
        sel.value = resetTo && items.includes(resetTo) ? resetTo : items[0];
    }

    function populateCount(maxN) {
        if (!selCount) return;
        selCount.innerHTML = '';
        for (let i = 1; i <= maxN; i++) {
            const opt = document.createElement('option');
            opt.value = i;
            opt.textContent = i === 1 ? '1 verse' : i + ' verses';
            selCount.appendChild(opt);
        }
        selCount.value = '1';
        selCount.dataset.max = String(maxN);
    }

    // Repopulate the edition dropdown to match the currently-selected book's
    // tradition: Hebrew OT books get BHS + LXX-Rahlfs; everything else gets
    // NA28 + TR + LXX-Rahlfs. Preserves the current edition if it's valid
    // in the new set; otherwise resets to the first option.
    function syncEditionOptions() {
        if (!selEdition) return;
        const opt    = selBook.selectedOptions[0];
        const lang   = opt ? opt.dataset.lang : '';
        const isLxx  = opt ? opt.value.startsWith('Lxx') : false;
        // OT editions for Hebrew MT books and all LXX books (which are OT Greek).
        const editions = (lang === 'Hebrew' || isLxx) ? OT_EDITIONS : NT_EDITIONS;
        const current  = selEdition.value;
        selEdition.innerHTML = '';
        for (const ed of editions) {
            const o = document.createElement('option');
            o.value = ed.code;
            o.textContent = ed.label || ed.code;
            o.title = ed.name;
            selEdition.appendChild(o);
        }
        const codes = editions.map(e => e.code);
        selEdition.value = codes.includes(current) ? current : editions[0].code;
        selEdition.disabled = false;
    }

    selBook.addEventListener('change', function () {
        // Only sync edition options on pages that use dynamic edition lists
        // (i.e. not pages with data-static on the edition select).
        if (!selEdition || !selEdition.dataset.static) {
            syncEditionOptions();
        }
        // Navigate directly so chapter/verse always reset to 1:1.
        // Preserve any extra form fields (width, letters, etc.) from the
        // current form so page-specific params survive book changes.
        const form = this.closest('form');
        const params = new URLSearchParams();
        params.set('book',    this.value);
        params.set('chapter', '1');
        params.set('verse',   '1');
        if (selEdition) params.set('edition', selEdition.value);
        if (form) {
            const skip = new Set(['book', 'chapter', 'verse', 'edition', 'count']);
            for (const el of form.elements) {
                if (el.name && !skip.has(el.name)) params.set(el.name, el.value);
            }
        }
        window.location.href = '?' + params.toString();
    });

    selChapter.addEventListener('change', async function () {
        const book    = selBook.value;
        const chapter = this.value;
        // Relative URL — works whether the page is served at /bible/ or root.
        const verses  = await fetch(`api.php?api=verses&book=${encodeURIComponent(book)}&chapter=${chapter}`)
            .then(r => r.json()).catch(() => []);
        populate(selVerse, verses, null);
        populateCount(verses.length || 1);
        const form = selChapter.closest('form');
        if (form) form.submit();
    });

    selVerse.addEventListener('change', function () {
        if (selCount) selCount.value = '1';
        const form = selVerse.closest('form');
        if (form) form.submit();
    });

    if (selCount) {
        selCount.addEventListener('change', function () {
            const form = selCount.closest('form');
            if (form) form.submit();
        });
    }

    // Auto-submit when the user picks a new edition — no need to click Go.
    if (selEdition) {
        selEdition.addEventListener('change', function () {
            const form = this.closest('form');
            if (form) form.submit();
        });
    }
})();
