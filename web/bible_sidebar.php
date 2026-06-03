<?php
// Highlight the current page in the sidebar nav
$_bsCurrentPage = basename($_SERVER['PHP_SELF']);
function _bsActive(string $file): string {
    global $_bsCurrentPage;
    return basename($file) === $_bsCurrentPage ? ' class="active"' : '';
}
?>
<aside id="bible-sidebar" class="bible-sidebar">
  <div class="bible-sidebar-inner">
    <p class="bible-sidebar-title">Bible DB</p>
    <nav class="bible-sidebar-nav">
      <a href="index.php"<?= _bsActive('index.php') ?>>Bible Viewer</a>
      <?php if ($_bsCurrentPage === 'search.php'): ?>
      <a href="search.php" class="active">Search Results</a>
      <?php endif; ?>
      <a href="els.php"<?= _bsActive('els.php') ?>>ELS Grid</a>
      <a href="numbers.php"<?= _bsActive('numbers.php') ?>>Number Sequences</a>
      <a href="stats.php"<?= _bsActive('stats.php') ?>>Stats</a>
    </nav>
  </div>
</aside>

<div id="bible-sidebar-backdrop"></div>

<script>
(function () {
    'use strict';
    var sidebar  = document.getElementById('bible-sidebar');
    var toggle   = document.getElementById('sidebar-toggle');
    var backdrop = document.getElementById('bible-sidebar-backdrop');
    if (!sidebar || !toggle) return;

    var MOBILE = window.matchMedia('(max-width: 768px)');

    /* Restore desktop collapsed state */
    if (!MOBILE.matches && localStorage.getItem('bible-sidebar-collapsed') === '1') {
        sidebar.classList.add('collapsed');
        toggle.setAttribute('aria-expanded', 'false');
    }

    function openMobile() {
        sidebar.classList.add('open');
        backdrop.classList.add('visible');
        toggle.setAttribute('aria-expanded', 'true');
    }
    function closeMobile() {
        sidebar.classList.remove('open');
        backdrop.classList.remove('visible');
        toggle.setAttribute('aria-expanded', 'false');
    }
    function toggleDesktop() {
        var now = sidebar.classList.toggle('collapsed');
        toggle.setAttribute('aria-expanded', now ? 'false' : 'true');
        localStorage.setItem('bible-sidebar-collapsed', now ? '1' : '0');
    }

    toggle.addEventListener('click', function () {
        MOBILE.matches ? (sidebar.classList.contains('open') ? closeMobile() : openMobile())
                       : toggleDesktop();
    });

    backdrop.addEventListener('click', closeMobile);

    document.addEventListener('keydown', function (e) {
        if ((e.key === 'Escape' || e.keyCode === 27) && sidebar.classList.contains('open')) {
            closeMobile();
            toggle.focus();
        }
    });
}());
</script>
