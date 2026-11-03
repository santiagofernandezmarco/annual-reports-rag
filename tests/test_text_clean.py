"""Limpieza de tablas con casos sacados de los informes reales."""

from rag_informes.text_clean import clean_table_markdown, is_soup_table, table_to_text


def test_html_entities_bold_and_placeholders():
    md = "|Col1|**2025**|Col3|\n|---|---|---|\n|E5&amp;#45;2|**127**||"
    assert clean_table_markdown(md) == "||2025||\n|---|---|---|\n|E5-2|127||"


def test_merged_cell_copies_are_emptied():
    # Telefónica p.13: la misma frase copiada en 4 columnas
    s = "En ene-26 se llevó a cabo la exclusión de la cotización de la NYSE."
    md = f"|{s}|{s}|{s}|{s}|"
    assert clean_table_markdown(md) == f"|{s}||||"


def test_short_repeated_values_are_kept():
    md = "|Ingresos|100|100|—|—|"
    assert clean_table_markdown(md) == md          # "100" repetido puede ser un dato real


def test_cleaning_is_idempotent():
    md = "|A&amp;#45;B|**x y z w**|**x y z w**|"
    once = clean_table_markdown(md)
    assert clean_table_markdown(once) == once


def test_soup_table_detected_and_flattened():
    soup = " ".join(str(n) for n in range(60)) + " Swaps"
    md = f"|Instrumento|Valores|\n|---|---|\n|Interest Rate Swaps|{soup}|\n|Interest Rate Swaps|{soup}|"
    assert is_soup_table(md)
    text = table_to_text(md)
    assert text.count("Interest Rate Swaps") == 1 and text.count(soup) == 1


def test_normal_financial_table_is_not_soup():
    md = "|Concepto|2025|2024|\n|---|---|---|\n|Ingresos|1.200|1.100|\n|EBITDA|300|280|"
    assert not is_soup_table(md)
