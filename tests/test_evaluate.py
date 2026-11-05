"""Las métricas de la evaluación, sin llamar a Groq."""

import pytest

from rag_informes.evaluate import (clave_in_text, evidence_pages, final_verdict, number_in_text,
                                   rescore_row, score, summarize)


@pytest.mark.parametrize("expected, text", [
    ("127.174", "BBVA tenía 127 174 empleados"),
    ("127.174", "127,174 employees"),
    ("12,7", "un CET1 del 12,70 %"),
    ("0,3", "pagó 0,30 € por acción"),
    ("19,3", "ROTE of 19.3%"),
])
def test_numbers_match_in_any_format(expected, text):
    assert number_in_text(expected, text)


@pytest.mark.parametrize("expected, text", [
    ("127.174", "125.916 empleados"),
    ("82.655", "100.870 empleados"),
])
def test_numbers_do_not_match_other_numbers(expected, text):
    assert not number_in_text(expected, text)


def test_numbers_in_a_table_row_are_separate():
    # "10.511 9.988" son dos cifras de una tabla, no el número 105119988
    assert number_in_text("10.511", "Resultado atribuido 10.511 9.988")
    assert number_in_text("125.916", "|Total|127.174 61.749 65.425| 125.916|")


def test_known_limitation_same_digits():
    # Al ignorar puntos y comas, "2,7" y "27" se confunden. Se asume: es raro y la
    # revisión de los fallos se hace igualmente a mano.
    assert number_in_text("2,7", "27 países")


def test_clave_alternatives_and_accents():
    assert clave_in_text("NYSE | Nueva York", "dejó de cotizar en Nueva York")
    assert clave_in_text("perímetro", "por cambios en el PERIMETRO de consolidación")
    assert not clave_in_text("Baa3", "rating BBB")


RET = [("BBVA", 189), ("BBVA", 5)]
Q = {"id": "bbva-08", "tipo": "cifra", "empresa": ["BBVA"], "paginas": [189], "claves": ["127.174"]}


def test_score_correct_answer():
    m = score(Q, "BBVA tenía 127.174 empleados [1].", RET, [("BBVA", 189)], False, [])
    assert m == {"busqueda": True, "cita": True, "claves": True, "rechazo": False,
                 "citas_inventadas": [], "acierto": True}


def test_score_wrong_number_and_wrong_citation():
    m = score(Q, "BBVA tenía 125.916 empleados [2].", RET, [("BBVA", 5)], False, [])
    assert m["busqueda"] is True and m["cita"] is False and m["acierto"] is False


def test_score_counts_evidence_pages_as_valid():
    # El dato también está en la p.15: citarla es correcto
    m = score(Q, "127.174 [1]", [("BBVA", 15)], [("BBVA", 15)], False, [], {("BBVA", 15)})
    assert m["busqueda"] is True and m["cita"] is True


def test_score_false_negative():
    m = score(Q, "No encuentro esta información en los informes disponibles.", RET, [], True, [])
    assert m["acierto"] is False and m["rechazo"] is True


def test_score_unanswerable_question():
    q = {"id": "none-01", "tipo": "sin_respuesta", "empresa": [], "paginas": [], "claves": []}
    assert score(q, "No encuentro...", RET, [], True, [])["acierto"] is True
    hallucination = score(q, "Ganó el Real Madrid.", RET, [], False, [])
    assert hallucination["acierto"] is False and hallucination["busqueda"] is None


PAGES = [
    {"company": "BBVA", "page": 5, "text": "beneficio atribuido de 10.511 millones"},
    {"company": "BBVA", "page": 340, "text": "Resultado atribuido 10.511 9.988"},
    {"company": "BBVA", "page": 8, "text": "ROTE cercano al 22%, eficiencia del 35%"},
    {"company": "Telefónica", "page": 3, "text": "10.511 clientes"},
]


def test_evidence_pages_only_for_specific_numbers_and_same_company():
    q = {"empresa": ["BBVA"], "paginas": [5], "claves": ["10.511"]}
    assert evidence_pages(q, PAGES) == {("BBVA", 5), ("BBVA", 340)}
    trivial = {"empresa": ["BBVA"], "paginas": [8], "claves": ["22", "35"]}
    assert evidence_pages(trivial, PAGES) == set()          # "22" es demasiado genérico
    text = {"empresa": ["BBVA"], "paginas": [8], "claves": ["ROTE"]}
    assert evidence_pages(text, PAGES) == set()             # solo claves numéricas


def test_rescore_reads_line_suffix_citations_and_evidence():
    q = {"id": "bbva-01", "tipo": "cifra", "empresa": ["BBVA"], "paginas": [5], "claves": ["10.511"]}
    row = {"id": "bbva-01", "tipo": "cifra", "respuesta": "10.511 M€【2†L1-L4】",
           "enviados": ["BBVA p.9", "BBVA p.340"], "fuentes": [], "metricas": {}}
    new = rescore_row(row, q, PAGES)
    assert new["fuentes"] == ["BBVA p.340"]
    assert new["metricas"]["cita"] is True and new["metricas"]["busqueda"] is True


def _row(i, tipo, acierto, rechazo):
    return {"id": i, "tipo": tipo, "metricas": {"busqueda": None, "cita": None, "acierto": acierto,
                                               "rechazo": rechazo, "citas_inventadas": []}}


def test_summary_lists_hallucinations_and_false_negatives():
    rows = [_row("none-01", "sin_respuesta", False, False), _row("fer-01", "idioma", False, True),
            _row("bbva-08", "cifra", True, False)]
    text = summarize(rows)
    assert "Alucinaciones (respondió a una pregunta sin respuesta): ['none-01']" in text
    assert "Falsos negativos" in text and "['fer-01']" in text
    assert "TOTAL" in text


def test_manual_review_overrides_final_verdict():
    rows = [_row("fer-04", "idioma", False, False), _row("bbva-08", "cifra", True, False)]
    review = {"fer-04": {"id": "fer-04", "acierto": True, "motivo": "redondeo correcto"}}
    assert final_verdict(rows[0], review) is True
    text = summarize(rows, review)
    assert "1/2 (50 %)" in text and "2/2 (100 %)" in text
