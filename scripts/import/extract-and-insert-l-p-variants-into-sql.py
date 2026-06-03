import re
import csv
import sys
from pathlib import Path

# Regex for valid references like Exo.20.4#09
REF_PATTERN = re.compile(r'^[A-Za-z]{3}\.\d+\.\d+#\d+$')

def parse_full_ref(full_ref):
    """
    Example: Exo.20.4#09
    Returns: ('Exo', 20, 4, 9)
    """
    book, chap, verse_pos = full_ref.split(".")
    chapter = int(chap)
    verse, pos = verse_pos.split("#")
    return book, int(chapter), int(verse), int(pos)


def extract_l_p_variants(path):
    """
    Extracts (full_ref, book, chapter, verse, position, L_value, P_value)
    Only for lines that contain a P= variant.
    """
    results = []
    p_pattern = re.compile(r'\bP=\s*([^\t]+)')

    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue

            # Extract raw reference (may include =L(p), =L(b+p), etc.)
            raw_ref = parts[0].strip()

            # Remove everything after "="
            full_ref = raw_ref.split("=")[0]

            # Skip lines that are not valid references
            if not REF_PATTERN.match(full_ref):
                continue

            # Extract L-value (2nd column)
            L_value = parts[1].strip()

            # Extract P-value
            p_match = p_pattern.search(line)
            if not p_match:
                continue

            P_value = p_match.group(1).strip()

            # Parse reference safely
            book, chapter, verse, position = parse_full_ref(full_ref)

            results.append((full_ref, book, chapter, verse, position, L_value, P_value))

    return results


if __name__ == "__main__":
    # Require filename argument
    if len(sys.argv) < 2:
        print("Usage: python extract-and-insert-l-p-variants-into-sql.py <tahot-file>")
        sys.exit(1)

    filename = sys.argv[1]

    # Extract variants
    variants = extract_l_p_variants(filename)

    # Generate SQL output to data/processed/
    project_root = Path(__file__).resolve().parent.parent.parent
    out_path = project_root / "data" / "processed" / "p_variants_import.sql"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as out:

        # 1. CREATE TABLE statement
        out.write(
            "CREATE TABLE IF NOT EXISTS p_variants_import (\n"
            "    full_ref VARCHAR(32) PRIMARY KEY,\n"
            "    book VARCHAR(16) NOT NULL,\n"
            "    chapter SMALLINT UNSIGNED NOT NULL,\n"
            "    verse SMALLINT UNSIGNED NOT NULL,\n"
            "    position SMALLINT UNSIGNED NOT NULL,\n"
            "    L_value VARCHAR(255) NOT NULL,\n"
            "    P_value VARCHAR(255) NOT NULL\n"
            ");\n\n"
        )

        # 2. INSERT statements
        out.write(
            "INSERT INTO p_variants_import "
            "(full_ref, book, chapter, verse, position, L_value, P_value) VALUES\n"
        )

        rows = []
        for full_ref, book, chapter, verse, position, L_value, P_value in variants:
            L_sql = L_value.replace("'", "''")
            P_sql = P_value.replace("'", "''")
            rows.append(
                f"('{full_ref}', '{book}', {chapter}, {verse}, {position}, '{L_sql}', '{P_sql}')"
            )

        out.write(",\n".join(rows) + ";\n")

    print(f"Created {out_path}")
