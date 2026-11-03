"""Fase 3 · El asistente: pregunta -> fragmentos -> Groq -> respuesta con citas.

Uso:
    python -m rag_informes.ask "¿Qué riesgos de tipos de interés menciona BBVA?"
    python -m rag_informes.ask "..." --show-context      # ver también los fragmentos enviados
    python -m rag_informes.ask "..." --model openai/gpt-oss-120b
"""

from __future__ import annotations

import argparse
import textwrap
import time
from dataclasses import dataclass, field

from .prompts import (NO_ANSWER, SYSTEM_PROMPT, build_user_message, is_no_answer,
                      normalize_citations, parse_citations)
from .retrieval import N_CONTEXT, known_companies, retrieve


@dataclass
class Answer:
    question: str
    text: str
    hits: list[dict]                       # fragmentos enviados al LLM, en orden ([1], [2]...)
    companies: list[str]                   # empresas detectadas en la pregunta
    cited: list[int] = field(default_factory=list)
    invalid: list[int] = field(default_factory=list)   # números citados que no existen
    no_answer: bool = False
    seconds: float = 0.0

    @property
    def sources(self) -> list[tuple[int, dict]]:
        return [(n, self.hits[n - 1]) for n in self.cited if 1 <= n <= len(self.hits)]


def answer_question(question: str, collection, embedder, llm, companies: list[str],
                    k: int = N_CONTEXT) -> Answer:
    t0 = time.time()
    hits, detected = retrieve(collection, embedder, question, companies, k=k)
    if not hits:
        return Answer(question, NO_ANSWER, [], detected, no_answer=True)

    text = normalize_citations(llm.complete(SYSTEM_PROMPT, build_user_message(question, hits)))
    cited = parse_citations(text)
    return Answer(
        question=question, text=text, hits=hits, companies=detected,
        cited=cited, invalid=[n for n in cited if not 1 <= n <= len(hits)],
        no_answer=is_no_answer(text), seconds=time.time() - t0,
    )


def _print_answer(a: Answer, show_context: bool, model: str) -> None:
    print(f"\nPregunta: {a.question}")
    if a.companies:
        print(f"Empresas detectadas: {', '.join(a.companies)}")
    print(f"\nRespuesta ({model}, {a.seconds:.1f} s):\n")
    # En la terminal las negritas de Markdown (**) solo estorban; cada línea se ajusta por separado
    for line in a.text.replace("**", "").splitlines():
        bullet = line.lstrip().startswith(("-", "•"))
        print(textwrap.fill(line.strip(), 100, subsequent_indent="  " if bullet else "") if line.strip() else "")

    if a.sources:
        print("\nFuentes:")
        for n, h in a.sources:
            print(f"  [{n}] {h['company']} {h['year']}, página {h['page']}")
    if a.invalid:
        print(f"\n⚠ La respuesta cita fragmentos que no existen: {a.invalid}. No te fíes de esas citas.")
    if not a.no_answer and not a.cited:
        print("\n⚠ La respuesta no cita ninguna fuente: tómala con cautela.")

    if show_context:
        print("\nFragmentos enviados al modelo:")
        for i, h in enumerate(a.hits, 1):
            mark = "✓ citado" if i in a.cited else "  no citado"
            print(f"\n[{i}] {h['company']} {h['year']}, página {h['page']} · "
                  f"similitud {h['similarity']:.3f} · {mark}")
            print(textwrap.indent(textwrap.fill(h["text"][:300] + "…", 100), "    "))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Pregunta a los informes anuales.")
    ap.add_argument("question", help="Tu pregunta, entre comillas")
    ap.add_argument("--k", type=int, default=N_CONTEXT, help="Fragmentos que se envían al modelo")
    ap.add_argument("--model", help="Modelo de Groq (por defecto openai/gpt-oss-120b)")
    ap.add_argument("--show-context", action="store_true", help="Mostrar los fragmentos enviados")
    args = ap.parse_args(argv)

    from .embeddings import MODEL_NAME, E5Embedder
    from .llm import GroqLLM
    from .vector_store import get_collection

    llm = GroqLLM(args.model)
    embedder = E5Embedder(MODEL_NAME)
    collection = get_collection(MODEL_NAME)
    answer = answer_question(args.question, collection, embedder, llm, known_companies(), k=args.k)
    _print_answer(answer, args.show_context, llm.name)


if __name__ == "__main__":
    main()
