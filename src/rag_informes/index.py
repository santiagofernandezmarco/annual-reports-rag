"""Vectoriza data/processed/chunks.jsonl y lo guarda en Chroma (data/chroma/).

Reanudable: los fragmentos ya guardados se saltan. Si se corta, vuelve a lanzarlo.

Uso:
    python -m rag_informes.index            # indexa lo que falte
    python -m rag_informes.index --reset    # borra la base y empieza de cero
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .embeddings import MAX_TOKENS, MODEL_NAME, passage_text
from .vector_store import CHROMA_DIR, get_collection

CHUNKS = Path(__file__).resolve().parents[2] / "data" / "processed" / "chunks.jsonl"


def index_chunks(chunks: list[dict], collection, embedder, batch_size: int = 64, log=print) -> int:
    """Sincroniza la colección con la lista de fragmentos. Devuelve cuántos vectorizó.

    * Fragmentos nuevos o cuyo texto ha cambiado -> se vectorizan (upsert = añadir o reemplazar).
    * Fragmentos que ya no existen -> se borran de la colección.
    * Los que no han cambiado no se tocan: así un arreglo pequeño no obliga a reindexar todo.
    """
    stored = collection.get(include=["documents"])
    stored_text = dict(zip(stored["ids"], stored["documents"]))
    wanted = {c["chunk_id"] for c in chunks}

    obsolete = [i for i in stored_text if i not in wanted]
    for start in range(0, len(obsolete), 500):
        collection.delete(ids=obsolete[start:start + 500])

    pending = [c for c in chunks if stored_text.get(c["chunk_id"]) != c["text"]]
    log(f"{len(chunks)} fragmentos · {len(chunks) - len(pending)} sin cambios · "
        f"{len(pending)} por vectorizar · {len(obsolete)} borrados por obsoletos")

    t0 = time.time()
    for start in range(0, len(pending), batch_size):
        batch = pending[start:start + batch_size]
        collection.upsert(
            ids=[c["chunk_id"] for c in batch],
            embeddings=embedder.embed_passages([passage_text(c) for c in batch]),
            documents=[c["text"] for c in batch],
            metadatas=[{k: c[k] for k in ("doc_id", "company", "year", "page", "n_words", "has_table")}
                       for c in batch],
        )
        done = start + len(batch)
        elapsed = time.time() - t0
        remaining = elapsed / done * (len(pending) - done)
        log(f"  {done}/{len(pending)} ({100 * done / len(pending):.0f} %) · "
            f"quedan ~{remaining / 60:.1f} min")
    return len(pending)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Vectoriza los fragmentos y los guarda en Chroma.")
    ap.add_argument("--chunks", type=Path, default=CHUNKS)
    ap.add_argument("--db", type=Path, default=CHROMA_DIR)
    ap.add_argument("--model", default=MODEL_NAME)
    ap.add_argument("--reset", action="store_true", help="Borrar la base y reindexar todo")
    args = ap.parse_args(argv)

    from .embeddings import E5Embedder

    chunks = [json.loads(line) for line in args.chunks.open(encoding="utf-8")]
    print(f"Cargando el modelo {args.model} (la primera vez lo descarga, ~1 GB)...", flush=True)
    embedder = E5Embedder(args.model)

    too_long = sum(embedder.count_tokens(passage_text(c)) > MAX_TOKENS for c in chunks)
    print(f"Fragmentos que superan {MAX_TOKENS} tokens (se recortarán): {too_long} "
          f"de {len(chunks)} ({100 * too_long / len(chunks):.1f} %)")

    collection = get_collection(args.model, args.db, reset=args.reset)
    added = index_chunks(chunks, collection, embedder, log=lambda m: print(m, flush=True))
    print(f"\nListo: {added} fragmentos nuevos. La base tiene {collection.count()} en {args.db}")


if __name__ == "__main__":
    main()
