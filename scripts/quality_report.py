"""Mide la calidad de la extracción leyendo data/processed/pages.jsonl.

No vuelve a abrir los PDF: tarda segundos. Cuenta, por empresa:
  - páginas con restos de <br> (problema que ya sabemos arreglar);
  - páginas con "palabras pegadas": secuencias de 25 letras o más sin espacio,
    p. ej. "Acuerdoconjuntoenelquelaspartes". Pocas palabras reales en español
    o inglés llegan a 25 letras, así que es una buena señal de espacios perdidos.

Uso:
    python scripts/quality_report.py              # resumen por empresa
    python scripts/quality_report.py --ejemplos 5 # además, ejemplos de cada empresa
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

PAGES = Path(__file__).resolve().parents[1] / "data" / "processed" / "pages.jsonl"

GLUED_RE = re.compile(r"[^\W\d_]{25,}")          # 25+ letras seguidas (incluye tildes)
BR_RE = re.compile(r"<br\s*/?>|&lt;br\s*/?&gt;", re.IGNORECASE)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ejemplos", type=int, default=0, help="Ejemplos a mostrar por empresa")
    args = ap.parse_args()

    stats = defaultdict(lambda: {"pages": 0, "tables": 0, "br": 0, "glued": 0,
                                 "glued_in_tables": 0, "examples": []})

    for line in PAGES.open(encoding="utf-8"):
        p = json.loads(line)
        s = stats[p["doc_id"]]
        s["pages"] += 1
        s["tables"] += p["n_tables"] > 0
        s["br"] += bool(BR_RE.search(p["text"]))

        glued = GLUED_RE.findall(p["text"])
        if glued:
            s["glued"] += 1
            s["glued_in_tables"] += p["n_tables"] > 0
            s["examples"].append((p["page"], glued[0][:60]))

    print(f"{'Documento':<18}{'Páginas':>8}{'Con tablas':>12}{'Con <br>':>10}"
          f"{'Pegadas':>9}{'  (de ellas con tablas)'}")
    for doc, s in stats.items():
        pct = 100 * s["glued"] / s["pages"]
        print(f"{doc:<18}{s['pages']:>8}{s['tables']:>12}{s['br']:>10}"
              f"{s['glued']:>9} ({pct:4.1f} %){s['glued_in_tables']:>10}")

    if args.ejemplos:
        for doc, s in stats.items():
            print(f"\n{doc} · ejemplos de palabras pegadas (página: texto)")
            for page, ex in s["examples"][: args.ejemplos]:
                print(f"   p.{page}: {ex}")


if __name__ == "__main__":
    main()
