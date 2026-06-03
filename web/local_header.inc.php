<?php
// local_header.inc.php
// Minimal standalone header for when the BibleDB web UI is run independently
// (not embedded inside the biblewheel.com site structure).
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bible Browser</title>
<link rel="stylesheet" href="style.css">
<style>
  body { margin: 0; font-family: system-ui, sans-serif; }
  .local-header {
    background: #1a1a2e;
    color: #eaeaea;
    padding: 12px 20px;
    font-size: 15px;
    border-bottom: 1px solid #333;
  }
  .local-header a { color: #7ec8ff; text-decoration: none; }
</style>
</head>
<body>
<div class="local-header">
  <strong>BibleDB</strong> — Standalone Development Mode
  &nbsp;|&nbsp; <a href="index.php">Home</a>
</div>
