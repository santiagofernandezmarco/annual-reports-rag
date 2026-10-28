"""Procesa todos los PDF listados en data/companies.json y guarda data/processed/pages.jsonl.

Uso:
    python -m rag_informes.ingest            # procesa todo
    python -m rag_informes.ingest --no-tables
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pdf_extract import extract_pdf

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Extrae texto limpio de los informes anuales.")
    ap.add_argument("--config", type=Path, default=DATA / "companies.json")
    ap.add_argument("--raw", type=Path, default=DATA / "raw")
    ap.add_argument("--out", type=Path, default=DATA / "processed" / "pages.jsonl")
    ap.add_argument("--no-tables", action="store_true", help="No convertir tablas a Markdown")
    args = ap.parse_args(argv)

    config = json.loads(args.config.read_text(encoding="utf-8"))
    args.out.parent.mkdir(parents=True, exist_ok=True)

    total_pages = 0
    with args.out.open("w", encoding="utf-8") as f:
        for doc in config["documents"]:
            pdf = args.raw / doc["file"]
            if not pdf.exists():
                print(f"[aviso] No encuentro {pdf.name}; lo salto.")
                continue

            pages = extract_pdf(
                pdf, doc["company"], doc["year"],
                skip_pages=doc.get("skip_pages"),
                tables_as_markdown=not args.no_tables,
            )
            for p in pages:
                f.write(json.dumps(p.to_dict(), ensure_ascii=False) + "\n")

            empty = [p.page for p in pages if len(p.text) < 50]
            with_tables = sum(1 for p in pages if p.n_tables)
            removed = {line for p in pages for line in p.removed_lines}
            print(
                f"{doc['company']} {doc['year']}: {len(pages)} páginas, "
                f"{with_tables} con tablas, {len(empty)} casi vacías"
            )
            if empty:
                print(f"   páginas casi vacías (¿escaneadas o solo gráficos?): {empty[:15]}")
            if removed:
                print(f"   ejemplos de cabeceras/pies eliminados: {sorted(removed)[:5]}")
            total_pages += len(pages)

    print(f"\nGuardadas {total_pages} páginas en {args.out}")


if __name__ == "__main__":
    main()
