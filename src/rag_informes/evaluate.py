"""Fase 4 · Evaluación: pasa todas las preguntas de eval/preguntas.yaml por el asistente y mide.

Métricas por pregunta (automáticas):
  * busqueda   ¿Está alguna página válida entre los fragmentos enviados al LLM?
  * cita       ¿Cita la respuesta alguna página válida?
  * claves     ¿Aparecen en la respuesta todos los datos clave? (números sin puntos/comas)
  * rechazo    ¿Ha respondido "No encuentro esta información..."?
  * acierto    Preguntas normales: claves presentes y sin rechazar.
               Preguntas sin respuesta: haber rechazado (si no, es una ALUCINACIÓN).
               Sin claves (descriptivas): queda para revisión manual (None).

"Páginas válidas" = las declaradas en la pregunta + las páginas de esa empresa cuyo texto
contiene los datos clave numéricos (un mismo dato suele repetirse en varias páginas:
carta del presidente, resumen, cuentas...). Solo se amplía con claves numéricas
"específicas" (3+ cifras y que no sean un año), para no dar por buena cualquier página
que contenga, por ejemplo, un "22".

Revisión manual: eval/revision_<label>.yaml (se genera con --plantilla-revision). Ahí una
persona puede corregir el acierto automático de una pregunta explicando el motivo, sin
tocar el conjunto de preguntas congelado.

Uso:
    python -m rag_informes.evaluate --label base                  # ejecutar (reanudable)
    python -m rag_informes.evaluate --label base --rescore        # recalcular sin llamar a Groq
    python -m rag_informes.evaluate --label base --plantilla-revision
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "eval" / "preguntas.yaml"
RESULTS_DIR = ROOT / "eval" / "resultados"
PAGES = ROOT / "data" / "processed" / "pages.jsonl"

TYPE_ORDER = ["cifra", "idioma", "trampa", "descriptiva", "comparacion", "sin_respuesta"]


# ------------------------------------------------------------------ comprobación de claves
def _normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def _is_number(s: str) -> bool:
    return bool(re.fullmatch(r"[\d.,\s%]+", s.strip())) and any(c.isdigit() for c in s)


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


# Un número: o bien con espacios como separador de miles ("127 174", grupos de 3 cifras),
# o bien con puntos/comas ("127.174", "19,3"). Así "10.511 9.988" son DOS números.
_NUMBER_RE = re.compile(r"\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)*")


def number_in_text(expected: str, text: str) -> bool:
    """'127.174' está en '127 174 empleados'; '12,7' está en '12,70 %'; '0,3' en '0,30 €'."""
    want = _digits(expected)
    want_trimmed = want.rstrip("0") or "0"
    for token in _NUMBER_RE.findall(text):
        got = _digits(token)
        if got == want or (len(want_trimmed) >= 2 and got.rstrip("0") == want_trimmed):
            return True
    return False


def clave_in_text(clave: str, text: str) -> bool:
    """Una clave puede tener alternativas separadas por '|': basta con que aparezca una."""
    for alt in (a.strip() for a in clave.split("|")):
        if _is_number(alt):
            if number_in_text(alt, text):
                return True
        elif _normalize_text(alt) in _normalize_text(text):
            return True
    return False


def _specific_numbers(clave: str) -> list[str]:
    """Alternativas numéricas lo bastante concretas como para buscarlas en todo el informe."""
    out = []
    for alt in (a.strip() for a in clave.split("|")):
        d = _digits(alt)
        if _is_number(alt) and len(d) >= 3 and not re.fullmatch(r"(19|20)\d\d", d):
            out.append(alt)
    return out


def evidence_pages(question: dict, pages: list[dict]) -> set[tuple[str, int]]:
    """Páginas de la(s) empresa(s) de la pregunta que contienen TODAS sus claves numéricas."""
    claves = question.get("claves") or []
    alts = [_specific_numbers(c) for c in claves]
    if not claves or any(not a for a in alts):
        return set()            # alguna clave no es numérica/específica: no se amplía
    found = set()
    for p in pages:
        if p["company"] in question["empresa"] and all(
                any(number_in_text(a, p["text"]) for a in clave_alts) for clave_alts in alts):
            found.add((p["company"], p["page"]))
    return found


# ------------------------------------------------------------------ métricas de una pregunta
def score(question: dict, text: str, retrieved: list[tuple], cited: list[tuple],
          no_answer: bool, invalid: list[int], extra_pages: set | None = None) -> dict:
    declared = {(c, p) for c in question["empresa"] for p in question["paginas"]}
    valid = declared | (extra_pages or set())
    claves = question.get("claves") or []
    claves_ok = all(clave_in_text(c, text) for c in claves) if claves else None

    if question["tipo"] == "sin_respuesta":
        acierto = no_answer
    elif claves_ok is None:
        acierto = None                                    # revisión manual
    else:
        acierto = claves_ok and not no_answer

    return {
        "busqueda": bool(valid & set(retrieved)) if declared else None,
        "cita": bool(valid & set(cited)) if declared else None,
        "claves": claves_ok,
        "rechazo": no_answer,
        "citas_inventadas": invalid,
        "acierto": acierto,
    }


# ------------------------------------------------------------------ revisión manual
def load_review(label: str) -> dict:
    path = RESULTS_DIR.parent / f"revision_{label}.yaml"
    if not path.exists():
        return {}
    import yaml

    items = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return {it["id"]: it for it in items if it.get("acierto") is not None}


def final_verdict(row: dict, review: dict):
    r = review.get(row["id"])
    return r["acierto"] if r else row["metricas"]["acierto"]


# ------------------------------------------------------------------ resumen
def _pct(values: list) -> str:
    vals = [v for v in values if v is not None]
    return f"{sum(vals)}/{len(vals)} ({100 * sum(vals) / len(vals):.0f} %)" if vals else "—"


def summarize(rows: list[dict], review: dict | None = None) -> str:
    review = review or {}
    by_type = defaultdict(list)
    for r in rows:
        by_type[r["tipo"]].append(r)

    head = f"{'Tipo':<14}{'N':>3}  {'Búsqueda':<14}{'Cita':<14}{'Acierto auto':<15}{'Acierto final':<14}"
    lines = [head, "-" * len(head)]

    def line(name, rs):
        m = [r["metricas"] for r in rs]
        return (f"{name:<14}{len(rs):>3}  {_pct([x['busqueda'] for x in m]):<14}"
                f"{_pct([x['cita'] for x in m]):<14}{_pct([x['acierto'] for x in m]):<15}"
                f"{_pct([final_verdict(r, review) for r in rs]):<14}")

    for t in TYPE_ORDER + sorted(set(by_type) - set(TYPE_ORDER)):
        if by_type.get(t):
            lines.append(line(t, by_type[t]))
    lines += ["-" * len(head), line("TOTAL", rows)]

    hallucinations = [r["id"] for r in rows if r["tipo"] == "sin_respuesta" and not r["metricas"]["rechazo"]]
    false_neg = [r["id"] for r in rows if r["tipo"] != "sin_respuesta" and r["metricas"]["rechazo"]]
    manual = [r["id"] for r in rows if final_verdict(r, review) is None]
    wrong = [r["id"] for r in rows if r["metricas"]["acierto"] is False and r["id"] not in false_neg + hallucinations]
    invented = [r["id"] for r in rows if r["metricas"]["citas_inventadas"]]
    lines += ["",
              f"Alucinaciones (respondió a una pregunta sin respuesta): {hallucinations or 'ninguna'}",
              f"Falsos negativos (dijo 'no lo encuentro' y sí estaba):  {false_neg or 'ninguno'}",
              f"Respuestas sin los datos clave:                        {wrong or 'ninguna'}",
              f"Citas a fragmentos inexistentes:                       {invented or 'ninguna'}",
              f"Pendientes de revisión manual:                         {manual or 'ninguna'}"]
    if review:
        changed = [f"{i}: {'✓' if v['acierto'] else '✗'}" for i, v in review.items()]
        lines.append(f"Corregidas en la revisión manual:                      {changed}")
    return "\n".join(lines)


# ------------------------------------------------------------------ utilidades
def load_questions(path: Path = QUESTIONS) -> list[dict]:
    import yaml

    questions = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [q for q in questions if q.get("estado") != "descartada"]


def load_pages(path: Path = PAGES) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def _parse_source(s: str) -> tuple[str, int]:
    company, page = s.rsplit(" p.", 1)
    return company, int(page)


def rescore_row(row: dict, question: dict, pages: list[dict]) -> dict:
    """Recalcula las métricas de una respuesta guardada (sin volver a llamar al LLM)."""
    from .prompts import is_no_answer, normalize_citations, parse_citations

    text = normalize_citations(row["respuesta"])
    sent = [_parse_source(s) for s in row["enviados"]]
    cited_n = parse_citations(text)
    cited = [sent[n - 1] for n in cited_n if 1 <= n <= len(sent)]
    invalid = [n for n in cited_n if not 1 <= n <= len(sent)]
    row = dict(row, respuesta=text, fuentes=[f"{c} p.{p}" for c, p in cited])
    row["metricas"] = score(question, text, sent, cited, is_no_answer(text), invalid,
                            evidence_pages(question, pages))
    return row


def _write_rows(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def write_review_template(label: str, rows: list[dict]) -> Path:
    """Plantilla con las preguntas que no son un acierto automático claro."""
    path = RESULTS_DIR.parent / f"revision_{label}.yaml"
    if path.exists():
        raise SystemExit(f"{path} ya existe: edítalo directamente (no lo sobrescribo).")
    lines = [f"# Revisión manual de los resultados '{label}'.",
             "# Para cada pregunta, lee la respuesta y la esperada y decide:",
             "#   acierto: true   -> la respuesta es correcta (aunque el automático diga que no)",
             "#   acierto: false  -> la respuesta es incorrecta",
             "#   acierto: null   -> sin revisar (cuenta el resultado automático)",
             "# Explica siempre el motivo. Las preguntas congeladas NO se tocan.", ""]
    for r in rows:
        if r["metricas"]["acierto"] is True:
            continue
        lines += [f"- id: {r['id']}",
                  f"  automatico: {json.dumps(r['metricas']['acierto'])}",
                  f"  pregunta: {json.dumps(r['pregunta'], ensure_ascii=False)}",
                  f"  esperada: {json.dumps(r['esperada'], ensure_ascii=False)}",
                  f"  respuesta: {json.dumps(r['respuesta'], ensure_ascii=False)}",
                  f"  fuentes: {json.dumps(r['fuentes'], ensure_ascii=False)}",
                  "  acierto: null",
                  '  motivo: ""', ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ------------------------------------------------------------------ programa
def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Evalúa el asistente con eval/preguntas.yaml")
    ap.add_argument("--label", required=True, help="Nombre de esta prueba, p. ej. 'base'")
    ap.add_argument("--only", nargs="*", help="Solo estas preguntas (ids)")
    ap.add_argument("--model", help="Modelo de Groq")
    ap.add_argument("--k", type=int, help="Fragmentos que se envían al modelo")
    ap.add_argument("--pause", type=float, default=20,
                    help="Segundos de espera entre preguntas (límite gratuito de Groq)")
    ap.add_argument("--summary", action="store_true", help="Solo mostrar el resumen")
    ap.add_argument("--rescore", action="store_true", help="Recalcular métricas sin llamar a Groq")
    ap.add_argument("--plantilla-revision", action="store_true",
                    help="Crear eval/revision_<label>.yaml con los casos a revisar a mano")
    args = ap.parse_args(argv)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{args.label}.jsonl"
    done = {}
    if out.exists():
        done = {r["id"]: r for r in map(json.loads, out.open(encoding="utf-8"))}

    questions = load_questions()
    if args.only:
        questions = [q for q in questions if q["id"] in args.only]
    by_id = {q["id"]: q for q in load_questions()}
    pages = load_pages()

    if args.rescore:
        rows = [rescore_row(done[i], by_id[i], pages) for i in done if i in by_id]
        _write_rows(out, rows)
        done = {r["id"]: r for r in rows}
        print(f"Recalculadas {len(rows)} respuestas de '{args.label}' (sin llamar a Groq).")
    elif not args.summary and not args.plantilla_revision:
        from .ask import answer_question
        from .embeddings import MODEL_NAME, E5Embedder
        from .llm import GroqLLM
        from .retrieval import N_CONTEXT, known_companies
        from .vector_store import get_collection

        pending = [q for q in questions if q["id"] not in done]
        print(f"{len(questions)} preguntas · {len(questions) - len(pending)} ya hechas · {len(pending)} por hacer")
        if pending:
            llm = GroqLLM(args.model, max_retries=8)
            embedder = E5Embedder(MODEL_NAME)
            collection = get_collection(MODEL_NAME)
            companies = known_companies()
            k = args.k or N_CONTEXT
            print(f"Modelo: {llm.name} · fragmentos: {k} · pausa entre preguntas: {args.pause:.0f} s "
                  f"(~{len(pending) * (args.pause + 3) / 60:.0f} min)\n", flush=True)

        with out.open("a", encoding="utf-8") as f:
            for i, q in enumerate(pending, 1):
                if i > 1:
                    time.sleep(args.pause)
                a = answer_question(q["pregunta"], collection, embedder, llm, companies, k=k)
                sent = [(h["company"], h["page"]) for h in a.hits]
                cited = [(h["company"], h["page"]) for _, h in a.sources]
                m = score(q, a.text, sent, cited, a.no_answer, a.invalid, evidence_pages(q, pages))
                row = {
                    "id": q["id"], "tipo": q["tipo"], "pregunta": q["pregunta"],
                    "respuesta": a.text, "esperada": q["respuesta_esperada"],
                    "paginas_esperadas": q["paginas"],
                    "fuentes": [f"{c} p.{p}" for c, p in cited],
                    "enviados": [f"{c} p.{p}" for c, p in sent],
                    "metricas": m, "modelo": llm.name, "k": k, "segundos": round(a.seconds, 1),
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()                                   # guardado inmediato: reanudable
                done[q["id"]] = row
                mark = {True: "✓", False: "✗", None: "?"}[m["acierto"]]
                print(f"[{i}/{len(pending)}] {mark} {q['id']:<9} búsqueda={m['busqueda']} "
                      f"cita={m['cita']} claves={m['claves']} rechazo={m['rechazo']}", flush=True)

    rows = [done[q["id"]] for q in questions if q["id"] in done]
    if args.plantilla_revision:
        path = write_review_template(args.label, rows)
        print(f"Plantilla de revisión creada: {path}")
        return
    review = load_review(args.label)
    print(f"\n===== Resultados '{args.label}' ({len(rows)} preguntas) =====\n")
    print(summarize(rows, review))
    print(f"\nDetalle de cada respuesta en {out}")


if __name__ == "__main__":
    main()
