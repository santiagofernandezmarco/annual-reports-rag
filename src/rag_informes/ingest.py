"""Procesa los PDF listados en data/companies.json.

Cada informe se guarda en su propio archivo, data/processed/docs/<Empresa>_<año>.jsonl,
en cuanto termina. Si la ingesta se corta (suspensión, Ctrl+C...), al relanzarla se
saltan los informes ya hechos. Al final se juntan todos en data/processed/pages.jsonl.

Uso:
    python -m rag_informes.ingest            # procesa solo lo que falta o ha cambiado
    python -m rag_informes.ingest --force    # vuelve a procesarlo todo
    python -m rag_informes.ingest --no-tables
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from .pdf_extract import extract_pdf

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def _is_up_to_date(out: Path, pdf: Path) -> bool:
    """El informe ya está procesado y el PDF no ha cambiado desde entonces."""
    return out.exists() and out.stat().st_mtime >= pdf.stat().st_mtime


def _write_atomic(path: Path, lines: list[str]) -> None:
    """Escribe a un archivo temporal y lo renombra al final.

    Así nunca queda un archivo a medias: o está completo o no existe.
    """
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.writelines(lines)
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Extrae texto limpio de los informes anuales.")
    ap.add_argument("--config", type=Path, default=DATA / "companies.json")
    ap.add_argument("--raw", type=Path, default=DATA / "raw")
    ap.add_argument("--out", type=Path, default=DATA / "processed" / "pages.jsonl")
    ap.add_argument("--force", action="store_true", help="Reprocesar aunque ya esté hecho")
    ap.add_argument("--no-tables", action="store_true", help="No convertir tablas a Markdown")
    args = ap.parse_args(argv)

    config = json.loads(args.config.read_text(encoding="utf-8"))
    docs_dir = args.out.parent / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    done_files: list[Path] = []
    for doc in config["documents"]:
        pdf = args.raw / doc["file"]
        out = docs_dir / f"{doc['company']}_{doc['year']}.jsonl"
        if not pdf.exists():
            print(f"[aviso] No encuentro {pdf.name}; lo salto.")
            continue

        if _is_up_to_date(out, pdf) and not args.force:
            print(f"{doc['company']} {doc['year']}: ya procesado, lo salto (usa --force para repetir)")
            done_files.append(out)
            continue

        print(f"Procesando {pdf.name}... (puede tardar varios minutos)", flush=True)
        t0 = time.time()
        pages = extract_pdf(
            pdf, doc["company"], doc["year"],
            skip_pages=doc.get("skip_pages"),
            tables_as_markdown=not args.no_tables,
        )
        _write_atomic(out, [json.dumps(p.to_dict(), ensure_ascii=False) + "\n" for p in pages])
        done_files.append(out)

        empty = [p.page for p in pages if len(p.text) < 50]
        with_tables = sum(1 for p in pages if p.n_tables)
        fallback = sum(1 for p in pages if p.n_tables_discarded)
        removed = {line for p in pages for line in p.removed_lines}
        print(
            f"{doc['company']} {doc['year']}: {len(pages)} páginas, "
            f"{with_tables} con tablas, {fallback} con tablas pasadas a texto (plan B), "
            f"{len(empty)} casi vacías · {time.time() - t0:.0f} s"
        )
        if empty:
            print(f"   páginas casi vacías (¿escaneadas o solo gráficos?): {empty[:15]}")
        if removed:
            print(f"   ejemplos de cabeceras/pies eliminados: {sorted(removed)[:5]}")

    # Juntar todos los informes en un único archivo para la Fase 2
    lines = [line for f in done_files for line in f.open(encoding="utf-8")]
    _write_atomic(args.out, lines)
    print(f"\nGuardadas {len(lines)} páginas de {len(done_files)} informes en {args.out}")


if __name__ == "__main__":
    main()
