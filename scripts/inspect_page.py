"""Muestra el texto limpio de una página concreta para comprobar la extracción a ojo.

Uso:
    python scripts/inspect_page.py Ferrovial 2025 42
"""

import json
import sys
from pathlib import Path

PAGES = Path(__file__).resolve().parents[1] / "data" / "processed" / "pages.jsonl"


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    company, year, page = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    for line in PAGES.open(encoding="utf-8"):
        p = json.loads(line)
        if p["company"].lower() == company.lower() and p["year"] == year and p["page"] == page:
            print(f"--- {p['company']} {p['year']} · página {p['page']} (impresa: {p['page_label']}) "
                  f"· {p['n_tables']} tablas ---\n")
            print(p["text"])
            print("\n--- eliminado como cabecera/pie ---")
            print(p["removed_lines"])
            return
    sys.exit("Página no encontrada. ¿Has ejecutado antes la ingesta?")


if __name__ == "__main__":
    main()
