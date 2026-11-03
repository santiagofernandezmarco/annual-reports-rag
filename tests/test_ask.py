"""Fase 3 sin gastar cupo de Groq: un LLM falso que responde lo que le digamos."""

import math

import pytest

pytest.importorskip("chromadb")

from rag_informes.ask import answer_question
from rag_informes.index import index_chunks
from rag_informes.prompts import NO_ANSWER, build_user_message, is_no_answer, parse_citations
from rag_informes.retrieval import detect_companies, retrieve, select_diverse
from rag_informes.vector_store import get_collection

COMPANIES = ["BBVA", "Ferrovial", "Telefónica"]
VOCAB = ["riesgo", "interés", "deuda", "empleados", "clima", "ingresos"]


class FakeEmbedder:
    name = "fake-model"

    def _vec(self, text):
        t = text.lower()
        v = [t.count(w) + 0.01 for w in VOCAB]
        n = math.sqrt(sum(x * x for x in v))
        return [x / n for x in v]

    def embed_passages(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


class FakeLLM:
    name = "fake-llm"

    def __init__(self, reply):
        self.reply = reply
        self.last_user = None

    def complete(self, system, user):
        self.last_user = user
        return self.reply


def _chunk(company, page, i, text):
    return {"chunk_id": f"{company}_2025_p{page}_c{i}", "doc_id": f"{company}_2025",
            "company": company, "year": 2025, "page": page, "text": text,
            "n_words": len(text.split()), "has_table": False}


CHUNKS = (
    [_chunk("BBVA", 403, i, f"Riesgo de interés número {i}. Riesgo de interés.") for i in range(1, 5)]
    + [_chunk("BBVA", 189, 1, "Empleados del grupo: 127.174 empleados.")]
    + [_chunk("Telefónica", 50, 1, "Telefónica gestiona el riesgo de interés con coberturas.")]
    + [_chunk("Ferrovial", 392, 1, "Ferrovial: riesgo de interés en su deuda.")]
)


@pytest.fixture
def collection(tmp_path):
    col = get_collection("fake-model", tmp_path / "chroma")
    index_chunks(CHUNKS, col, FakeEmbedder(), log=lambda m: None)
    return col


# --- detección de empresas -------------------------------------------------
def test_detect_companies_ignores_accents_and_case():
    assert detect_companies("¿Qué dice telefonica sobre el clima?", COMPANIES) == ["Telefónica"]
    assert detect_companies("Compara BBVA y Ferrovial", COMPANIES) == ["BBVA", "Ferrovial"]
    assert detect_companies("¿Cuántos empleados hay?", COMPANIES) == []


def test_comparison_words_mean_all_companies():
    assert detect_companies("Compara el riesgo de interés de las tres empresas", COMPANIES) == COMPANIES


# --- selección de fragmentos -----------------------------------------------
def test_select_diverse_limits_chunks_per_page():
    hits = [{"doc_id": "A", "page": 1}] * 5 + [{"doc_id": "A", "page": 2}] * 5
    chosen = select_diverse(hits, k=4, max_per_page=2)
    assert [h["page"] for h in chosen] == [1, 1, 2, 2]


def test_retrieve_one_company_filters(collection):
    hits, companies = retrieve(collection, FakeEmbedder(), "riesgo de interés en Ferrovial", COMPANIES)
    assert companies == ["Ferrovial"] and {h["company"] for h in hits} == {"Ferrovial"}


def test_retrieve_comparison_takes_every_company(collection):
    hits, _ = retrieve(collection, FakeEmbedder(), "Compara el riesgo de interés de las tres empresas",
                       COMPANIES, k=6)
    assert {h["company"] for h in hits} == set(COMPANIES)


def test_retrieve_max_two_per_page(collection):
    hits, _ = retrieve(collection, FakeEmbedder(), "riesgo de interés BBVA", COMPANIES, k=6)
    assert sum(h["page"] == 403 for h in hits) == 2


# --- prompt y citas -------------------------------------------------------
def test_user_message_numbers_fragments_with_source():
    msg = build_user_message("¿Pregunta?", [CHUNKS[4]])
    assert "[1] (BBVA 2025, página 189)\nEmpleados del grupo" in msg
    assert msg.endswith("Pregunta: ¿Pregunta?")


@pytest.mark.parametrize("text, expected", [
    ("Dato [1] y otro [3].", [1, 3]),
    ("Dato [1][3] y [1].", [1, 3]),
    ("Dato [2, 4] y [1; 2].", [2, 4, 1]),
    ("Sin citas.", []),
    ("Estilo gpt-oss【2】 y 【1】【2】.", [2, 1]),
])
def test_parse_citations(text, expected):
    assert parse_citations(text) == expected


def test_fullwidth_citations_are_normalized_and_mapped(collection):
    llm = FakeLLM("BBVA tiene 127.174 empleados【1】.")
    a = answer_question("¿Cuántos empleados tiene BBVA?", collection, FakeEmbedder(), llm, COMPANIES)
    assert a.text == "BBVA tiene 127.174 empleados[1]."
    assert [(n, h["page"]) for n, h in a.sources] == [(1, 189)]


def test_no_answer_detection():
    assert is_no_answer(NO_ANSWER)
    assert is_no_answer(f"«{NO_ANSWER}»")
    assert not is_no_answer("BBVA tiene 127.174 empleados [1].")


# --- de principio a fin ---------------------------------------------------
def test_answer_maps_citations_to_pages(collection):
    llm = FakeLLM("BBVA tiene 127.174 empleados [1].")
    a = answer_question("¿Cuántos empleados tiene BBVA?", collection, FakeEmbedder(), llm, COMPANIES)
    assert a.hits[0]["page"] == 189
    assert [(n, h["page"]) for n, h in a.sources] == [(1, 189)]
    assert not a.invalid and not a.no_answer
    assert "(BBVA 2025, página 189)" in llm.last_user


def test_answer_flags_invented_citations(collection):
    llm = FakeLLM("Dato inventado [9].")
    a = answer_question("riesgo de interés", collection, FakeEmbedder(), llm, COMPANIES)
    assert a.invalid == [9] and a.sources == []


def test_answer_detects_no_answer(collection):
    a = answer_question("¿Quién ganó la liga?", collection, FakeEmbedder(), FakeLLM(NO_ANSWER), COMPANIES)
    assert a.no_answer
