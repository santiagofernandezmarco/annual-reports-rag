# rag-informes

Asistente que responde preguntas sobre informes anuales de empresas cotizadas
(Ferrovial, Telefónica, BBVA…) **usando solo lo que dicen los documentos** y
**citando empresa, año y página**.

> Estado: Fase 1 (lectura y limpieza de los PDF) ✅ · Fase 2 (trocear y vectorizar) ⏳

## Estructura

```
rag-informes/
├── data/
│   ├── companies.json      # qué PDF hay y de qué empresa/año es cada uno
│   ├── raw/                # aquí van los PDF (no se suben a GitHub)
│   └── processed/          # pages.jsonl generado por la ingesta
├── src/rag_informes/
│   ├── pdf_extract.py      # extracción + limpieza de cabeceras, pies y tablas
│   └── ingest.py           # procesa todos los PDF -> pages.jsonl
├── scripts/inspect_page.py # ver a ojo cómo quedó una página
├── tests/                  # pytest
├── eval/                   # (Fase 4) preguntas y respuestas de referencia
└── NOTAS.md                # diario de decisiones y problemas encontrados
```

## Instalación

```bash
git clone <tu-repo> && cd rag-informes
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env                                   # y pon tu clave de API
```

## Uso (Fase 1)

1. Descarga los informes anuales en PDF y guárdalos en `data/raw/`.
2. Ajusta `data/companies.json` (nombre de archivo, empresa, año y páginas a saltar).
3. Ejecuta la ingesta:

```bash
python -m rag_informes.ingest
python scripts/inspect_page.py Ferrovial 2025 42   # revisar una página
pytest                                             # pruebas
```

Cada línea de `data/processed/pages.jsonl` es una página:

```json
{"company": "Ferrovial", "year": 2025, "page": 42, "page_label": "40",
 "text": "...", "n_tables": 1, "removed_lines": ["Informe anual 2025", "40"],
 "doc_id": "Ferrovial_2025"}
```

`page` es la página física del PDF; `page_label` es el número impreso (si el PDF
lo define). Para citar, usaremos `page`, que es la que el usuario encuentra al
abrir el PDF.

## Cómo se limpia el texto

- **Cabeceras y pies**: bloques en el 8 % superior o inferior de la página que se
  repiten en al menos el 30 % de las páginas (comparando con los dígitos
  normalizados, así "Página 3 de 200" y "Página 4 de 200" cuentan como iguales).
- **Números de página** sueltos.
- **Palabras partidas** con guion al final de línea.
- **Tablas**: si PyMuPDF las detecta, se sustituyen por su versión en Markdown.
  Las tablas sin bordes muchas veces no se detectan (ver `NOTAS.md`).

## Resultados y limitaciones

Se completará en la Fase 4 y 5.
