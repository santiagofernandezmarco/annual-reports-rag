"""Fase 3 · Elegir qué fragmentos se envían al LLM.

Problemas vistos en la Fase 2 y cómo se tratan aquí:
  * Una tabla larga acaparaba los resultados (Ferrovial p.396 en 4 de 10 puestos)
    -> se buscan 20 candidatos y se envían 6, con un máximo de 2 por página.
  * Sin filtro, casi todo salía de BBVA (más fragmentos, y en español)
    -> si la pregunta nombra empresas, se busca en cada una por separado.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

from .vector_store import search

COMPANIES_FILE = Path(__file__).resolve().parents[2] / "data" / "companies.json"

N_CANDIDATES = 20
N_CONTEXT = 6
MAX_PER_PAGE = 2

# Frases que indican que hay que mirar todas las empresas aunque no se nombren
_ALL_COMPANIES = re.compile(
    r"\b(compar\w*|cada (una de las )?empresas?|las tres|todas las empresas|"
    r"each company|all (three )?companies|compare)\b"
)


def _normalize(text: str) -> str:
    """Minúsculas y sin tildes: 'Telefónica' y 'telefonica' cuentan igual."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def known_companies(path: Path = COMPANIES_FILE) -> list[str]:
    config = json.loads(path.read_text(encoding="utf-8"))
    return sorted({d["company"] for d in config["documents"]})


def detect_companies(question: str, companies: list[str]) -> list[str]:
    """Empresas que se nombran en la pregunta (o todas, si pide comparar)."""
    q = _normalize(question)
    named = [c for c in companies if re.search(rf"\b{re.escape(_normalize(c))}\b", q)]
    if len(named) < 2 and _ALL_COMPANIES.search(q):
        return companies
    return named


def select_diverse(hits: list[dict], k: int, max_per_page: int = MAX_PER_PAGE) -> list[dict]:
    """Los k mejores, sin pasar de max_per_page fragmentos de una misma página."""
    chosen, per_page = [], {}
    for h in hits:
        key = (h["doc_id"], h["page"])
        if per_page.get(key, 0) >= max_per_page:
            continue
        per_page[key] = per_page.get(key, 0) + 1
        chosen.append(h)
        if len(chosen) == k:
            break
    return chosen


def retrieve(collection, embedder, question: str, companies: list[str],
             k: int = N_CONTEXT, n_candidates: int = N_CANDIDATES,
             max_per_page: int = MAX_PER_PAGE) -> tuple[list[dict], list[str]]:
    """Devuelve (fragmentos elegidos, empresas detectadas en la pregunta)."""
    targets = detect_companies(question, companies)

    if len(targets) <= 1:
        company = targets[0] if targets else None
        hits = search(collection, embedder, question, k=n_candidates, company=company)
        return select_diverse(hits, k, max_per_page), targets

    # Varias empresas: mismo número de huecos para cada una
    per_company = math.ceil(k / len(targets))
    chosen = []
    for company in targets:
        hits = search(collection, embedder, question, k=n_candidates, company=company)
        chosen.extend(select_diverse(hits, per_company, max_per_page))
    return chosen, targets
