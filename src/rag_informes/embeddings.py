"""Fase 2 · Paso 2 · Convertir textos en vectores (embeddings).

Modelo: intfloat/multilingual-e5-base (gratuito, local, español + inglés, vectores de 768).

Detalles importantes de este modelo:
  * Prefijos: se entrenó con "query: " delante de las preguntas y "passage: " delante
    de los documentos. Si no se ponen, la búsqueda empeora.
  * Límite: lee como mucho 512 tokens; lo que pase de ahí se ignora sin avisar.
    Por eso troceamos a ~300 palabras.
  * Normalizamos los vectores (norma 1), así similitud = producto escalar = coseno.
"""

from __future__ import annotations

from typing import Protocol

MODEL_NAME = "intfloat/multilingual-e5-base"
MAX_TOKENS = 512


class Embedder(Protocol):
    """Lo que necesita el resto del código. Permite usar un modelo falso en las pruebas."""
    name: str

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


def passage_text(chunk: dict) -> str:
    """Texto que se vectoriza: una cabecera con empresa, año y página + el fragmento.

    La cabecera ayuda a que "¿qué riesgos menciona BBVA?" se acerque a fragmentos de BBVA.
    El texto que se guarda y se muestra es el original, sin cabecera.
    """
    return f"{chunk['company']} {chunk['year']}, página {chunk['page']}. {chunk['text']}"


class E5Embedder:
    """multilingual-e5 a través de sentence-transformers."""

    def __init__(self, model_name: str = MODEL_NAME, batch_size: int = 16):
        # Importación aquí dentro: cargar torch tarda unos segundos y las pruebas no lo necesitan
        from sentence_transformers import SentenceTransformer

        self.name = model_name
        self.batch_size = batch_size
        self.model = SentenceTransformer(model_name)  # la 1.ª vez lo descarga (~1 GB)
        self.model.max_seq_length = MAX_TOKENS

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            ["passage: " + t for t in texts],
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode("query: " + text, normalize_embeddings=True).tolist()

    def count_tokens(self, text: str) -> int:
        """Para comprobar cuántos fragmentos superan el límite de 512 tokens."""
        return len(self.model.tokenizer("passage: " + text)["input_ids"])
