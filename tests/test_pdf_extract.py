"""Pruebas de la Fase 1 sobre un PDF sintético que imita un informe anual."""

import pymupdf
import pytest

from rag_informes.pdf_extract import clean_table_markdown, clean_text, extract_pdf, has_glued_words

HEADER = "Informe Anual 2025 · Empresa Demo S.A."


@pytest.fixture
def fake_report(tmp_path):
    path = tmp_path / "demo.pdf"
    doc = pymupdf.open()
    for i in range(1, 7):
        page = doc.new_page(width=595, height=842)  # A4
        page.insert_text((50, 30), HEADER, fontsize=9)
        page.insert_text((290, 820), str(i), fontsize=9)
        page.insert_text((50, 120), f"Capítulo {i}. El margen EBITDA mejoró en el ejercicio.", fontsize=11)
        page.insert_text((50, 140), "Los riesgos de tipos de interés se gestionan con", fontsize=11)
        page.insert_text((50, 154), "derivados de cobertura.", fontsize=11)
        if i == 3:
            # Tabla con bordes: 3 filas x 2 columnas
            rows = [("Concepto", "2025"), ("Ingresos", "1.200"), ("EBITDA", "300")]
            x0, y0, w, h = 50, 300, 150, 20
            for r, (a, b) in enumerate(rows):
                for c, val in enumerate((a, b)):
                    rect = pymupdf.Rect(x0 + c * w, y0 + r * h, x0 + (c + 1) * w, y0 + (r + 1) * h)
                    page.draw_rect(rect, color=(0, 0, 0), width=0.8)
                    page.insert_text((rect.x0 + 4, rect.y0 + 14), val, fontsize=10)
    doc.save(path)
    return path


def test_metadata_and_page_numbers(fake_report):
    pages = extract_pdf(fake_report, "Demo", 2025)
    assert [p.page for p in pages] == [1, 2, 3, 4, 5, 6]
    assert all(p.company == "Demo" and p.year == 2025 for p in pages)
    assert pages[0].doc_id == "Demo_2025"


def test_headers_and_page_numbers_removed(fake_report):
    pages = extract_pdf(fake_report, "Demo", 2025)
    for p in pages:
        assert HEADER not in p.text
        assert p.text.splitlines()[-1].strip() != str(p.page)
        assert "margen EBITDA" in p.text


def test_table_converted_to_markdown(fake_report):
    pages = extract_pdf(fake_report, "Demo", 2025)
    p3 = pages[2]
    assert p3.n_tables == 1
    assert "|" in p3.text and "Ingresos" in p3.text and "1.200" in p3.text
    assert pages[0].n_tables == 0


def test_skip_pages(fake_report):
    pages = extract_pdf(fake_report, "Demo", 2025, skip_pages=[1, 2])
    assert [p.page for p in pages] == [3, 4, 5, 6]


def test_clean_table_markdown_removes_br():
    md = "|Pasivos por&lt;br&gt;impuestos|Importe<br>a pagar|"
    assert clean_table_markdown(md) == "|Pasivos por impuestos|Importe a pagar|"


def test_has_glued_words():
    assert has_glued_words("|Acuerdoconjuntoenelquelaspartes|x|")
    assert not has_glued_words("|Internacionalización del negocio|2025|")


def test_clean_text_dehyphenates():
    assert clean_text("rentabi-\nlidad   neta\n\n\n\nfin") == "rentabilidad neta\n\nfin"
