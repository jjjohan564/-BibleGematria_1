import re
import json
from collections import defaultdict
from pathlib import Path

def extract_p_variants(path):
    """
    Reads a TAHOT-style file and extracts all P= variants.
    Returns a dict: { "Exo.20.4": [("Exo.20.4#09", "מִ/מַּעַל"), ...] }
    """

    grouped = defaultdict(list)
    p_pattern = re.compile(r'\bP=\s*([^\t]+)')

    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            # Extract full reference (e.g., Exo.20.4#09)
            ref_match = re.match(r'^([A-Za-z0-9\.#]+)', line)
            if not ref_match:
                continue

            full_ref = ref_match.group(1)

            # Extract verse-level reference (e.g., Exo.20.4)
            verse_ref = full_ref.split('#')[0]

            # Extract P= text
            p_match = p_pattern.search(line)
            if p_match:
                p_text = p_match.group(1).strip()
                grouped[verse_ref].append((full_ref, p_text))

    return grouped


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent.parent
    filename = str(project_root / "data" / "raw" / "TAHOT Gen-Deu - Translators Amalgamated Hebrew OT - STEPBible.org CC BY.txt")

    grouped = extract_p_variants(filename)

    # Pretty print
    for verse, items in grouped.items():
        print(f"\n{verse}")
        print("-" * len(verse))
        for full_ref, text in items:
            print(f"  {full_ref}: {text}")

    # Write to data/processed/
    project_root = Path(__file__).resolve().parent.parent.parent
    out_path = project_root / "data" / "processed" / "p_variants.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as out:
        json.dump(grouped, out, ensure_ascii=False, indent=2)
    print(f"Wrote {out_path}")
