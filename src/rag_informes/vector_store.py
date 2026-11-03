"""Acceso a la base de datos vectorial (Chroma), guardada en data/chroma/.

Una "colección" de Chroma es como una tabla: cada fila tiene
  id (chunk_id) · vector · texto original · metadatos (empresa, año, página...).
Usamos la distancia del coseno: distancia = 1 - similitud.
"""

from __future__ import annotations

from pathlib import Path

CHROMA_DIR = Path(__file__).resolve().parents[2] / "data" / "chroma"
COLLECTION = "informes"


def get_collection(model_name: str, path: Path = CHROMA_DIR, reset: bool = False):
    import chromadb

    client = chromadb.PersistentClient(path=str(path))
    if reset:
        try:
            client.delete_collection(COLLECTION)
        except Exception:
            pass  # no existía
    collection = client.get_or_create_collection(
        COLLECTION,
        configuration={"hnsw": {"space": "cosine"}},
        metadata={"embedding_model": model_name},
    )
    stored = (collection.metadata or {}).get("embedding_model")
    if stored != model_name:
        raise SystemExit(
            f"La base vectorial se creó con el modelo '{stored}' y ahora usas '{model_name}'.\n"
            "Los vectores de modelos distintos no son comparables: vuelve a indexar con --reset."
        )
    return collection


def search(collection, embedder, question: str, k: int = 5, company: str | None = None) -> list[dict]:
    """Devuelve los k fragmentos más cercanos a la pregunta, del más al menos parecido."""
    result = collection.query(
        query_embeddings=[embedder.embed_query(question)],
        n_results=k,
        where={"company": company} if company else None,
    )
    hits = []
    for chunk_id, text, meta, dist in zip(result["ids"][0], result["documents"][0],
                                          result["metadatas"][0], result["distances"][0]):
        hits.append({"chunk_id": chunk_id, "text": text, "similarity": 1 - dist, **meta})
    return hits
