"""Busca en los informes por significado y muestra los fragmentos más parecidos.

Uso:
    python -m rag_informes.search "riesgos de tipos de interés"
    python -m rag_informes.search "deuda neta" --k 3 --company Ferrovial
"""

from __future__ import annotations

import argparse
import textwrap

from .embeddings import MODEL_NAME
from .vector_store import get_collection, search


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Búsqueda semántica en los informes.")
    ap.add_argument("question", help="Lo que quieres buscar, entre comillas")
    ap.add_argument("--k", type=int, default=5, help="Cuántos fragmentos mostrar")
    ap.add_argument("--company", help="Filtrar por empresa (p. ej. BBVA)")
    ap.add_argument("--chars", type=int, default=400, help="Caracteres de cada fragmento a mostrar")
    args = ap.parse_args(argv)

    from .embeddings import E5Embedder

    embedder = E5Embedder(MODEL_NAME)
    collection = get_collection(MODEL_NAME)
    hits = search(collection, embedder, args.question, k=args.k, company=args.company)

    print(f'\nPregunta: "{args.question}"\n')
    for i, h in enumerate(hits, 1):
        print(f"[{i}] {h['company']} {h['year']}, página {h['page']} · similitud {h['similarity']:.3f}"
              f"{' · contiene tabla' if h['has_table'] else ''}")
        snippet = h["text"][: args.chars] + ("…" if len(h["text"]) > args.chars else "")
        print(textwrap.indent(textwrap.fill(snippet, 100), "    "), end="\n\n")


if __name__ == "__main__":
    main()
