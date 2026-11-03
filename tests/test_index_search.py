"""Indexación y búsqueda con un modelo FALSO, para no descargar 1 GB en cada prueba.

El modelo falso convierte cada texto en un vector de "palabras clave": textos que
comparten palabras quedan cerca. No entiende significados, pero basta para comprobar
que la tubería (vectorizar -> guardar -> buscar) funciona.
"""

import math

import pytest

chromadb = pytest.importorskip("chromadb")

from rag_informes.embeddings import passage_text
from rag_informes.index import index_chunks
from rag_informes.vector_store import get_collection, search

VOCAB = ["riesgo", "interés", "deuda", "empleados", "clima", "ingresos", "bbva", "ferrovial"]


class FakeEmbedder:
    name = "fake-model"

    def _vec(self, text):
        t = text.lower()
        v = [t.count(w) + 0.01 for w in VOCAB]
        norm = math.sqrt(sum(x * x for x in v))
        return [x / norm for x in v]

    def embed_passages(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


def _chunk(i, company, page, text):
    return {"chunk_id": f"{company}_2025_p{page}_c{i}", "doc_id": f"{company}_2025", "company": company,
            "year": 2025, "page": page, "text": text, "n_words": len(text.split()), "has_table": False}


CHUNKS = [
    _chunk(1, "BBVA", 10, "El riesgo de tipo de interés afecta al margen. Riesgo de interés."),
    _chunk(1, "BBVA", 20, "La plantilla de empleados creció en 2025."),
    _chunk(1, "Ferrovial", 30, "La deuda neta se redujo. Deuda y más deuda."),
    _chunk(2, "Ferrovial", 31, "Ferrovial analiza el riesgo climático y el clima."),
]


@pytest.fixture
def collection(tmp_path):
    return get_collection("fake-model", tmp_path / "chroma")


def test_passage_text_has_header():
    assert passage_text(CHUNKS[0]).startswith("BBVA 2025, página 10. El riesgo")


def test_index_is_resumable(collection):
    emb = FakeEmbedder()
    assert index_chunks(CHUNKS[:2], collection, emb, log=lambda m: None) == 2
    assert index_chunks(CHUNKS, collection, emb, log=lambda m: None) == 2   # solo los 2 nuevos
    assert collection.count() == 4


def test_index_updates_changed_and_deletes_obsolete(collection):
    emb = FakeEmbedder()
    index_chunks(CHUNKS, collection, emb, log=lambda m: None)
    changed = dict(CHUNKS[2], text="La deuda neta bajó mucho.")
    new_list = [CHUNKS[0], CHUNKS[1], changed]             # CHUNKS[3] desaparece
    assert index_chunks(new_list, collection, emb, log=lambda m: None) == 1   # solo el cambiado
    assert collection.count() == 3
    stored = collection.get(ids=[changed["chunk_id"]], include=["documents"])
    assert stored["documents"] == ["La deuda neta bajó mucho."]


def test_search_finds_the_right_chunk_with_citation(collection):
    emb = FakeEmbedder()
    index_chunks(CHUNKS, collection, emb, log=lambda m: None)
    hits = search(collection, emb, "deuda neta", k=2)
    assert hits[0]["chunk_id"] == "Ferrovial_2025_p30_c1"
    assert (hits[0]["company"], hits[0]["year"], hits[0]["page"]) == ("Ferrovial", 2025, 30)
    assert hits[0]["similarity"] > hits[1]["similarity"]


def test_search_filter_by_company(collection):
    emb = FakeEmbedder()
    index_chunks(CHUNKS, collection, emb, log=lambda m: None)
    hits = search(collection, emb, "riesgo", k=4, company="Ferrovial")
    assert hits and all(h["company"] == "Ferrovial" for h in hits)


def test_changing_model_requires_reset(tmp_path):
    get_collection("modelo-A", tmp_path / "chroma")
    with pytest.raises(SystemExit):
        get_collection("modelo-B", tmp_path / "chroma")
    get_collection("modelo-B", tmp_path / "chroma", reset=True)  # con --reset sí deja
