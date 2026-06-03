<?php
// verse_selector.inc.php — reusable verse-picker <form> for Bible Browser pages.
//
// Output: a bare <form method="get" id="dd-form">…</form> — callers wrap it
// in whatever <div> they need (e.g. <div class="selector">).
//
// Variables expected in the caller's scope (all standard after the normal
// parameter-resolution block):
//
//   $books         array of book rows: osis_code, name, language
//   $chapters      array of chapter ints
//   $verses        array of verse ints
//   $book_code     string — currently selected osis_code
//   $chapter       int
//   $verse         int
//   $selector_extra_fields  (optional) HTML string injected between the Verse
//                           select and the <button type="submit">.
//                           Use for edition pickers, count selects, custom
//                           inputs, etc.
?>
<form method="get" id="dd-form">
    <label class="sel-label">Book</label>
    <select name="book" id="sel-book">
    <?php foreach ($books as $b): ?>
        <?php $b_full = preg_replace('/^LXX\s+/i', '', $b['name']); ?>
        <?php $b_abbr = preg_replace('/^Lxx/', '', $b['osis_code']); ?>
        <option value="<?= h($b['osis_code']) ?>"
                data-lang="<?= h($b['language']) ?>"
                data-full="<?= h($b_full) ?>"
                data-abbr="<?= h($b_abbr) ?>"
                <?= $b['osis_code'] === $book_code ? 'selected' : '' ?>>
            <?= h($b_full) ?>
        </option>
    <?php endforeach; ?>
    </select>

    <label class="sel-label">Chapter</label>
    <select name="chapter" id="sel-chapter">
    <?php foreach ($chapters as $c): ?>
        <option value="<?= (int)$c ?>" <?= (int)$c === (int)$chapter ? 'selected' : '' ?>>
            <?= (int)$c ?>
        </option>
    <?php endforeach; ?>
    </select>

    <label class="sel-label">Verse</label>
    <select name="verse" id="sel-verse">
    <?php foreach ($verses as $vn): ?>
        <option value="<?= (int)$vn ?>" <?= (int)$vn === (int)$verse ? 'selected' : '' ?>>
            <?= (int)$vn ?>
        </option>
    <?php endforeach; ?>
    </select>

    <?= $selector_extra_fields ?? '' ?>

    <button type="submit">Go</button>
</form>
