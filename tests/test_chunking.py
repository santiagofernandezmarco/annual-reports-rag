"""Pruebas del troceado (Fase 2, paso 1)."""

import re

from rag_informes.chunking import chunk_page, count_words, rebuild_paragraphs


def _page(text, page=7):
    return {"doc_id": "Demo_2025", "company": "Demo", "year": 2025, "page": page, "text": text}


def _sentence(i, n_words=20):
    return "Frase número " + str(i) + " " + " ".join(["palabra"] * (n_words - 3)) + "."


def test_rebuild_joins_lines_of_the_same_sentence():
    text = "Durante 2025 las oportunidades\n\nde negocio crecieron.\n\nOtro párrafo."
    assert rebuild_paragraphs(text) == [
        "Durante 2025 las oportunidades de negocio crecieron.",
        "Otro párrafo.",
    ]


def test_short_page_is_one_chunk_with_metadata():
    chunks = chunk_page(_page(" ".join(_sentence(i) for i in range(3))))
    assert len(chunks) == 1
    c = chunks[0]
    assert (c.company, c.year, c.page, c.chunk_id) == ("Demo", 2025, 7, "Demo_2025_p7_c1")


def test_no_chunk_exceeds_max_and_no_sentence_is_cut():
    text = "\n\n".join(_sentence(i) for i in range(60))      # 60 frases de 20 palabras
    chunks = chunk_page(_page(text), max_words=100, overlap_words=30)
    assert len(chunks) > 1
    for c in chunks:
        assert c.n_words <= 100
        assert c.text.startswith("Frase número") and c.text.endswith(".")


def test_overlap_repeats_whole_sentences():
    text = "\n\n".join(_sentence(i) for i in range(20))
    chunks = chunk_page(_page(text), max_words=100, overlap_words=45)
    first_sentences = re.findall(r"Frase número (\d+)", chunks[0].text)
    second_sentences = re.findall(r"Frase número (\d+)", chunks[1].text)
    # 45 palabras de solapamiento = 2 frases de 20
    assert second_sentences[:2] == first_sentences[-2:]


def test_no_text_is_lost():
    sentences = [_sentence(i) for i in range(40)]
    chunks = chunk_page(_page("\n\n".join(sentences)), max_words=100, overlap_words=30)
    joined = " ".join(c.text for c in chunks)
    for s in sentences:
        assert s in joined


def test_big_table_split_by_rows_keeps_header():
    rows = [f"|Concepto {i}|{' '.join(['dato'] * 10)}|" for i in range(30)]
    table = "|Concepto|Valor|\n|---|---|\n" + "\n".join(rows)
    chunks = chunk_page(_page(table), max_words=100, overlap_words=30)
    assert len(chunks) > 1
    for c in chunks:
        assert c.has_table and c.n_words <= 100
        assert c.text.startswith("|Concepto|Valor|\n|---|---|")


def test_numbers_counting_double_never_exceed_max():
    # una "frase" enorme sin puntos y llena de números como 1.200 (cuentan 2 palabras)
    text = " ".join(["1.200 ventas"] * 400)
    chunks = chunk_page(_page(text), max_words=100, overlap_words=20)
    assert chunks and all(c.n_words <= 100 for c in chunks)


def test_tiny_fragments_are_dropped():
    assert chunk_page(_page("JFK Airport. New York, U.S.")) == []


def test_count_words():
    # Ingresos, de, 1, 200, M, 5 -> los números con punto cuentan doble (aprox. a tokens)
    assert count_words("Ingresos de 1.200 M€ (+5 %)") == 6
