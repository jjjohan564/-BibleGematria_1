// grammar-tooltip.js — expand grammar tag abbreviations on hover for both
// Greek (Robinson morphology) and Hebrew (STEPBible TAHOT format).
// The .grammar div must carry data-lang="grk" or data-lang="heb".
(function () {
    const HOVER_DELAY_MS = 250;
    const HIDE_DELAY_MS  = 200;
    let showTimer = null;
    let hideTimer = null;

    // =========================================================================
    // Greek (Robinson morphology)
    // =========================================================================
    const GRK_POS = {
        N:'Noun', V:'Verb', T:'Definite Article', A:'Adjective',
        P:'Personal Pronoun', D:'Demonstrative Pronoun', R:'Relative Pronoun',
        I:'Interrogative Pronoun', X:'Indefinite Pronoun', F:'Reflexive Pronoun',
        S:'Possessive Pronoun', K:'Correlative Pronoun', C:'Reciprocal Pronoun',
        Q:'Correlative/Interrogative Pronoun',
        ADV:'Adverb', CONJ:'Conjunction', PREP:'Preposition',
        PRT:'Particle', INJ:'Interjection', COND:'Conditional',
        HEB:'Hebrew word', ARAM:'Aramaic word',
    };
    const GRK_INDECL = new Set(['ADV','CONJ','PREP','PRT','INJ','COND','HEB','ARAM']);
    const GRK_CASE   = {N:'Nominative',G:'Genitive',D:'Dative',A:'Accusative',V:'Vocative'};
    const GRK_NUM    = {S:'Singular',P:'Plural',D:'Dual'};
    const GRK_GENDER = {M:'Masculine',F:'Feminine',N:'Neuter'};
    const GRK_TENSE  = {P:'Present',I:'Imperfect',F:'Future',A:'Aorist',R:'Perfect',L:'Pluperfect',X:'Aorist (irreg.)'};
    const GRK_VOICE  = {A:'Active',M:'Middle',P:'Passive',E:'Mid./Pass.',D:'Middle Dep.',O:'Passive Dep.',N:'Mid./Pass. Dep.',Q:'Mid.Dep./Pass.'};
    const GRK_MOOD   = {I:'Indicative',S:'Subjunctive',O:'Optative',M:'Imperative',N:'Infinitive',P:'Participle'};
    const GRK_PERSON = {'1':'1st','2':'2nd','3':'3rd'};

    function expandGreekCode(code) {
        if (!code) return null;
        var segs = code.split('-');
        var pc   = segs[0];
        if (GRK_INDECL.has(pc)) {
            var neg = (pc === 'PRT' && segs[1] === 'N') ? ['Negative'] : [];
            return { pos: GRK_POS[pc], rows: neg.length ? [neg] : [] };
        }
        var pos = GRK_POS[pc];
        if (!pos) return null;
        if (pc === 'V') {
            var tvm = segs[1] || '';
            var is2 = tvm.charAt(0) === '2';
            if (is2) tvm = tvm.slice(1);
            var t = GRK_TENSE[tvm[0]], v = GRK_VOICE[tvm[1]], m = GRK_MOOD[tvm[2]];
            var r1 = [];
            if (is2) r1.push('2nd form');
            if (t) r1.push(t); if (v) r1.push(v); if (m) r1.push(m);
            var r2 = [], tail = segs[2] || '';
            if (tail) {
                if (m === 'Participle') {
                    if (GRK_CASE[tail[0]])  r2.push(GRK_CASE[tail[0]]);
                    if (GRK_NUM[tail[1]])   r2.push(GRK_NUM[tail[1]]);
                    if (GRK_GENDER[tail[2]])r2.push(GRK_GENDER[tail[2]]);
                } else if (m !== 'Infinitive') {
                    if (GRK_PERSON[tail[0]]) r2.push(GRK_PERSON[tail[0]] + ' Pers.');
                    if (GRK_NUM[tail[1]])    r2.push(GRK_NUM[tail[1]]);
                }
            }
            return { pos: pos, rows: [r1, r2].filter(function(r){return r.length;}) };
        }
        var cng = segs[1] || '', row = [];
        if (GRK_CASE[cng[0]])   row.push(GRK_CASE[cng[0]]);
        if (GRK_NUM[cng[1]])    row.push(GRK_NUM[cng[1]]);
        if (GRK_GENDER[cng[2]]) row.push(GRK_GENDER[cng[2]]);
        if (segs[2] === 'T') row.push('Title');
        if (segs[2] === 'P') row.push('Proper');
        return { pos: pos, rows: row.length ? [row] : [] };
    }

    function buildGreekHtml(text) {
        if (!text || !/^[A-Z0-9 +=\-]+$/.test(text)) return null;
        var parts   = text.split(' + ');
        var entries = [];
        parts.forEach(function(p) {
            var eq    = p.indexOf('=');
            var label = eq !== -1 ? p.slice(0, eq).trim() : null;
            var code  = eq !== -1 ? p.slice(eq + 1).trim() : p.trim();
            var exp   = expandGreekCode(code);
            if (exp) entries.push({ label: label, exp: exp });
        });
        return entries.length ? renderEntries(entries) : null;
    }

    // =========================================================================
    // Hebrew (STEPBible TAHOT — formatted output of format_hebrew_grammar())
    //
    // Formatted codes look like:
    //   V-Qal-Perf-3ms       Verb: stem · aspect · pgn
    //   N-ms / N-ms-c        Noun: gender+num [· Construct]
    //   N-pr-ms              Proper Noun: gender+num
    //   Adj-fs-c             Adjective: Fem Sing Construct
    //   Pro-p3ms             Pronoun: pgn
    //   Conj-w               Conjunction
    //   Prep-b               Preposition
    //   Art-h                Article
    //   Suf-h-p3ms           Suffix: pgn
    //   Neg / Adv / Acc …    Simple particles
    // Compound morphemes are joined by ' | '.
    // =========================================================================
    var HEB_POS = {
        'V':'Verb', 'N':'Noun', 'Adj':'Adjective', 'Pro':'Pronoun',
        'Conj':'Conjunction', 'Prep':'Preposition', 'Art':'Article',
        'Suf':'Suffix', 'Neg':'Negative particle', 'Adv':'Adverb',
        'Acc':'Direct-object marker', 'Inter':'Interrogative particle',
        'Rel':'Relative particle', 'Cond':'Conditional particle',
        'Excl':'Exclamation', 'DirObj':'Direct-object marker', 'Part':'Particle',
    };
    var HEB_ASPECT = {
        'Perf':'Perfect', 'ConsecPerf':'Consec. Perfect',
        'Imperf':'Imperfect', 'ConsecImperf':'Consec. Imperfect',
        'Cohort':'Cohortative', 'Juss':'Jussive', 'Imp':'Imperative',
        'Part':'Participle', 'PartPass':'Passive Participle',
        'InfAbs':'Inf. Absolute', 'InfCons':'Inf. Construct',
    };
    var HEB_STEM = { 'Hith':'Hithpael', 'QalPass':'Qal Passive', 'NifalPass':'Nifal Passive' };
    var HEB_PERSON = {'1':'1st','2':'2nd','3':'3rd'};
    var HEB_GENDER = {'m':'Masc','f':'Fem','c':'Common','b':'Both'};
    var HEB_NUM    = {'s':'Sing','p':'Plur','d':'Dual'};

    // Gender+number 2-char code: [mfcb][spd]
    function isGN(tok) { return /^[mfcb][spd]$/.test(tok); }

    // 3-char verb pgn like '3ms' → ['3rd','Masc','Sing']
    function expandVerbPgn(pgn) {
        var out = [];
        var p = HEB_PERSON[pgn[0]]; if (p) out.push(p);
        var g = HEB_GENDER[pgn[1]]; if (g) out.push(g);
        var n = HEB_NUM[pgn[2]];    if (n) out.push(n);
        return out;
    }

    // 4-char pronoun/suffix pgn like 'p3ms' → ['3rd','Masc','Sing']
    function expandPronPgn(pgn) {
        var out = [];
        var p = HEB_PERSON[pgn[1]]; if (p) out.push(p);
        var g = HEB_GENDER[pgn[2]]; if (g) out.push(g);
        var n = HEB_NUM[pgn[3]];    if (n) out.push(n);
        return out;
    }

    // Smart verb tail: finite [person][gender][number] e.g. '3ms'
    // vs participial [gender][number][state] e.g. 'mpa','msc','fsa'
    function expandVerbTail(tail) {
        if (!tail || tail.length < 2) return [];
        if ('123'.indexOf(tail[0]) !== -1) return expandVerbPgn(tail);
        var row = [];
        var g = HEB_GENDER[tail[0]]; if (g) row.push(g);
        var n = HEB_NUM[tail[1]];    if (n) row.push(n);
        if (tail[2] === 'c') row.push('Construct');
        return row;
    }

    function expandGN(gn) {
        var out = [];
        var g = HEB_GENDER[gn[0]]; if (g) out.push(g);
        var n = HEB_NUM[gn[1]];    if (n) out.push(n);
        return out;
    }

    function expandHebrewSegment(seg) {
        var parts = seg.split('-');
        var pk = parts[0];
        var pos = HEB_POS[pk];
        if (!pos) return null;

        // Simple indeclinable particles
        if (pk === 'Neg' || pk === 'Adv' || pk === 'Acc' || pk === 'Inter' ||
            pk === 'Rel' || pk === 'Cond' || pk === 'Excl' || pk === 'DirObj' || pk === 'Part') {
            return { pos: pos, rows: [] };
        }

        // Conjunction, Preposition, Article — just show POS (connecting letter non-essential)
        if (pk === 'Conj' || pk === 'Prep' || pk === 'Art') {
            return { pos: pos, rows: [] };
        }

        // Verb: V-Stem-Aspect[-tail]
        if (pk === 'V') {
            var stem   = HEB_STEM[parts[1]] || parts[1] || '';
            var aspect = HEB_ASPECT[parts[2]] || parts[2] || '';
            var r1 = [stem, aspect].filter(Boolean);
            var r2 = parts[3] ? expandVerbTail(parts[3]) : [];
            return { pos: pos, rows: [r1, r2].filter(function(r){return r.length;}) };
        }

        // Pronoun: Pro-pgn4 (like p3ms)
        if (pk === 'Pro') {
            var pgn = parts[1] || '';
            var row = (pgn.length === 4 && pgn[0] === 'p') ? expandPronPgn(pgn) :
                      (pgn.length === 3) ? expandVerbPgn(pgn) : [];
            return { pos: pos, rows: row.length ? [row] : [] };
        }

        // Suffix: Suf[-letter1][-pgn4]
        if (pk === 'Suf') {
            // parts[1] is either a 1-char letter or the pgn itself
            var pgnPart = null;
            if (parts.length >= 3 && parts[2].length === 4 && parts[2][0] === 'p') {
                pgnPart = parts[2];
            } else if (parts.length >= 2 && parts[1].length === 4 && parts[1][0] === 'p') {
                pgnPart = parts[1];
            }
            var sufRow = pgnPart ? expandPronPgn(pgnPart) : [];
            return { pos: pos, rows: sufRow.length ? [sufRow] : [] };
        }

        // Noun / Adjective: N/Adj[-pr|-gent]-gn2[-c]
        var details = [], isConstruct = false, gnPart = null;
        for (var i = 1; i < parts.length; i++) {
            var t = parts[i];
            if (t === 'pr')   { details.unshift('Proper');   continue; }
            if (t === 'gent') { details.unshift('Gentilic'); continue; }
            if (t === 'c' && !isGN(t)) { isConstruct = true; continue; }
            if (isGN(t)) { gnPart = t; continue; }
        }
        if (gnPart) expandGN(gnPart).forEach(function(x){ details.push(x); });
        if (isConstruct) details.push('Construct');
        return { pos: pos, rows: details.length ? [details] : [] };
    }

    function buildHebrewHtml(text) {
        if (!text) return null;
        var segs    = text.split(' | ');
        var entries = [];
        segs.forEach(function(seg) {
            var exp = expandHebrewSegment(seg.trim());
            if (exp) entries.push({ label: null, exp: exp });
        });
        return entries.length ? renderEntries(entries) : null;
    }

    // =========================================================================
    // Shared renderer
    // =========================================================================
    function esc(s) {
        return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    function renderEntries(entries) {
        var html = '';
        entries.forEach(function(r, i) {
            if (i > 0) html += '<div class="gt-divider"></div>';
            if (r.label) html += '<div class="gt-compound-label">' + esc(r.label) + '</div>';
            html += '<div class="gt-pos">' + esc(r.exp.pos) + '</div>';
            r.exp.rows.forEach(function(row) {
                if (!row.length) return;
                html += '<div class="gt-details">'
                    + row.map(function(d){ return '<span class="gt-detail">' + esc(d) + '</span>'; })
                         .join('<span class="gt-sep">\u00B7</span>')
                    + '</div>';
            });
        });
        return html || null;
    }

    function buildHtml(grammarEl) {
        var text = (grammarEl.textContent || '').trim();
        var lang = grammarEl.dataset.lang;
        if (!text) return null;
        if (lang === 'grk' || (!lang && /^[A-Z0-9 +=\-]+$/.test(text))) return buildGreekHtml(text);
        if (lang === 'heb' || (!lang && /[a-z]/.test(text)))              return buildHebrewHtml(text);
        return null;
    }

    // =========================================================================
    // Tooltip DOM + positioning
    // =========================================================================
    var tip = document.createElement('div');
    tip.className = 'grammar-tooltip';
    tip.setAttribute('hidden', '');
    document.body.appendChild(tip);

    function hide() { tip.setAttribute('hidden', ''); }

    function positionTooltip(el) {
        var rect = el.getBoundingClientRect();
        var margin = 8;
        tip.style.left = '0px'; tip.style.top = '0px';
        tip.removeAttribute('hidden');
        var tipW = tip.offsetWidth, tipH = tip.offsetHeight;
        var viewW = document.documentElement.clientWidth;
        var viewBot = window.scrollY + document.documentElement.clientHeight;
        var left = rect.left + window.scrollX;
        var top  = rect.bottom + window.scrollY + margin;
        if (left + tipW + margin > viewW + window.scrollX) left = viewW + window.scrollX - tipW - margin;
        if (left < margin) left = margin;
        if (top + tipH + margin > viewBot) top = rect.top + window.scrollY - tipH - margin;
        tip.style.left = left + 'px';
        tip.style.top  = top  + 'px';
    }

    function show(el) {
        var html = buildHtml(el);
        if (!html) return;
        tip.innerHTML = html;
        positionTooltip(el);
    }

    // =========================================================================
    // Event delegation
    // =========================================================================
    document.addEventListener('mouseover', function(ev) {
        var target = ev.target.closest('.word-cell .grammar');
        if (!target) return;
        if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
        if (showTimer) return;
        showTimer = setTimeout(function(){ showTimer = null; show(target); }, HOVER_DELAY_MS);
    });

    document.addEventListener('mouseout', function(ev) {
        if (!ev.target.closest('.word-cell .grammar')) return;
        if (showTimer) { clearTimeout(showTimer); showTimer = null; }
        if (hideTimer) clearTimeout(hideTimer);
        hideTimer = setTimeout(hide, HIDE_DELAY_MS);
    });

    tip.addEventListener('mouseenter', function() { if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; } });
    tip.addEventListener('mouseleave', function() { if (hideTimer) clearTimeout(hideTimer); hideTimer = setTimeout(hide, HIDE_DELAY_MS); });

    window.addEventListener('scroll', hide, { passive: true });
    window.addEventListener('resize', hide);
})();
