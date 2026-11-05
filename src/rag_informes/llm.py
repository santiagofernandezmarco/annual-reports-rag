"""Fase 3 · Conexión con el LLM que redacta las respuestas (Groq).

Usamos la librería `openai` apuntando a la dirección de Groq: Groq habla el mismo
"idioma" que la API de OpenAI. Así, cambiar a OpenAI o Azure OpenAI (Fase 6) sería
cambiar la dirección, la clave y el nombre del modelo, no el código.

La clave se lee de .env (GROQ_API_KEY). El modelo se puede cambiar con GROQ_MODEL en
.env o con --model en la línea de comandos.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

ROOT = Path(__file__).resolve().parents[2]
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# Los Llama dejaron de estar disponibles en la cuenta (03/11/2026, comprobado con
# `python -m rag_informes.llm`). gpt-oss-120b es un modelo que "razona" antes de responder:
# ese razonamiento interno también gasta tokens, por eso el límite es holgado y
# le pedimos que razone poco (REASONING_EFFORT).
DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_ANSWER_TOKENS = 2000
REASONING_EFFORT = "low"


class LLM(Protocol):
    """Lo mínimo que necesita el asistente. Permite usar un LLM falso en las pruebas."""
    name: str

    def complete(self, system: str, user: str) -> str: ...


class GroqLLM:
    def __init__(self, model: str | None = None, api_key: str | None = None, max_retries: int = 2):
        """max_retries: reintentos automáticos si Groq responde "límite alcanzado" (429).
        La librería espera lo que Groq indique (cabecera retry-after) antes de reintentar.
        Para la evaluación por lotes conviene subirlo (p. ej. 8)."""
        from dotenv import load_dotenv
        from openai import OpenAI

        load_dotenv(ROOT / ".env")
        api_key = api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise SystemExit(
                "No encuentro GROQ_API_KEY. Crea el archivo .env en la carpeta del proyecto con la línea:\n"
                "GROQ_API_KEY=gsk_...tu_clave..."
            )
        self.name = model or os.getenv("GROQ_MODEL") or DEFAULT_MODEL
        self.client = OpenAI(api_key=api_key, base_url=GROQ_BASE_URL, max_retries=max_retries)

    def complete(self, system: str, user: str) -> str:
        import openai

        extra = {}
        if "gpt-oss" in self.name:          # solo los modelos que razonan aceptan este ajuste
            extra["reasoning_effort"] = REASONING_EFFORT
        try:
            response = self.client.chat.completions.create(
                model=self.name,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                temperature=0,              # respuestas estables: siempre la opción más probable
                max_tokens=MAX_ANSWER_TOKENS,
                **extra,
            )
        except openai.AuthenticationError:
            raise SystemExit("Groq rechaza la clave. Revisa GROQ_API_KEY en .env (¿copiada entera?).")
        except openai.RateLimitError:
            raise SystemExit("Has llegado al límite gratuito de Groq (por minuto o por día). "
                             "Espera un poco y vuelve a intentarlo.")
        except openai.NotFoundError as e:
            raise SystemExit(f"Groq no reconoce el modelo '{self.name}'.\n"
                             f"Mensaje de Groq: {e}\n"
                             "Para ver los modelos disponibles en tu cuenta: python -m rag_informes.llm")
        except openai.APIConnectionError:
            raise SystemExit("No puedo conectar con Groq. ¿Tienes conexión a internet?")

        choice = response.choices[0]
        text = (choice.message.content or "").strip()
        if not text:
            raise SystemExit(f"El modelo devolvió una respuesta vacía (motivo: {choice.finish_reason}). "
                             "Si el motivo es 'length', ha gastado todos los tokens razonando: "
                             "sube MAX_ANSWER_TOKENS en llm.py.")
        if choice.finish_reason == "length":
            text += "\n\n[Aviso: la respuesta se ha cortado por el límite de longitud]"
        return text

    def available_models(self) -> list[str]:
        """Modelos que tu cuenta de Groq puede usar ahora mismo (se lo preguntamos a la API)."""
        return sorted(m.id for m in self.client.models.list().data)


def main() -> None:
    """python -m rag_informes.llm  -> lista los modelos y hace una pregunta de prueba."""
    llm = GroqLLM()
    models = llm.available_models()
    print("Modelos disponibles en tu cuenta de Groq:")
    for m in models:
        print(f"  {'→' if m == llm.name else ' '} {m}")
    if llm.name not in models:
        print(f"\nEl modelo configurado ('{llm.name}') NO está en la lista. Elige otro y ponlo en .env:\n"
              "GROQ_MODEL=nombre_del_modelo")
        return
    print(f"\nPrueba rápida con {llm.name}...")
    print("Respuesta:", llm.complete("Responde en una sola frase.", "Di hola en español."))


if __name__ == "__main__":
    main()
