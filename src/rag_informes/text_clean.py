"""Limpieza del texto de tablas en Markdown (sin dependencias: se usa en la Fase 1 y en la 2).

Problemas que corrige, todos vistos en los informes reales:
  * <br> dentro de las celdas (saltos de línea).
  * Entidades HTML: "&amp;#45;" en vez de "-" (a veces escapadas dos veces).
  * Marcas de negrita "**...**" y cabeceras vacías inventadas "Col3", "Col4"...
  * Celdas combinadas que PyMuPDF COPIA en cada columna: la misma frase 3-4 veces
    en una fila. Dejamos la primera y vaciamos las copias.
Y detecta tablas que no tienen arreglo ("sopa de números"): una celda con decenas
de cifras amontonadas. Esas se pasan a texto normal (plan B).
"""

from __future__ import annotations

import html
import re

_BR_RE = re.compile(r"\s*(<br\s*/?>|&lt;br\s*/?&gt;)\s*", re.IGNORECASE)
_COL_PLACEHOLDER = re.compile(r"^Col\d+$")
_WORD_RE = re.compile(r"\w+")
_GLUED_RE = re.compile(r"[^\W\d_]{25,}")   # 25+ letras seguidas: palabras sin espacios

MIN_WORDS_REPEATED_CELL = 4    # celdas más cortas ("2025", "—") pueden repetirse legítimamente
SOUP_MIN_WORDS = 40
SOUP_MIN_DIGIT_SHARE = 0.6


def is_table(block: str) -> bool:
    lines = [l for l in block.splitlines() if l.strip()]
    return bool(lines) and all(l.lstrip().startswith("|") for l in lines)


def _split_row(line: str) -> list[str]:
    """'|a||c|' -> ['a', '', 'c']. Quita solo UNA barra a cada lado (no las celdas vacías finales)."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def has_glued_words(text: str) -> bool:
    return bool(_GLUED_RE.search(text))


def _clean_cell(cell: str) -> str:
    cell = html.unescape(html.unescape(cell))          # "&amp;#45;" -> "&#45;" -> "-"
    cell = _BR_RE.sub(" ", cell).replace("**", "")
    cell = re.sub(r"\s+", " ", cell).strip()
    return "" if _COL_PLACEHOLDER.match(cell) else cell


def clean_table_markdown(md: str) -> str:
    """Limpia una tabla Markdown fila a fila. Es idempotente: aplicarla dos veces no cambia nada."""
    md = _BR_RE.sub(" ", md)
    out = []
    for line in md.strip().splitlines():
        if not line.strip().startswith("|"):
            out.append(line)
            continue
        cells = [_clean_cell(c) for c in _split_row(line)]
        seen = set()
        for i, c in enumerate(cells):
            if len(_WORD_RE.findall(c)) >= MIN_WORDS_REPEATED_CELL:
                if c in seen:
                    cells[i] = ""          # copia de una celda combinada
                seen.add(c)
        out.append("|" + "|".join(cells) + "|")
    return "\n".join(out).strip()


def is_soup_table(md: str) -> bool:
    """Tabla mal detectada: alguna celda con >= 40 'palabras' y >= 60 % de ellas números."""
    for line in md.splitlines():
        if not line.strip().startswith("|"):
            continue
        for cell in _split_row(line):
            words = _WORD_RE.findall(cell)
            if len(words) >= SOUP_MIN_WORDS and sum(w.isdigit() for w in words) / len(words) >= SOUP_MIN_DIGIT_SHARE:
                return True
    return False


def table_to_text(md: str) -> str:
    """Plan B para una tabla sin arreglo: sus celdas como texto, cada contenido una sola vez."""
    seen, parts = set(), []
    for line in md.splitlines():
        if set(line.replace("|", "").strip()) <= set("-: "):
            continue   # separador |---|---|
        for cell in _split_row(line):
            cell = _clean_cell(cell)
            if cell and cell not in seen:
                seen.add(cell)
                parts.append(cell)
    return " ".join(parts)
