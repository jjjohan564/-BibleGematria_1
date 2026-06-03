// search-trigger.js — keeps the search bar populated from three signals:
//
//  1. Word cell clicks  → Strong's mode (fills with H/G code, auto-detected).
//  2. Mouse-drag over the assembled ORIGINAL text → Phrase mode (Hebrew/Greek).
//  3. Mouse-drag over the assembled ENGLISH (KJV) text → Phrase mode (English).
//     Selection is expanded to whole-word boundaries — partial highlights
//     like "od created th" round out to "God created the".
//
// The bar is ALWAYS visible so the user can type directly. Mode + lang
// auto-detect from the input:
//   • Strong's code (H/G + digits)  → strongs mode, phrase checkbox hidden
//   • Everything else               → phrase checkbox visible; checked = phrase,
//                                     unchecked = text (AND-of-words)
(function () {
    'use strict';

    const interlinear = document.getElementById('interlinear');
    const searchBar   = document.getElementById('word-search-bar');
    if (!searchBar) return;

    const searchInput = document.getElementById('search-input');
    const searchBtn   = document.getElementById('search-btn');
    const searchClear = document.getElementById('search-clear');
    const phraseLabel = document.getElementById('search-phrase-label');
    const phraseCheck = document.getElementById('search-phrase');

    // Show the × button whenever the input is non-empty.
    function syncClearBtn() {
        if (searchClear) searchClear.hidden = !searchInput.value;
    }

    // Show the Phrase checkbox only when input is non-empty and not a Strong's code or gematria number.
    let isStrongs  = false;
    let isGematria = false;
    function syncPhraseLabel() {
        if (phraseLabel) phraseLabel.hidden = isStrongs || isGematria || !searchInput.value;
    }

    const el = document.getElementById('word-data');
    let DATA = {};
    try { if (el) DATA = JSON.parse(el.textContent); } catch (e) {}

    // ── Script / mode auto-detect ─────────────────────────────────────────────

    // Detected language for the eventual search-page query string. Empty =>
    // fall back to VERSE_LANG (the current verse's language). Set by
    // updateDetected() on every input change, and explicitly by the KJV
    // selection handler so a quick highlight + Enter doesn't need to wait.
    let detectedLang = '';

    function detectScript(text) {
        if (/[\u0590-\u05FF\uFB1D-\uFB4F]/.test(text)) return 'Hebrew';
        if (/[\u0370-\u03FF\u1F00-\u1FFF]/.test(text)) return 'Greek';
        if (/[A-Za-z]/.test(text))   return 'English';
        return '';
    }

    // Decide mode + lang from whatever is currently in the box.
    // Sets isStrongs and detectedLang; syncs UI via helpers.
    function updateDetected() {
        const v = searchInput.value.trim();
        if (!v) { detectedLang = ''; isStrongs = false; isGematria = false; syncPhraseLabel(); return; }

        // Strong's code: one or more H/G codes, comma-separated (e.g. "H430" or "H430, G3056").
        if (/^[HG]\d{1,5}[A-Za-z]?(,\s*[HG]\d{1,5}[A-Za-z]?)*$/i.test(v)) {
            isStrongs = true; isGematria = false;
            detectedLang = '';
            syncPhraseLabel();
            return;
        }

        // Pure positive integer → gematria search.
        if (/^\d+$/.test(v)) {
            isGematria = true; isStrongs = false;
            detectedLang = '';
            syncPhraseLabel();
            return;
        }

        isStrongs = false; isGematria = false;
        const script = detectScript(v);
        if (script) detectedLang = script;
        syncPhraseLabel();
    }

    // Return the active search mode for doSearch().
    function getMode() {
        if (isStrongs) return 'strongs';
        return (phraseCheck && phraseCheck.checked) ? 'phrase' : 'text';
    }

    searchInput.addEventListener('input', function () { updateDetected(); syncClearBtn(); });

    // ── Helpers ───────────────────────────────────────────────────────────────

    function extractStrongsCode(raw) {
        if (!raw) return '';
        let m = raw.match(/\{([HG]\d{3,5}[A-Za-z]?)\}/);
        if (m) return m[1];
        m = raw.match(/([HG]\d{3,5}[A-Za-z]?)/);
        return m ? m[1] : '';
    }

    // Expand the current window selection within `containerEl` so that any
    // partially-touched word becomes fully included, and return the plain-
    // text result with HTML tags / inline Strong's markup stripped out.
    // Letters, digits, marks and apostrophes count as "in a word"; anything
    // else is a word boundary.
    function expandSelectionToWords(containerEl) {
        const sel = window.getSelection();
        if (!sel || sel.rangeCount === 0) return '';
        const range = sel.getRangeAt(0);
        if (range.collapsed) return '';
        if (!containerEl.contains(range.commonAncestorContainer)) return '';

        const startOff = textOffsetInContainer(containerEl, range.startContainer, range.startOffset);
        const endOff   = textOffsetInContainer(containerEl, range.endContainer,   range.endOffset);
        if (endOff <= startOff) return '';

        const full = containerEl.textContent || '';
        const wordChar = /[\p{L}\p{M}\p{N}']/u;

        // Only expand outward if the selection's own first/last char is a
        // word char — i.e. a word was partially touched. A selection that
        // *starts* in whitespace doesn't drag the previous word in (and
        // mirror for the end). Otherwise highlighting " created " with
        // flanking spaces would unhelpfully sweep in "God" and "the".
        let s = startOff;
        if (wordChar.test(full[startOff] || '')) {
            while (s > 0 && wordChar.test(full[s - 1])) s--;
        }
        let e = endOff;
        if (wordChar.test(full[endOff - 1] || '')) {
            while (e < full.length && wordChar.test(full[e])) e++;
        }

        // Collapse any run of internal whitespace down to a single space.
        return full.slice(s, e).replace(/\s+/g, ' ').trim();
    }

    // Translate a (node, offsetInNode) selection boundary into a single
    // character offset against the container's flat text. Uses a throwaway
    // Range from the container's start to the boundary — its toString()
    // length equals the cumulative text seen so far, and the browser
    // handles all the element-boundary / nested-span cases correctly.
    function textOffsetInContainer(container, node, offsetInNode) {
        const r = document.createRange();
        r.setStart(container, 0);
        try { r.setEnd(node, offsetInNode); }
        catch (e) { return 0; }
        return r.toString().length;
    }

    // ── Word-cell selection (interlinear) ─────────────────────────────────────

    // Cell clicks always fill with the Strong's code (most precise for concordance).
    // Phrase / text mode is for typed or drag-selected input.
    function refreshFromCells() {
        if (!interlinear) return;
        const selected = interlinear.querySelectorAll('.word-cell.selected');
        if (selected.length === 0) {
            // Clear the box only if it was populated by a cell click (Strong's mode).
            if (isStrongs) {
                searchInput.value = '';
                updateDetected();
                syncClearBtn();
            }
            return;
        }

        const seen   = new Set();
        const values = [];
        selected.forEach(function (cell) {
            const strongsEl = cell.querySelector('.strongs[data-strongs]');
            const val = strongsEl ? strongsEl.dataset.strongs : '';
            if (val && !seen.has(val)) { seen.add(val); values.push(val); }
        });

        searchInput.value = values.join(', ');
        updateDetected();
        syncClearBtn();
    }

    // Exposed so word-selection.js can trigger a refresh after any selection change.
    window._refreshFromCells = refreshFromCells;

    // ── Phrase selection: assembled ORIGINAL (Hebrew / Greek) ─────────────────

    const assembledOrig = document.querySelector('.assembled .original');
    if (assembledOrig) {
        assembledOrig.addEventListener('mouseup', function () {
            const text = expandSelectionToWords(assembledOrig);
            if (!text) return;
            if (phraseCheck) phraseCheck.checked = true;
            searchInput.value = text;
            updateDetected();
            syncClearBtn();
            searchInput.select();
        });
    }

    // ── Phrase selection: assembled ENGLISH (KJV) ─────────────────────────────
    // Expand the highlight to whole words, populate the box, and set the
    // phrase checkbox so it routes to bible_kjv as an exact phrase.
    const assembledEng = document.querySelector('.assembled .english');
    if (assembledEng) {
        assembledEng.addEventListener('mouseup', function () {
            // Defer so the browser finalises the selection first.
            setTimeout(function () {
                const phrase = expandSelectionToWords(assembledEng);
                if (!phrase) return;
                if (phraseCheck) phraseCheck.checked = true;
                searchInput.value = phrase;
                detectedLang      = 'English';
                syncClearBtn();
                syncPhraseLabel();
                searchInput.focus();
                searchInput.select();
            }, 0);
        });
    }

    // ── Verse-reference detection ──────────────────────────────────────────────
    // Recognised book-name keys (lowercase, no spaces) — mirrors PHP BOOK_ALIASES.
    // Checked first in doSearch() so "Jhn 3:16" or "Psalm 23" navigates to the verse.
    const BOOK_PREFIXES = new Set([
        // OT abbreviations + full names
        'gen','genesis','exo','exod','exodus','lev','leviticus','num','numbers',
        'deu','deut','deuteronomy','jos','josh','joshua','jdg','judg','judges',
        'rut','ruth','1sa','1sam','1samuel','2sa','2sam','2samuel',
        '1ki','1kgs','1kings','2ki','2kgs','2kings',
        '1ch','1chr','1chron','1chronicles','2ch','2chr','2chron','2chronicles',
        'ezr','ezra','neh','nehemiah','est','esth','esther','job',
        'psa','ps','psalm','psalms','pro','prov','proverbs',
        'ecc','eccl','ecclesiastes','sng','song','songofsolomon','songofsongs',
        'isa','isaiah','jer','jeremiah','lam','lamentations',
        'ezk','ezek','ezekiel','dan','daniel','hos','hosea',
        'jol','joel','amo','amos','oba','obad','obadiah','jon','jonah',
        'mic','micah','nam','nah','nahum','hab','habakkuk',
        'zep','zeph','zephaniah','hag','haggai','zec','zech','zechariah','mal','malachi',
        // NT abbreviations + full names
        'mat','matt','matthew','mrk','mar','mk','mark','luk','lk','luke',
        'jhn','jn','joh','john','act','acts','rom','romans',
        '1co','1cor','1corinthians','2co','2cor','2corinthians',
        'gal','galatians','eph','ephesians','php','phil','philippians',
        'col','colossians','1th','1thes','1thess','1thessalonians',
        '2th','2thes','2thess','2thessalonians','1ti','1tim','1timothy',
        '2ti','2tim','2timothy','tit','titus','phm','phlm','philemon',
        'heb','hebrews','jas','jam','james',
        '1pe','1pet','1peter','2pe','2pet','2peter',
        '1jn','1jo','1john','2jn','2jo','2john','3jn','3jo','3john',
        'jud','jude','rev','revelation','revelations'
    ]);

    // Try to interpret q as a verse reference. If it matches a known book name
    // + chapter (+ optional verse), navigate to index.php?ref=… and return true.
    // Otherwise return false so doSearch() falls through to regular search.
    function tryNavigateRef(q) {
        // Full ref: "Book Ch:V", "Book Ch.V", "Book Ch V"  (e.g. "Jhn 3:16")
        let m = q.match(/^([1-3]?\s*[A-Za-z]+\.?)\s+(\d+)\s*[:. ]\s*(\d+)$/i);
        if (m) {
            const key = m[1].replace(/\s+/g, '').toLowerCase();
            if (BOOK_PREFIXES.has(key)) {
                window.location.href = 'index.php?ref=' + encodeURIComponent(q);
                return true;
            }
        }
        // Chapter-only: "Book Ch"  (e.g. "Psalm 23", "Jhn 3") → PHP defaults to verse 1
        m = q.match(/^([1-3]?\s*[A-Za-z]+\.?)\s+(\d+)$/i);
        if (m) {
            const key = m[1].replace(/\s+/g, '').toLowerCase();
            if (BOOK_PREFIXES.has(key)) {
                window.location.href = 'index.php?ref=' + encodeURIComponent(q);
                return true;
            }
        }
        return false;
    }

    // ── Search navigation ─────────────────────────────────────────────────────

    function doSearch() {
        const q = searchInput.value.trim();
        if (!q) return;
        // Pure integer → gematria search.
        if (/^\d+$/.test(q) && parseInt(q, 10) > 0) {
            window.location.href = 'search.php?mode=gematria&standard=' + parseInt(q, 10);
            return;
        }
        // Verse-reference check takes priority (e.g. "Jhn 3:16", "Psalm 23").
        if (tryNavigateRef(q)) return;
        // Re-derive lang/mode from the current input in case state was lost
        // (e.g. browser back-navigation resets the JS closure while the
        // browser restores form values independently).
        updateDetected();
        // Detected (from input or selection) wins; fall back to the verse's
        // own language for the cell-click cases that didn't go through input.
        const lang = detectedLang ||
                     (typeof VERSE_LANG !== 'undefined' ? VERSE_LANG : '');
        window.location.href = 'search.php'
            + '?q='    + encodeURIComponent(q)
            + '&mode=' + encodeURIComponent(getMode())
            + '&lang=' + encodeURIComponent(lang);
    }
    searchBtn.addEventListener('click', doSearch);
    if (searchClear) {
        searchClear.addEventListener('click', function () {
            searchInput.value = '';
            detectedLang = '';
            isStrongs = false; isGematria = false;
            syncClearBtn();
            syncPhraseLabel();
            searchInput.focus();
        });
    }
    searchInput.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter') doSearch();
    });

    // ── Escape: clear the input but keep the bar visible ──────────────────────
    document.addEventListener('keydown', function (ev) {
        if (ev.key !== 'Escape') return;
        if (document.activeElement === searchInput) {
            searchInput.value = '';
            detectedLang = '';
            isStrongs = false; isGematria = false;
            syncClearBtn();
            syncPhraseLabel();
        }
    });

    // Gematria × clear also clears cell selection → re-evaluate input.
    const clearBtn = document.getElementById('gem-clear');
    if (clearBtn) clearBtn.addEventListener('click', function () {
        setTimeout(refreshFromCells, 0);
    });

    // Sync on load — defer so browser-restored form values are in place, then
    // call updateDetected() to correctly set isStrongs before syncing the UI.
    setTimeout(function () { updateDetected(); syncClearBtn(); }, 0);
})();
