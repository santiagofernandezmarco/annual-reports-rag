"""Trocea data/processed/pages.jsonl y guarda data/processed/chunks.jsonl.

Uso:
    python -m rag_informes.chunk                    # 300 palabras, 50 de solapamiento
    python -m rag_informes.chunk --max-words 200    # para probar otros tamaños
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from collections import defaultdict
from pathlib import Path

from .chunking import MAX_WORDS, OVERLAP_WORDS, chunk_page

DATA = Path(__file__).resolve().parents[2] / "data" / "processed"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Trocea las páginas en fragmentos.")
    ap.add_argument("--pages", type=Path, default=DATA / "pages.jsonl")
    ap.add_argument("--out", type=Path, default=DATA / "chunks.jsonl")
    ap.add_argument("--max-words", type=int, default=MAX_WORDS)
    ap.add_argument("--overlap", type=int, default=OVERLAP_WORDS)
    args = ap.parse_args(argv)

    by_doc: dict[str, list] = defaultdict(list)
    pages_without_chunks: dict[str, int] = defaultdict(int)
    with args.pages.open(encoding="utf-8") as f:
        for line in f:
            page = json.loads(line)
            chunks = chunk_page(page, args.max_words, args.overlap)
            by_doc[page["doc_id"]].extend(chunks)
            if not chunks:
                pages_without_chunks[page["doc_id"]] += 1

    tmp = args.out.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for chunks in by_doc.values():
            for c in chunks:
                f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
    os.replace(tmp, args.out)

    print(f"Fragmentos de máx. {args.max_words} palabras, solapamiento {args.overlap}\n")
    print(f"{'Documento':<18}{'Fragmentos':>11}{'Media pal.':>11}{'Mín':>6}{'Máx':>6}"
          f"{'Con tabla':>11}{'Págs. sin fragmentos':>22}")
    total = 0
    for doc, chunks in by_doc.items():
        words = [c.n_words for c in chunks]
        tables = sum(c.has_table for c in chunks)
        print(f"{doc:<18}{len(chunks):>11}{statistics.mean(words):>11.0f}{min(words):>6}{max(words):>6}"
              f"{tables:>11}{pages_without_chunks[doc]:>22}")
        total += len(chunks)
    print(f"\nGuardados {total} fragmentos en {args.out}")


if __name__ == "__main__":
    main()
