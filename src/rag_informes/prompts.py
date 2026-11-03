"""Fase 3 · Instrucciones para el LLM y formato de las citas.

Decisión de diseño: el LLM cita con NÚMEROS ([1], [2]...) que corresponden a los
fragmentos que le pasamos. Es nuestro código, no el LLM, quien convierte cada número
en "Empresa año, página N" usando los metadatos guardados. Así el LLM no puede
inventarse una página, y podemos comprobar que no cita fragmentos que no existen.
"""

from __future__ import annotations

import re

NO_ANSWER = "No encuentro esta información en los informes disponibles."

SYSTEM_PROMPT = f"""Eres un asistente de análisis financiero. Respondes preguntas sobre informes \
anuales de empresas cotizadas usando EXCLUSIVAMENTE los fragmentos que se te proporcionan.

Reglas:
1. Usa solo la información de los fragmentos. No añadas conocimientos propios ni suposiciones.
2. Cada dato o afirmación debe llevar la cita del fragmento del que sale: su número entre \
corchetes, por ejemplo [2]. Si sale de varios, [1][3].
3. Si los fragmentos no contienen la información para responder, responde exactamente: \
"{NO_ANSWER}" y nada más. Si solo permiten responder una parte, responde esa parte con sus \
citas e indica claramente qué no aparece.
4. Copia las cifras tal como aparecen, con sus unidades y el año al que se refieren. No hagas \
cálculos que no estén en los fragmentos.
5. Responde en el mismo idioma que la pregunta, aunque los fragmentos estén en otro idioma.
6. Sé conciso: ve al grano, en uno o pocos párrafos o en una lista breve.
7. Algunos fragmentos son tablas en formato Markdown (columnas separadas por |)."""


def build_user_message(question: str, hits: list[dict]) -> str:
    """Los fragmentos numerados, cada uno con su procedencia, y la pregunta al final."""
    blocks = [
        f"[{i}] ({h['company']} {h['year']}, página {h['page']})\n{h['text']}"
        for i, h in enumerate(hits, 1)
    ]
    return "Fragmentos:\n\n" + "\n\n".join(blocks) + f"\n\nPregunta: {question}"


# Corchetes normales [1] o "corchetes chinos" 【1】, que usan los modelos gpt-oss
_CITATION_RE = re.compile(r"[\[【](\d+(?:\s*[,;]\s*\d+)*)[\]】]")


def normalize_citations(answer: str) -> str:
    """【2】 -> [2], para que todas las respuestas citen igual."""
    return re.sub(r"【(\d+(?:\s*[,;]\s*\d+)*)】", r"[\1]", answer)


def parse_citations(answer: str) -> list[int]:
    """Números citados en la respuesta, sin repetir y en orden de aparición.

    Reconoce [1], [1][3], [1, 3], [1; 3] y lo mismo con 【】.
    """
    seen: list[int] = []
    for group in _CITATION_RE.findall(answer):
        for n in re.split(r"\s*[,;]\s*", group):
            if int(n) not in seen:
                seen.append(int(n))
    return seen


def is_no_answer(answer: str) -> bool:
    return answer.strip().strip('"«»').rstrip(".") == NO_ANSWER.rstrip(".")
