"""La ingesta guarda cada informe por separado y se salta los ya procesados."""

import json

import pymupdf

from rag_informes import ingest


def _make_pdf(path, n_pages=3):
    doc = pymupdf.open()
    for i in range(n_pages):
        doc.new_page().insert_text((50, 120), f"Texto de la página {i + 1}.", fontsize=11)
    doc.save(path)


def test_ingest_resumes(tmp_path, capsys):
    raw = tmp_path / "raw"
    raw.mkdir()
    _make_pdf(raw / "a.pdf")
    _make_pdf(raw / "b.pdf", n_pages=2)
    config = tmp_path / "companies.json"
    config.write_text(json.dumps({"documents": [
        {"file": "a.pdf", "company": "A", "year": 2025},
        {"file": "b.pdf", "company": "B", "year": 2025},
    ]}), encoding="utf-8")
    out = tmp_path / "processed" / "pages.jsonl"
    argv = ["--config", str(config), "--raw", str(raw), "--out", str(out)]

    ingest.main(argv)
    assert len(out.read_text(encoding="utf-8").splitlines()) == 5
    assert (tmp_path / "processed" / "docs" / "A_2025.jsonl").exists()

    capsys.readouterr()
    ingest.main(argv)  # segunda vez: no reprocesa nada
    assert "Procesando" not in capsys.readouterr().out
    assert len(out.read_text(encoding="utf-8").splitlines()) == 5
