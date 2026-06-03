<?php
require_once __DIR__ . '/helpers.php';
bible_render_layout_header();
?>

<html><head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="author" content="Richard Amiel McGough">
<title>Number Sequences — Bible Wheel</title>
<?php bible_render_layout_styles(); ?>
<style>
  main h1 { font-size: 1.4rem; margin-bottom: 4px; }
  .num-controls {
      display: flex; gap: 16px; align-items: center; flex-wrap: wrap;
      margin: 12px 0 8px;
  }
  .num-controls label { font-size: 13px; color: var(--muted); }
  .num-controls select {
      font-size: 13px; padding: 4px 8px;
      border: 1px solid var(--border); border-radius: 4px;
      background: var(--card); color: var(--fg);
  }
  .num-info { font-size: 12px; color: var(--muted); margin: 4px 0 12px; }
  /* Chip grid */
  .num-grid { display: flex; flex-wrap: wrap; gap: 5px; margin: 8px 0; }
  .num-chip {
      border: 1px solid var(--border); border-radius: 5px;
      padding: 4px 9px; text-align: center;
      background: var(--card); cursor: default;
      transition: border-color 0.12s, background 0.12s;
  }
  .num-chip:hover { background: var(--bg-alt); border-color: var(--accent); }
  .num-chip a {
      font-weight: 600; font-size: 13px;
      color: var(--accent); text-decoration: none;
      display: block; font-variant-numeric: tabular-nums;
  }
  .num-chip a:hover { text-decoration: underline; }
  .num-chip .chip-fac {
      font-size: 10px; color: #444;
      display: block; white-space: nowrap; line-height: 1.4;
  }
  .num-chip .chip-idx {
      font-size: 9px; color: #999;
      display: block; line-height: 1.2;
  }
</style>
</head>
<body>
<?php bible_render_layout_banner(); ?>
<div class="bible-layout">
<main class="bible-main">

<h1>Number Sequences</h1>

<div class="num-controls">
  <label for="seq-type">Sequence</label>
  <select id="seq-type">
    <option value="primes">Primes</option>
    <option value="composites">Composites</option>
    <option value="semiprimes">Semiprimes</option>
  </select>

  <label for="seq-limit">Show</label>
  <select id="seq-limit">
    <option value="100">First 100</option>
    <option value="500" selected>First 500</option>
    <option value="1000">First 1,000</option>
    <option value="99999">All (up to 10,000)</option>
  </select>
</div>

<p class="num-info" id="seq-info"></p>
<div class="num-grid" id="seq-grid"></div>

<script>
(function () {
    'use strict';

    /* ---- Sieve of Eratosthenes up to LIMIT ---- */
    var LIMIT = 10000;
    var notPrime = new Uint8Array(LIMIT + 1); /* 0 = prime */
    notPrime[0] = notPrime[1] = 1;
    for (var i = 2; i * i <= LIMIT; i++) {
        if (!notPrime[i]) {
            for (var j = i * i; j <= LIMIT; j += i) notPrime[j] = 1;
        }
    }
    function isPrime(n) { return n >= 2 && !notPrime[n]; }

    /* ---- Prime factorization ---- */
    function factorize(n) {
        var factors = [], d = n;
        for (var p = 2; p * p <= d; p++) {
            if (d % p === 0 && !notPrime[p]) {
                var e = 0;
                while (d % p === 0) { e++; d = Math.floor(d / p); }
                factors.push([p, e]);
            }
        }
        if (d > 1) factors.push([d, 1]);
        return factors;
    }

    function factorHTML(n) {
        if (isPrime(n)) return '<span style="font-style:italic;color:var(--muted)">prime</span>';
        return factorize(n).map(function (pe) {
            return pe[1] > 1 ? pe[0] + '<sup>' + pe[1] + '</sup>' : '' + pe[0];
        }).join(' &times; ');
    }

    /* ---- Semiprime: exactly 2 prime factors counted with multiplicity ---- */
    function isSemiprime(n) {
        if (n < 4) return false;
        var total = factorize(n).reduce(function (s, pe) { return s + pe[1]; }, 0);
        return total === 2;
    }

    /* ---- Build sequence ---- */
    function buildSequence(type, limit) {
        var result = [];
        for (var n = 2; n <= LIMIT && result.length < limit; n++) {
            if      (type === 'primes'      && isPrime(n))     result.push(n);
            else if (type === 'composites'  && !isPrime(n))    result.push(n);
            else if (type === 'semiprimes'  && isSemiprime(n)) result.push(n);
        }
        return result;
    }

    /* ---- Render ---- */
    var grid     = document.getElementById('seq-grid');
    var info     = document.getElementById('seq-info');
    var selType  = document.getElementById('seq-type');
    var selLimit = document.getElementById('seq-limit');

    function render() {
        var type  = selType.value;
        var limit = parseInt(selLimit.value, 10);
        var seq   = buildSequence(type, limit);
        var showFactors = (type !== 'primes');

        var html = '';
        for (var i = 0; i < seq.length; i++) {
            var v = seq[i];
            html += '<div class="num-chip">'
                + '<a href="search.php?mode=gematria&amp;standard=' + v + '">' + v + '</a>'
                + (showFactors ? '<span class="chip-fac">' + factorHTML(v) + '</span>' : '')
                + '<span class="chip-idx">' + (i + 1) + '</span>'
                + '</div>';
        }
        grid.innerHTML = html;

        var maxVal = seq.length ? seq[seq.length - 1] : 0;
        var capped = seq.length === limit ? ', limit reached' : '';
        info.textContent = seq.length.toLocaleString() + ' ' + type
            + ' \u2264 ' + maxVal.toLocaleString() + capped;
    }

    selType.addEventListener('change', render);
    selLimit.addEventListener('change', render);
    render();
}());
</script>

</main>
<?php require __DIR__ . '/bible_sidebar.php'; ?>
</div>
</body>
</html>
