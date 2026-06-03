-- =====================================================================
-- LXX schema (Septuagint, Rahlfs 1935) — separate namespace
-- Source: eliranwong/LXX-Rahlfs-1935  (CATSS LXXM + OSSP joins)
-- License: CC BY-NC-SA 4.0 — local use only.
-- =====================================================================
-- Design choice: the LXX lives in its own set of tables (book_lxx /
-- verse_lxx / word_lxx) parallel to the existing 11-table v2 schema.
-- The shared `edition` table gains one row, `LXX-Rahlfs`, which the web
-- UI uses as a mode switch — selecting it routes lookups to the LXX
-- tables and (where mt_parallel_osis allows) auto-jumps to the
-- corresponding LXX book.
--
-- Why separate tables?
--   * LXX uses Rahlfs's own versification (Ps 9 = MT 9+10, Esther has
--     Greek-only additions tagged 1:1a..1:1s, Daniel/Susanna/Bel/etc.
--     are first-class books).
--   * Several books have multiple recensions (JoshA/B, JudgA/B,
--     OG vs Theodotion Daniel/Susanna/Bel, Tobit B/A vs S).
--   * Mixing those into the shared book/verse/word tables would force
--     constant alignment-table lookups and break invariants in code
--     that assumes one tradition per book_id.
--
-- The existing tables (book, verse, word, etc.) are left strictly
-- alone by this script.
-- =====================================================================

USE stepbible;

-- ---------------------------------------------------------------------
-- Drop the dependent tables first so re-runs are clean. book_lxx is
-- referenced by verse_lxx and word_lxx, so order matters.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS word_lxx;
DROP TABLE IF EXISTS verse_lxx;
DROP TABLE IF EXISTS book_lxx;

-- ---------------------------------------------------------------------
-- book_lxx — one row per Rahlfs book identifier (59 books).
-- ---------------------------------------------------------------------
CREATE TABLE book_lxx (
    id               TINYINT UNSIGNED NOT NULL PRIMARY KEY,
    osis_code        VARCHAR(16) NOT NULL,      -- 'LxxGen', 'LxxJoshA', 'LxxPsSol'
    name             VARCHAR(60) NOT NULL,
    mt_parallel_osis VARCHAR(8)  NULL,          -- 'Gen' for LxxGen; NULL for deuteros
    tradition        VARCHAR(16) NOT NULL DEFAULT 'LXX',
                                                 -- LXX | LXX-alt | LXX-OG | Theodotion
    rahlfs_code      VARCHAR(16) NOT NULL,      -- the source's identifier ('1Sam/K', '1/3Kgs', 'TobBA')
    book_order       TINYINT UNSIGNED NOT NULL,
    UNIQUE KEY uq_book_lxx_osis (osis_code),
    KEY idx_book_lxx_mt_parallel (mt_parallel_osis),
    KEY idx_book_lxx_tradition   (tradition)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- verse_lxx — one row per LXX verse (~30,291 rows).
-- ---------------------------------------------------------------------
CREATE TABLE verse_lxx (
    id            INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    book_id       TINYINT UNSIGNED NOT NULL,
    chapter       SMALLINT UNSIGNED NOT NULL,
    verse         SMALLINT UNSIGNED NOT NULL,
    subverse      VARCHAR(4) NOT NULL DEFAULT '',   -- 'a'..'s' for Esther / Prov / Dan additions
    osis_ref      VARCHAR(32) NOT NULL,             -- 'LxxGen.1.1', 'LxxEsth.1.1a'
    raw_ref       VARCHAR(64) NOT NULL,             -- as in source, e.g. 'Esth 1:1a'
    text_original MEDIUMTEXT NOT NULL,              -- assembled accented Greek
    text_english  MEDIUMTEXT NOT NULL,              -- assembled English glosses
    word_count    SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    CONSTRAINT fk_verse_lxx_book FOREIGN KEY (book_id) REFERENCES book_lxx(id),
    UNIQUE KEY uq_verse_lxx_ref (book_id, chapter, verse, subverse),
    KEY idx_verse_lxx_chapter (book_id, chapter)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- word_lxx — one row per Greek word in the LXX (~623,693 rows).
-- ---------------------------------------------------------------------
CREATE TABLE word_lxx (
    id              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    verse_id        INT UNSIGNED NOT NULL,
    book_id         TINYINT UNSIGNED NOT NULL,        -- denormalized for quick filtering
    chapter         SMALLINT UNSIGNED NOT NULL,
    verse           SMALLINT UNSIGNED NOT NULL,
    position        SMALLINT UNSIGNED NOT NULL,       -- 1..N within verse
    text_original   VARCHAR(255) NULL,                -- accented Greek surface
    transliteration VARCHAR(255) NULL,                -- SBL transliteration
    translation     VARCHAR(255) NULL,                -- English gloss (1-2 senses)
    strongs         VARCHAR(32)  NULL,                -- 'G####' (single Strong)
    strongs_primary VARCHAR(16)  NULL,                -- normalized G####
    grammar         VARCHAR(64)  NULL,                -- CATSS morph code, e.g. 'V.AAI3S'
    grammar_desc    VARCHAR(128) NULL,                -- 'verb, Aor Act Ind 3rd Sing'
    lemma           VARCHAR(128) NULL,                -- dictionary form (OSSP lexeme)
    dictionary_form VARCHAR(255) NULL,                -- 'lemma=gloss' (mirrors NT convention)
    pronunciation   VARCHAR(128) NULL,                -- modern Greek pronunciation
    CONSTRAINT fk_word_lxx_verse FOREIGN KEY (verse_id) REFERENCES verse_lxx(id) ON DELETE CASCADE,
    CONSTRAINT fk_word_lxx_book  FOREIGN KEY (book_id) REFERENCES book_lxx(id),
    UNIQUE KEY uq_word_lxx_pos    (verse_id, position),
    KEY idx_word_lxx_strongs_p   (strongs_primary),
    KEY idx_word_lxx_book_ref    (book_id, chapter, verse, position)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- edition row for the LXX-Rahlfs mode selector (shared edition table).
-- ---------------------------------------------------------------------
INSERT INTO edition (code, name, language, description, edition_order)
VALUES ('LXX-Rahlfs', 'LXX Rahlfs 1935', 'Greek',
        'Septuagint, Alfred Rahlfs editio minor 1935 (CATSS / Eliran Wong)',
        25)
ON DUPLICATE KEY UPDATE name = VALUES(name),
                        description = VALUES(description);

-- ---------------------------------------------------------------------
-- book_lxx seed data — 59 books, ids 1-59, book_order matches id.
-- mt_parallel_osis uses the existing book.osis_code values (Gen/Exo/...).
-- tradition: 'LXX' is primary; 'LXX-alt' is JoshA/JudgA/TobS;
-- 'LXX-OG' is the Old Greek Daniel/Susanna/Bel; 'Theodotion' is the
-- Theodotion Daniel/Susanna/Bel.
-- ---------------------------------------------------------------------
INSERT INTO book_lxx (id, osis_code, name, mt_parallel_osis, tradition, rahlfs_code, book_order) VALUES
( 1, 'LxxGen',    'LXX Genesis',                  'Gen', 'LXX',        'Gen',     1),
( 2, 'LxxExod',   'LXX Exodus',                   'Exo', 'LXX',        'Exod',    2),
( 3, 'LxxLev',    'LXX Leviticus',                'Lev', 'LXX',        'Lev',     3),
( 4, 'LxxNum',    'LXX Numbers',                  'Num', 'LXX',        'Num',     4),
( 5, 'LxxDeut',   'LXX Deuteronomy',              'Deu', 'LXX',        'Deut',    5),
( 6, 'LxxJoshB',  'LXX Joshua (Vaticanus, B)',    'Jos', 'LXX',        'JoshB',   6),
( 7, 'LxxJoshA',  'LXX Joshua (Alexandrinus, A)', 'Jos', 'LXX-alt',    'JoshA',   7),
( 8, 'LxxJudgB',  'LXX Judges (B)',               'Jdg', 'LXX',        'JudgB',   8),
( 9, 'LxxJudgA',  'LXX Judges (A)',               'Jdg', 'LXX-alt',    'JudgA',   9),
(10, 'LxxRuth',   'LXX Ruth',                     'Rut', 'LXX',        'Ruth',   10),
(11, 'Lxx1Kdm',   'LXX 1 Kingdoms (= MT 1 Sam)',  '1Sa', 'LXX',        '1Sam/K', 11),
(12, 'Lxx2Kdm',   'LXX 2 Kingdoms (= MT 2 Sam)',  '2Sa', 'LXX',        '2Sam/K', 12),
(13, 'Lxx3Kdm',   'LXX 3 Kingdoms (= MT 1 Kgs)',  '1Ki', 'LXX',        '1/3Kgs', 13),
(14, 'Lxx4Kdm',   'LXX 4 Kingdoms (= MT 2 Kgs)',  '2Ki', 'LXX',        '2/4Kgs', 14),
(15, 'Lxx1Chr',   'LXX 1 Chronicles',             '1Ch', 'LXX',        '1Chr',   15),
(16, 'Lxx2Chr',   'LXX 2 Chronicles',             '2Ch', 'LXX',        '2Chr',   16),
(17, 'Lxx2Esd',   'LXX 2 Esdras (= MT Ezra-Neh)', 'Ezr', 'LXX',        '2Esdr',  17),
(18, 'LxxEsth',   'LXX Esther (Greek expansions)','Est', 'LXX',        'Esth',   18),
(19, 'LxxJob',    'LXX Job',                      'Job', 'LXX',        'Job',    19),
(20, 'LxxPs',     'LXX Psalms',                   'Psa', 'LXX',        'Ps',     20),
(21, 'LxxProv',   'LXX Proverbs',                 'Pro', 'LXX',        'Prov',   21),
(22, 'LxxQoh',    'LXX Ecclesiastes (Qoheleth)',  'Ecc', 'LXX',        'Qoh',    22),
(23, 'LxxCant',   'LXX Song of Songs',            'Sng', 'LXX',        'Cant',   23),
(24, 'LxxIsa',    'LXX Isaiah',                   'Isa', 'LXX',        'Isa',    24),
(25, 'LxxJer',    'LXX Jeremiah',                 'Jer', 'LXX',        'Jer',    25),
(26, 'LxxLam',    'LXX Lamentations',             'Lam', 'LXX',        'Lam',    26),
(27, 'LxxEzek',   'LXX Ezekiel',                  'Ezk', 'LXX',        'Ezek',   27),
(28, 'LxxDan',    'LXX Daniel (OG)',              'Dan', 'LXX-OG',     'Dan',    28),
(29, 'LxxDanTh',  'Theodotion Daniel',            'Dan', 'Theodotion', 'DanTh',  29),
(30, 'LxxHos',    'LXX Hosea',                    'Hos', 'LXX',        'Hos',    30),
(31, 'LxxJoel',   'LXX Joel',                     'Jol', 'LXX',        'Joel',   31),
(32, 'LxxAmos',   'LXX Amos',                     'Amo', 'LXX',        'Amos',   32),
(33, 'LxxObad',   'LXX Obadiah',                  'Oba', 'LXX',        'Obad',   33),
(34, 'LxxJonah',  'LXX Jonah',                    'Jon', 'LXX',        'Jonah',  34),
(35, 'LxxMic',    'LXX Micah',                    'Mic', 'LXX',        'Mic',    35),
(36, 'LxxNah',    'LXX Nahum',                    'Nam', 'LXX',        'Nah',    36),
(37, 'LxxHab',    'LXX Habakkuk',                 'Hab', 'LXX',        'Hab',    37),
(38, 'LxxZeph',   'LXX Zephaniah',                'Zep', 'LXX',        'Zeph',   38),
(39, 'LxxHag',    'LXX Haggai',                   'Hag', 'LXX',        'Hag',    39),
(40, 'LxxZech',   'LXX Zechariah',                'Zec', 'LXX',        'Zech',   40),
(41, 'LxxMal',    'LXX Malachi',                  'Mal', 'LXX',        'Mal',    41),
-- Deuterocanonical / apocryphal — no MT parallel.
(42, 'LxxTobBA',  'Tobit (BA recension)',         NULL,  'LXX',        'TobBA',  42),
(43, 'LxxTobS',   'Tobit (Sinaiticus, S)',        NULL,  'LXX-alt',    'TobS',   43),
(44, 'LxxJdt',    'Judith',                       NULL,  'LXX',        'Jdt',    44),
(45, 'Lxx1Esd',   '1 Esdras',                     NULL,  'LXX',        '1Esdr',  45),
(46, 'Lxx1Mac',   '1 Maccabees',                  NULL,  'LXX',        '1Mac',   46),
(47, 'Lxx2Mac',   '2 Maccabees',                  NULL,  'LXX',        '2Mac',   47),
(48, 'Lxx3Mac',   '3 Maccabees',                  NULL,  'LXX',        '3Mac',   48),
(49, 'Lxx4Mac',   '4 Maccabees',                  NULL,  'LXX',        '4Mac',   49),
(50, 'LxxWis',    'Wisdom of Solomon',            NULL,  'LXX',        'Wis',    50),
(51, 'LxxSir',    'Sirach (Ecclesiasticus)',      NULL,  'LXX',        'Sir',    51),
(52, 'LxxBar',    'Baruch',                       NULL,  'LXX',        'Bar',    52),
(53, 'LxxEpJer',  'Epistle of Jeremiah',          NULL,  'LXX',        'EpJer',  53),
(54, 'LxxOdes',   'Odes',                         NULL,  'LXX',        'Od',     54),
(55, 'LxxPsSol',  'Psalms of Solomon',            NULL,  'LXX',        'PsSol',  55),
(56, 'LxxSus',    'Susanna (OG)',                 NULL,  'LXX-OG',     'Sus',    56),
(57, 'LxxSusTh',  'Theodotion Susanna',           NULL,  'Theodotion', 'SusTh',  57),
(58, 'LxxBel',    'Bel and the Dragon (OG)',      NULL,  'LXX-OG',     'Bel',    58),
(59, 'LxxBelTh',  'Theodotion Bel',               NULL,  'Theodotion', 'BelTh',  59);

-- ---------------------------------------------------------------------
-- Sanity check
-- ---------------------------------------------------------------------
SELECT tradition, COUNT(*) AS books
  FROM book_lxx
 GROUP BY tradition
 ORDER BY tradition;
