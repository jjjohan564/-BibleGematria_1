-- =====================================================================
-- Bible Database Schema v2 (MariaDB / MySQL 8+)
-- Source: STEPBible.org TAGNT (Greek NT) + TAHOT (Hebrew OT), CC BY 4.0
-- =====================================================================
-- Goals of v2:
--   * Normalize editions/manuscripts into first-class tables.
--   * Promote textual variants from freeform strings to structured rows
--     so every variant is queryable by edition, kind, Strong's, etc.
--   * Preserve Hebrew morpheme breakdown (prefixes / root / suffixes).
--   * Preserve grammatical "conjoin" links between words.
--   * Preserve alt Strong's tag-instance breakdown.
--   * Preserve verbatim verse-summary blocks for round-tripping.
--
-- Tables (11):
--   book                  – 66 canonical books
--   edition               – 24 named manuscript editions (9 Greek + 15 Hebrew)
--   verse                 – one per Bible verse
--   verse_summary         – verbatim '#_Translation' / '#_Word=Grammar' lines
--   word                  – the canonical printed form of each word
--   word_edition          – many-to-many: word ↔ editions containing the base form
--   word_alt_strong       – word ↔ alternate Strong's tags
--   word_morpheme         – Hebrew prefix/root/suffix breakdown (one row per element)
--   word_link             – grammatical conjoin arrows (word → target word in same verse)
--   variant               – one row per textual variant reading
--   variant_edition       – many-to-many: variant ↔ editions supporting it
-- =====================================================================

CREATE DATABASE IF NOT EXISTS stepbible
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE stepbible;

-- Drop in dependency-safe order so the script is fully re-runnable.
DROP VIEW  IF EXISTS v_verse;
DROP TABLE IF EXISTS variant_edition;
DROP TABLE IF EXISTS variant;
DROP TABLE IF EXISTS word_link;
DROP TABLE IF EXISTS word_morpheme;
DROP TABLE IF EXISTS word_alt_strong;
DROP TABLE IF EXISTS word_edition;
DROP TABLE IF EXISTS word;
DROP TABLE IF EXISTS verse_summary;
DROP TABLE IF EXISTS verse;
DROP TABLE IF EXISTS edition;
DROP TABLE IF EXISTS book;

-- ---------------------------------------------------------------------
-- book: 66 rows. Populated by the Python loader (BOOKS list).
-- ---------------------------------------------------------------------
CREATE TABLE book (
    id            TINYINT UNSIGNED NOT NULL PRIMARY KEY,    -- 1..66 canonical order
    osis_code     VARCHAR(8)  NOT NULL,                     -- e.g. 'Gen', 'Mat', '1Co'
    name          VARCHAR(40) NOT NULL,                     -- e.g. 'Genesis'
    testament     ENUM('OT','NT') NOT NULL,
    language      ENUM('Hebrew','Greek') NOT NULL,
    book_order    TINYINT UNSIGNED NOT NULL,
    UNIQUE KEY uq_book_osis (osis_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- edition: named manuscript editions / sources.
-- ---------------------------------------------------------------------
-- Greek editions (9):
--   NA28  Nestle-Aland 28 (2012)
--   NA27  Nestle-Aland 27
--   Tyn   Tyndale House GNT (2017)
--   SBL   SBL GNT (Holmes 2010)
--   WH    Westcott + Hort (1881)
--   Treg  Tregelles 1879 / Jongkind 2009
--   TR    Textus Receptus (Scrivener 1894)
--   Byz   Byzantine (Robinson-Pierpont 2005)
--   KJV   King James Version (1611) – its underlying Greek text
--
-- Hebrew sources (15):
--   L     Leningrad codex
--   Q     Qere (scribal "spoken" correction)
--   K     Ketiv (uncorrected written text)
--   R     Restored text (Jos.21.36-37, Neh.7.67b)
--   X     Reconstructed Hebrew based on LXX
--   A     Aleppo manuscript
--   B     Biblia Hebraica Stuttgartensia (BHS)
--   C     Cairensis manuscript
--   D     Dead Sea / Judean Desert manuscript
--   E     Editorial emendation of ancient sources
--   F     Formatting variant (pointing / word division)
--   H     Ben Chaim edition (Second Rabbinic Bible)
--   P     Alternate punctuation
--   S     Scribal traditions (Itture/Tiqqune Sopherim, Masora)
--   V     Variant in other Hebrew manuscripts
-- ---------------------------------------------------------------------
CREATE TABLE edition (
    id            TINYINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    code          VARCHAR(8)  NOT NULL,         -- 'NA28', 'L', 'Q', etc.
    name          VARCHAR(80) NOT NULL,
    language      ENUM('Hebrew','Greek') NOT NULL,
    description   VARCHAR(255) NULL,
    edition_order TINYINT UNSIGNED NOT NULL,    -- display ordering
    UNIQUE KEY uq_edition_code_lang (code, language)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- verse: one row per Bible verse. Assembled text columns make
-- "give me the English of John 3:16" a single-table SELECT.
-- ---------------------------------------------------------------------
CREATE TABLE verse (
    id                       INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    book_id                  TINYINT UNSIGNED NOT NULL,
    chapter                  SMALLINT UNSIGNED NOT NULL,
    verse                    SMALLINT UNSIGNED NOT NULL,
    osis_ref                 VARCHAR(24) NOT NULL,           -- 'Gen.1.1' (NRSV English ref)
    raw_ref                  VARCHAR(64) NOT NULL,           -- 'Psa.3.0(3.1)' as in source
    text_original            MEDIUMTEXT NOT NULL,            -- assembled Hebrew/Greek
    text_english             MEDIUMTEXT NOT NULL,            -- assembled English glosses
    word_count               SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    has_significant_variant  BOOLEAN NOT NULL DEFAULT FALSE, -- '#_Significant variant' had content
    CONSTRAINT fk_verse_book FOREIGN KEY (book_id) REFERENCES book(id),
    UNIQUE KEY uq_verse_ref (book_id, chapter, verse),
    KEY idx_verse_chapter   (book_id, chapter),
    KEY idx_verse_sigvar    (has_significant_variant)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- verse_summary: round-trip storage of the '#_...' lines that appear
-- above each verse in the source files. One row per "block" — long
-- verses span multiple summary blocks (see e.g. Mat.5.22).
-- ---------------------------------------------------------------------
CREATE TABLE verse_summary (
    id            INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    verse_id      INT UNSIGNED NOT NULL,
    block_num     TINYINT UNSIGNED NOT NULL,    -- 1, 2, 3 for multi-line verses
    original_line MEDIUMTEXT NOT NULL,          -- '# Mat.5.22\tἐγὼ\tδὲ\t...'
    translation   MEDIUMTEXT NOT NULL,          -- '#_Translation\tI myself\thowever\t...'
    grammar       MEDIUMTEXT NOT NULL,          -- '#_Word=Grammar\tG1473=P-1NS\t...'
    sig_variant   MEDIUMTEXT NULL,              -- '#_Significant variant\t...' (NULL when empty)
    CONSTRAINT fk_vs_verse FOREIGN KEY (verse_id) REFERENCES verse(id) ON DELETE CASCADE,
    UNIQUE KEY uq_vs (verse_id, block_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- word: one row per Hebrew/Greek word in the canonical printed text.
-- ---------------------------------------------------------------------
CREATE TABLE word (
    id                 INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    verse_id           INT UNSIGNED NOT NULL,
    book_id            TINYINT UNSIGNED NOT NULL,             -- denormalized
    chapter            SMALLINT UNSIGNED NOT NULL,            -- denormalized
    verse              SMALLINT UNSIGNED NOT NULL,            -- denormalized
    position           SMALLINT UNSIGNED NOT NULL,            -- 1..N sequential within verse (unique)
    word_num           SMALLINT UNSIGNED NOT NULL,            -- original '#NN' from source file (may repeat in 15 Hebrew verses where two source blocks share an English ref)
    chunk_num          TINYINT  UNSIGNED NOT NULL DEFAULT 1,  -- which source block within the verse (1, 2, ...) — used to scope conjoin links
    source_type        VARCHAR(32) NOT NULL,                  -- 'NKO' / 'L' / 'Q(K)' etc.
    is_variant_marked  BOOLEAN NOT NULL DEFAULT FALSE,        -- TRUE if source_type has uppercase brackets
    language           ENUM('Hebrew','Greek') NOT NULL,
    text_original      VARCHAR(255) NULL,                     -- pointed Hebrew or accented Greek
    transliteration    VARCHAR(255) NULL,                     -- Hebrew col 3
    translation        VARCHAR(255) NULL,                     -- English gloss
    strongs            VARCHAR(128) NULL,                     -- raw dStrongs (e.g. 'H9003/{H7225G}')
    strongs_primary    VARCHAR(16)  NULL,                     -- first H/G number for indexing
    grammar            VARCHAR(64) NULL,                      -- morphology code
    dictionary_form    VARCHAR(255) NULL,                     -- Greek 'lemma=gloss'
    submeaning         VARCHAR(255) NULL,                     -- Greek sub-meaning
    sstrong_instance   VARCHAR(32) NULL,                      -- 'G0976_A'
    CONSTRAINT fk_word_verse FOREIGN KEY (verse_id) REFERENCES verse(id) ON DELETE CASCADE,
    CONSTRAINT fk_word_book  FOREIGN KEY (book_id)  REFERENCES book(id),
    UNIQUE KEY uq_word_pos   (verse_id, position),
    KEY idx_word_strongs_p   (strongs_primary),
    KEY idx_word_book_ref    (book_id, chapter, verse, word_num),
    KEY idx_word_translation (translation(64)),
    KEY idx_word_lang        (language),
    KEY idx_word_chunk       (verse_id, chunk_num, word_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- word_edition: which editions contain the BASE/printed form of a word.
-- For Greek this comes from the 'editions' column; for Hebrew it comes
-- from parsing the source_type letters (e.g. 'LA(bh)' → L+A as base).
-- ---------------------------------------------------------------------
CREATE TABLE word_edition (
    word_id      INT UNSIGNED NOT NULL,
    edition_id   TINYINT UNSIGNED NOT NULL,
    is_minor     BOOLEAN NOT NULL DEFAULT FALSE,    -- TRUE for lowercase markers (insignificant difference)
    PRIMARY KEY (word_id, edition_id),
    CONSTRAINT fk_we_word    FOREIGN KEY (word_id)    REFERENCES word(id)    ON DELETE CASCADE,
    CONSTRAINT fk_we_edition FOREIGN KEY (edition_id) REFERENCES edition(id),
    KEY idx_we_edition (edition_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- word_alt_strong: alternative Strong's-number tags for the same word
-- (used when other Bibles tag the word differently).
-- ---------------------------------------------------------------------
CREATE TABLE word_alt_strong (
    id           INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    word_id      INT UNSIGNED NOT NULL,
    alt_strong   VARCHAR(32) NOT NULL,           -- e.g. 'G0040', 'G5216'
    CONSTRAINT fk_was_word FOREIGN KEY (word_id) REFERENCES word(id) ON DELETE CASCADE,
    KEY idx_was_word    (word_id),
    KEY idx_was_strong  (alt_strong)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- word_morpheme: per-element breakdown of a Hebrew word's prefix(es),
-- root, and suffix(es). Parsed from the 'Expanded Strong tags' column.
-- One row per morpheme, ordered by morpheme_num.
-- ---------------------------------------------------------------------
CREATE TABLE word_morpheme (
    id            INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    word_id       INT UNSIGNED NOT NULL,
    morpheme_num  TINYINT UNSIGNED NOT NULL,    -- 1..N order within the word
    role          ENUM('prefix','root','suffix','punctuation') NOT NULL,
    strong_code   VARCHAR(16) NOT NULL,         -- 'H9001', 'H6213H', etc.
    hebrew        VARCHAR(64) NULL,             -- e.g. 'ו' or 'עָשָׂה'
    gloss         VARCHAR(255) NULL,            -- e.g. '&' or 'to make' or 'verseEnd'
    submeaning    VARCHAR(255) NULL,            -- text after '»' or ':'
    CONSTRAINT fk_wm_word FOREIGN KEY (word_id) REFERENCES word(id) ON DELETE CASCADE,
    UNIQUE KEY uq_wm (word_id, morpheme_num),
    KEY idx_wm_strong (strong_code),
    KEY idx_wm_role   (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- word_link: grammatical conjoin arrows. A particle/article that is
-- semantically attached to another word in the same verse.
-- direction: '»' = link points forward to a later word
--            '«' = link points backward to an earlier word
-- ---------------------------------------------------------------------
CREATE TABLE word_link (
    id              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    word_id         INT UNSIGNED NOT NULL,
    target_word_id  INT UNSIGNED NULL,             -- resolved at load time; NULL if cannot resolve
    target_word_num SMALLINT UNSIGNED NOT NULL,    -- always present; word_num within same verse
    target_strong   VARCHAR(16) NULL,
    direction       ENUM('forward','backward') NOT NULL,
    CONSTRAINT fk_wl_word   FOREIGN KEY (word_id)         REFERENCES word(id) ON DELETE CASCADE,
    CONSTRAINT fk_wl_target FOREIGN KEY (target_word_id)  REFERENCES word(id) ON DELETE SET NULL,
    KEY idx_wl_word    (word_id),
    KEY idx_wl_target  (target_word_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- variant: one row per textual variant reading.
-- kind:
--   'meaning'   - different word/form that affects translation
--   'spelling'  - same meaning, different spelling
--   'omission'  - this word is missing in some editions (the BASE word
--                  is the omitted-from-some-editions word)
--   'addition'  - some editions add an extra word here (the variant
--                  text is the added word; the BASE word is the
--                  preceding/following word it's attached to)
-- ---------------------------------------------------------------------
CREATE TABLE variant (
    id                   INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    word_id              INT UNSIGNED NOT NULL,    -- the canonical word this varies from
    kind                 ENUM('meaning','spelling','omission','addition') NOT NULL,
    -- position: the SLOT this variant occupies within its verse. For
    -- substitutions/omissions it matches the canonical word.position. For
    -- additions emitted by diff_editions.py it sits between two anchor
    -- positions (e.g. 4.25, 4.50, 4.75). Backfilled from word.position at
    -- the end of import_bible.py; populated explicitly for Phase 3 additions
    -- by diff_editions.py.
    position             DECIMAL(6,2) NOT NULL DEFAULT 0,
    text_original        VARCHAR(255) NULL,        -- variant Hebrew/Greek text
    transliteration      VARCHAR(255) NULL,
    translation          VARCHAR(255) NULL,        -- English meaning of the variant
    strongs              VARCHAR(64)  NULL,
    strongs_primary      VARCHAR(16)  NULL,
    grammar              VARCHAR(64)  NULL,
    note                 TEXT NULL,                -- human-readable note
    CONSTRAINT fk_var_word FOREIGN KEY (word_id) REFERENCES word(id) ON DELETE CASCADE,
    KEY idx_var_word         (word_id),
    KEY idx_var_kind         (kind),
    KEY idx_var_strong       (strongs_primary),
    KEY idx_variant_position (word_id, position)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- variant_edition: editions / manuscripts that support each variant.
-- ---------------------------------------------------------------------
CREATE TABLE variant_edition (
    variant_id  INT UNSIGNED NOT NULL,
    edition_id  TINYINT UNSIGNED NOT NULL,
    is_minor    BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (variant_id, edition_id),
    CONSTRAINT fk_ve_variant FOREIGN KEY (variant_id) REFERENCES variant(id) ON DELETE CASCADE,
    CONSTRAINT fk_ve_edition FOREIGN KEY (edition_id) REFERENCES edition(id),
    KEY idx_ve_edition (edition_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- Convenience view: verse rows joined to book metadata.
-- ---------------------------------------------------------------------
CREATE VIEW v_verse AS
SELECT  v.id           AS verse_id,
        b.osis_code    AS book,
        b.name         AS book_name,
        b.testament,
        b.language,
        v.chapter,
        v.verse,
        v.osis_ref,
        v.raw_ref,
        v.text_original,
        v.text_english,
        v.word_count,
        v.has_significant_variant
FROM verse v
JOIN book  b ON b.id = v.book_id;
