<?php
// Bible Viewer — page view statistics
header('Cache-Control: no-store, no-cache, must-revalidate');
header('Pragma: no-cache');
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/helpers.php';

// View counts are private per-instance — the api.php viewcount endpoint
// already returns 0/0 in remote mode. Stats follows the same policy: in
// remote API mode we render a friendly disabled-page rather than proxying
// verse_views.
if (should_use_remote_api()) {
    ?><?php bible_render_layout_header(); ?>
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stats — Bible Browser</title>
<?php bible_render_layout_styles(); ?>
</head>
<body>
<?php bible_render_layout_banner(); ?>
<div class="bible-layout">
<main class="bible-main">
    <h1>Bible Page View Stats</h1>
    <div class="verse-card empty">
        Stats are not exposed in remote API mode &mdash; per-instance view
        counts are private to each deployment. Disable
        <code>use_remote_api</code> in <code>web/config.php</code> and point
        at a local database to see local view stats.
    </div>
</main>
<?php require __DIR__ . '/bible_sidebar.php'; ?>
</div>
</body>
</html>
<?php
    exit;
}

try {
    $pdo = bible_pdo();

    // Detect whether the book column is named 'book_code' or 'book'
    $cols     = $pdo->query("SHOW COLUMNS FROM verse_views")->fetchAll(PDO::FETCH_COLUMN);
    $book_col = in_array('book_code', $cols) ? 'book_code' : 'book';

    // Total views
    $total = (int)$pdo->query("SELECT COALESCE(SUM(view_count),0) FROM verse_views")->fetchColumn();

    // Total distinct verses ever loaded
    $distinct = (int)$pdo->query("SELECT COUNT(*) FROM verse_views")->fetchColumn();

    // Top 50 most-viewed verses (join book table for readable name)
    $top = $pdo->query(
        "SELECT vv.$book_col AS book_code, vv.chapter, vv.verse, vv.view_count,
                COALESCE(b.name, vv.$book_col) AS book_name
           FROM verse_views vv
      LEFT JOIN book b ON b.osis_code COLLATE utf8mb4_unicode_ci = vv.$book_col
          ORDER BY vv.view_count DESC
          LIMIT 50"
    )->fetchAll();

    // Views per book (summed), ordered by total desc
    $by_book = $pdo->query(
        "SELECT vv.$book_col AS book_code, COALESCE(b.name, vv.$book_col) AS book_name,
                SUM(vv.view_count) AS total, COUNT(*) AS verses_seen
           FROM verse_views vv
      LEFT JOIN book b ON b.osis_code COLLATE utf8mb4_unicode_ci = vv.$book_col
          GROUP BY vv.$book_col, book_name
          ORDER BY total DESC"
    )->fetchAll();

} catch (Throwable $e) {
    $total     = 0;
    $distinct  = 0;
    $top       = [];
    $by_book   = [];
    $debug_err = $e->getMessage();
}
?><?php bible_render_layout_header(); ?>

<html><head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="author" content="Richard Amiel McGough">
<title>Bible Page View Stats — Bible Wheel</title>
<?php bible_render_layout_styles(); ?>
<style>
  .stats-summary { display: flex; gap: 32px; flex-wrap: wrap; margin: 16px 0 24px; }
  .stat-box { border: 1px solid var(--border,#ddd); border-radius: 6px; padding: 12px 20px; text-align: center; }
  .stat-box .num { font-size: 2rem; font-weight: bold; color: var(--accent,#2a6496); }
  .stat-box .lbl { font-size: 11px; color: var(--muted,#888); margin-top: 2px; }
  .stats-grid { display: grid; grid-template-columns: auto auto; gap: 24px; justify-content: start; }
  @media (max-width: 700px) { .stats-grid { grid-template-columns: 1fr; } }
  main h1 { font-size: 1.4rem; margin-bottom: 4px; }
  main h2 { font-size: 1rem; border-bottom: 1px solid var(--border,#ddd); padding-bottom: 4px; margin-bottom: 8px; }
  .stats-table { border-collapse: collapse; font-size: 13px; }
  .stats-table th, .stats-table td { text-align: left; padding: 5px 12px; border-bottom: 1px solid var(--border,#eee); }
  .stats-table th { color: #333; background: var(--bg-alt,#f5f5f5); font-weight: 600; }
  .stats-table td.num, .stats-table th.num { text-align: right; font-variant-numeric: tabular-nums; }
</style>
</head>
<body>
<?php bible_render_layout_banner(); ?>
<div class="bible-layout">
<main class="bible-main">
<?php if (!empty($debug_err)): ?>
<pre style="color:red;background:#fff8f8;padding:8px;border:1px solid red">Stats error: <?= htmlspecialchars($debug_err) ?></pre>
<?php endif; ?>
<h1>Bible Page View Stats</h1>

<div class="stats-summary">
  <div class="stat-box">
    <div class="num"><?= number_format($total) ?></div>
    <div class="lbl">Total page views</div>
  </div>
  <div class="stat-box">
    <div class="num"><?= number_format($distinct) ?></div>
    <div class="lbl">Distinct verses viewed</div>
  </div>
</div>

<div class="stats-grid">

  <div>
    <h2>Top 50 Most-Viewed Verses</h2>
    <?php if ($top): ?>
    <table class="stats-table">
      <thead><tr><th>#</th><th>Verse</th><th class="num">Views</th></tr></thead>
      <tbody>
      <?php foreach ($top as $i => $row): ?>
        <tr>
          <td><?= $i + 1 ?></td>
          <td><a href="index.php?book=<?= h($row['book_code']) ?>&chapter=<?= (int)$row['chapter'] ?>&verse=<?= (int)$row['verse'] ?>">
            <?= h($row['book_name']) ?> <?= (int)$row['chapter'] ?>:<?= (int)$row['verse'] ?>
          </a></td>
          <td class="num"><?= number_format((int)$row['view_count']) ?></td>
        </tr>
      <?php endforeach; ?>
      </tbody>
    </table>
    <?php else: ?>
    <p style="color:var(--muted,#888)">No data yet.</p>
    <?php endif; ?>
  </div>

  <div>
    <h2>Views by Book</h2>
    <?php if ($by_book): ?>
    <table class="stats-table">
      <thead><tr><th>Book</th><th class="num">Views</th><th class="num">Verses</th></tr></thead>
      <tbody>
      <?php foreach ($by_book as $row): ?>
        <tr>
          <td><?= h($row['book_name']) ?></td>
          <td class="num"><?= number_format((int)$row['total']) ?></td>
          <td class="num"><?= number_format((int)$row['verses_seen']) ?></td>
        </tr>
      <?php endforeach; ?>
      </tbody>
    </table>
    <?php else: ?>
    <p style="color:var(--muted,#888)">No data yet.</p>
    <?php endif; ?>
  </div>

</div>
</main>
<?php require __DIR__ . '/bible_sidebar.php'; ?>
</div>
</body>
</html>
