"""Fase 2 · Paso 1 · Trocear las páginas en fragmentos ("chunks").

Decisiones (ver NOTAS.md):
  * Cada fragmento pertenece a UNA sola página  -> la cita es siempre exacta.
  * Se corta por párrafos; si un párrafo es demasiado largo, por frases;
    y solo si una frase es enorme, por palabras.
  * Tamaño objetivo ~300 palabras con ~50 de solapamiento, porque el modelo de
    embeddings (multilingual-e5) solo lee unos 512 tokens (≈ 350 palabras).

Cómo funciona, paso a paso:
  1. Reconstruir párrafos. PyMuPDF a veces guarda cada LÍNEA como un bloque
     (pasa mucho en BBVA). Si un trozo no termina en . : ; ? ! la frase sigue
     en el siguiente, así que los unimos.
  2. Partir cada párrafo en "piezas": frases (texto) o grupos de filas (tablas).
  3. Empaquetar piezas en fragmentos sin pasar del tamaño máximo.
  4. Solapamiento: cada fragmento nuevo empieza repitiendo las últimas frases
     COMPLETAS del anterior (hasta ~50 palabras), así nunca se corta a mitad de frase.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher

from .text_clean import clean_table_markdown, is_soup_table, is_table, table_to_text

MAX_WORDS = 300
OVERLAP_WORDS = 50
MIN_WORDS = 15          # fragmentos más cortos (pies de foto, títulos sueltos) se descartan

_WORD_RE = re.compile(r"\w+")
_END_OF_SENTENCE = re.compile(r"[.!?:;…]['\"”’)]*$")
# Fin de frase: . ! ? seguido de espacio y mayúscula/número/comilla/viñeta
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÑ0-9“\"(¿¡•\-])")


def count_words(text: str) -> int:
    """Palabras "a lo bruto": secuencias de letras/números. 1.200 cuenta como 2."""
    return len(_WORD_RE.findall(text))


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    company: str
    year: int
    page: int
    text: str
    n_words: int
    has_table: bool

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- 1
_is_table = is_table
NEAR_DUPLICATE = 0.9   # dos fragmentos de la misma página con >= 90 % de coincidencia: sobra uno


def rebuild_paragraphs(page_text: str) -> list[str]:
    """Une los trozos separados por línea en blanco que en realidad son la misma frase.

    Además limpia las tablas (entidades HTML, negritas, celdas copiadas) y convierte en
    texto normal las que son "sopa de números".
    """
    blocks = [b.strip() for b in re.split(r"\n\s*\n", page_text) if b.strip()]
    paragraphs: list[str] = []
    for block in blocks:
        if _is_table(block):
            table = clean_table_markdown(block)
            if not is_soup_table(table):
                paragraphs.append(table)
                continue
            block = table_to_text(table)        # plan B: la tabla rota pasa a ser texto
            if not block:
                continue
        block = re.sub(r"\s*\n\s*", " ", block)  # saltos de línea internos -> espacio
        prev = paragraphs[-1] if paragraphs else None
        if prev is not None and not _is_table(prev) and not _END_OF_SENTENCE.search(prev):
            paragraphs[-1] = prev + " " + block
        else:
            paragraphs.append(block)
    return paragraphs


# --------------------------------------------------------------------------- 2
@dataclass
class _Piece:
    text: str
    n_words: int
    new_paragraph: bool   # empieza un párrafo nuevo (se une con \n\n en vez de espacio)
    is_table: bool


def _split_long(text: str, max_words: int) -> list[str]:
    """Último recurso: partir un texto enorme por palabras."""
    out, current, current_words = [], [], 0
    for w in text.split():
        n = count_words(w)              # "1.200" cuenta como 2: hay que mirar antes de añadir
        if current and current_words + n > max_words:
            out.append(" ".join(current))
            current, current_words = [], 0
        current.append(w)
        current_words += n
    if current:
        out.append(" ".join(current))
    return out


def _table_pieces(table: str, max_words: int) -> list[str]:
    """Una tabla cabe entera si puede; si no, se parte por filas repitiendo la cabecera."""
    if count_words(table) <= max_words:
        return [table]
    lines = table.splitlines()
    header = lines[:2] if len(lines) > 2 and set(lines[1].replace("|", "").strip()) <= set("-: ") else lines[:1]
    body = lines[len(header):]
    pieces, current = [], []
    for row in body:
        candidate = "\n".join(header + current + [row])
        if current and count_words(candidate) > max_words:
            pieces.append("\n".join(header + current))
            current = []
        current.append(row)
    if current:
        pieces.append("\n".join(header + current))
    # una fila gigante sola puede seguir pasándose: la partimos por palabras
    return [p for piece in pieces for p in (_split_long(piece, max_words) if count_words(piece) > max_words else [piece])]


def _pieces(paragraphs: list[str], max_words: int) -> list[_Piece]:
    pieces: list[_Piece] = []
    for para in paragraphs:
        if _is_table(para):
            parts, is_table = _table_pieces(para, max_words), True
        elif count_words(para) <= max_words:
            parts, is_table = [para], False
        else:
            sentences = _SENTENCE_SPLIT.split(para)
            parts = [s for sent in sentences
                     for s in (_split_long(sent, max_words) if count_words(sent) > max_words else [sent])]
            is_table = False
        for i, part in enumerate(parts):
            pieces.append(_Piece(part, count_words(part), new_paragraph=(i == 0 or is_table), is_table=is_table))
    return pieces


# --------------------------------------------------------------------------- 3 y 4
def _join(pieces: list[_Piece]) -> str:
    text = ""
    for i, p in enumerate(pieces):
        if i == 0:
            text = p.text
        else:
            text += ("\n\n" if p.new_paragraph else " ") + p.text
    return text


def _similar(a: list[str], b: list[str]) -> float:
    """Parecido entre dos listas de palabras, de 0 a 1 (proporción de palabras coincidentes en orden)."""
    sm = SequenceMatcher(None, a, b, autojunk=False)
    if sm.real_quick_ratio() < NEAR_DUPLICATE or sm.quick_ratio() < NEAR_DUPLICATE:
        return 0.0   # atajos baratos: si ni siquiera el límite superior llega, no calculamos
    return sm.ratio()


def chunk_page(page: dict, max_words: int = MAX_WORDS, overlap_words: int = OVERLAP_WORDS,
               min_words: int = MIN_WORDS) -> list[Chunk]:
    """Trocea UNA página (un dict de pages.jsonl) en fragmentos."""
    pieces = _pieces(rebuild_paragraphs(page["text"]), max_words)

    groups: list[list[_Piece]] = []
    current: list[_Piece] = []
    current_words = 0
    for piece in pieces:
        if current and current_words + piece.n_words > max_words:
            groups.append(current)
            # solapamiento: últimas frases completas (no tablas) que quepan en overlap_words
            tail: list[_Piece] = []
            tail_words = 0
            for prev in reversed(current):
                if prev.is_table or tail_words + prev.n_words > overlap_words:
                    break
                tail.insert(0, prev)
                tail_words += prev.n_words
            # el solapamiento nunca debe hacer que el nuevo fragmento se pase
            while tail and tail_words + piece.n_words > max_words:
                tail_words -= tail.pop(0).n_words
            current, current_words = list(tail), tail_words
        current.append(piece)
        current_words += piece.n_words
    if current:
        groups.append(current)

    chunks: list[Chunk] = []
    kept_words: list[list[str]] = []
    for group in groups:
        text = _join(group)
        n = count_words(text)
        if n < min_words:
            continue
        words = _WORD_RE.findall(text.lower())
        if any(_similar(words, prev) >= NEAR_DUPLICATE for prev in kept_words):
            continue   # casi idéntico a otro fragmento de esta página (tablas repetidas)
        kept_words.append(words)
        chunks.append(Chunk(
            chunk_id=f"{page['doc_id']}_p{page['page']}_c{len(chunks) + 1}",
            doc_id=page["doc_id"], company=page["company"], year=page["year"],
            page=page["page"], text=text, n_words=n,
            has_table=any(p.is_table for p in group),
        ))
    return chunks
