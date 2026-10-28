"""Fase 1 · Extraer y limpiar el texto de un informe anual en PDF.

Idea general
------------
1. Leemos cada página como una lista de *bloques* de texto con su posición (bbox).
2. Detectamos cabeceras y pies de página: bloques situados en la franja superior
   o inferior de la página que se REPITEN en muchas páginas (comparando el texto
   con los dígitos normalizados, para que "Página 3" y "Página 4" cuenten igual).
3. Quitamos también los números de página sueltos.
4. Las tablas suelen salir desordenadas como texto plano. Si PyMuPDF las detecta,
   sustituimos sus bloques por la tabla en Markdown y marcamos la página.
5. Devolvemos una lista de `PageText` con los metadatos que necesitaremos para
   citar: empresa, año, página física del PDF y etiqueta de página impresa.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path

import pymupdf

# Fracción de la altura de página considerada "franja" de cabecera / pie.
MARGIN_FRACTION = 0.08
# Un texto en la franja se considera cabecera/pie si aparece en al menos
# este porcentaje de páginas (y en un mínimo de 3).
REPEAT_THRESHOLD = 0.3

_PAGE_NUMBER_RE = re.compile(
    r"^\s*(p[áa]g(ina)?\.?|page)?\s*\d{1,4}(\s*(/|de|of)\s*\d{1,4})?\s*$",
    re.IGNORECASE,
)


@dataclass
class PageText:
    company: str
    year: int
    page: int                 # número de página física en el PDF (desde 1)
    page_label: str           # número impreso en el documento, si el PDF lo define
    text: str
    n_tables: int = 0
    removed_lines: list[str] = field(default_factory=list)  # para depurar la limpieza

    @property
    def doc_id(self) -> str:
        return f"{self.company}_{self.year}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["doc_id"] = self.doc_id
        return d


def _normalize(text: str) -> str:
    """Texto comparable entre páginas: minúsculas, dígitos -> '#', espacios colapsados."""
    text = re.sub(r"\d+", "#", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _in_margin(bbox, page_height: float) -> bool:
    _, y0, _, y1 = bbox
    return y1 <= page_height * MARGIN_FRACTION or y0 >= page_height * (1 - MARGIN_FRACTION)


def clean_text(text: str) -> str:
    """Limpieza ligera del cuerpo: guiones de partición, espacios y saltos."""
    text = text.replace("­", "")                      # guion blando
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)            # pala-\nbra -> palabra
    text = re.sub(r"[ \t ]+", " ", text)               # espacios múltiples
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)                  # como mucho una línea en blanco
    return text.strip()


def _overlaps(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _page_blocks(page: pymupdf.Page) -> list[tuple[tuple, str]]:
    """Bloques de texto (bbox, texto) en el orden natural del PDF; se ignoran imágenes."""
    out = []
    for x0, y0, x1, y1, text, _no, btype in page.get_text("blocks"):
        if btype == 0 and text.strip():
            out.append(((x0, y0, x1, y1), text))
    return out


def _find_tables(page: pymupdf.Page) -> list[tuple[tuple, str]]:
    """Tablas detectadas como (bbox, markdown). Si falla la detección, lista vacía."""
    try:
        found = page.find_tables()
    except Exception:  # la detección de tablas puede fallar en PDF raros
        return []
    tables = []
    for t in found.tables:
        md = t.to_markdown(clean=True).strip()
        if md:
            tables.append((tuple(t.bbox), md))
    return tables


def find_repeated_margin_lines(doc: pymupdf.Document, skip: set[int]) -> set[str]:
    """Textos normalizados que aparecen en la franja de cabecera/pie de muchas páginas."""
    counts: Counter[str] = Counter()
    n_pages = 0
    for page in doc:
        if page.number + 1 in skip:
            continue
        n_pages += 1
        seen_here = set()
        for bbox, text in _page_blocks(page):
            if _in_margin(bbox, page.rect.height):
                seen_here.add(_normalize(text))
        counts.update(seen_here)
    min_count = max(3, int(n_pages * REPEAT_THRESHOLD))
    return {t for t, c in counts.items() if c >= min_count and t}


def extract_pdf(
    path: str | Path,
    company: str,
    year: int,
    skip_pages: list[int] | None = None,
    tables_as_markdown: bool = True,
) -> list[PageText]:
    """Extrae y limpia todas las páginas de un PDF."""
    skip = set(skip_pages or [])
    pages: list[PageText] = []

    with pymupdf.open(path) as doc:
        repeated = find_repeated_margin_lines(doc, skip)

        for page in doc:
            page_no = page.number + 1
            if page_no in skip:
                continue

            blocks = _page_blocks(page)
            tables = _find_tables(page) if tables_as_markdown else []
            removed: list[str] = []
            parts: list[str] = []
            placed_tables: set[int] = set()

            for bbox, text in blocks:
                # 1) cabeceras/pies repetidos y números de página sueltos
                if _in_margin(bbox, page.rect.height) and (
                    _normalize(text) in repeated or _PAGE_NUMBER_RE.match(text)
                ):
                    removed.append(text.strip())
                    continue
                if _PAGE_NUMBER_RE.match(text):
                    removed.append(text.strip())
                    continue

                # 2) bloques dentro de una tabla -> se sustituye por la tabla en Markdown
                table_idx = next((i for i, (tb, _) in enumerate(tables) if _overlaps(bbox, tb)), None)
                if table_idx is not None:
                    if table_idx not in placed_tables:
                        parts.append("\n" + tables[table_idx][1] + "\n")
                        placed_tables.add(table_idx)
                    continue

                parts.append(text)

            # Tablas que no solapaban ningún bloque de texto: al final
            for i, (_, md) in enumerate(tables):
                if i not in placed_tables:
                    parts.append("\n" + md + "\n")

            pages.append(
                PageText(
                    company=company,
                    year=year,
                    page=page_no,
                    page_label=page.get_label() or str(page_no),
                    text=clean_text("\n".join(parts)),
                    n_tables=len(tables),
                    removed_lines=removed,
                )
            )
    return pages
