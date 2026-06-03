-- gematria_schema.sql
-- Adds gematria value tables + supporting stored procedures (GetGematriaWords)
-- and verse_views + record_verse_view proc for web UI features.
-- Run after schema.sql and import_bible.py have completed.
-- Safe to re-run (uses IF NOT EXISTS / DROP IF EXISTS).

-- Per-word gematria values.
-- SMALLINT UNSIGNED (0-65535) is sufficient for any single word.
CREATE TABLE IF NOT EXISTS gematria_word (
    word_id        INT UNSIGNED    NOT NULL,
    standard       SMALLINT UNSIGNED NOT NULL DEFAULT 0,  -- Mispar Hechrachi / Isopsephy
    standard_sofit SMALLINT UNSIGNED NOT NULL DEFAULT 0,  -- as above but final forms = 500-900
    ordinal        SMALLINT UNSIGNED NOT NULL DEFAULT 0,  -- Alef=1…Tav=22 / Alpha=1…Omega=24
    reduced        TINYINT UNSIGNED  NOT NULL DEFAULT 0,  -- digital root of standard (1-9)
    PRIMARY KEY (word_id),
    CONSTRAINT fk_gematria_word
        FOREIGN KEY (word_id) REFERENCES word(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Per-verse gematria totals (sum of all words in the verse).
-- MEDIUMINT UNSIGNED (0-16,777,215) accommodates long verses with sofit values.
CREATE TABLE IF NOT EXISTS gematria_verse (
    verse_id       INT UNSIGNED     NOT NULL,
    standard       MEDIUMINT UNSIGNED NOT NULL DEFAULT 0,
    standard_sofit MEDIUMINT UNSIGNED NOT NULL DEFAULT 0,
    ordinal        MEDIUMINT UNSIGNED NOT NULL DEFAULT 0,
    reduced        TINYINT UNSIGNED   NOT NULL DEFAULT 0,  -- digital root of standard total
    PRIMARY KEY (verse_id),
    CONSTRAINT fk_gematria_verse
        FOREIGN KEY (verse_id) REFERENCES verse(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Note: Stored procedures (GetGematriaWords, record_verse_view) and the
-- verse_views table (if not present in core schema) are ensured at runtime
-- by the pipeline's ensure_schema_migrations() for both fresh and existing DBs.
-- This keeps the .sql file simple (only tables) while supporting the web search/UI features.
