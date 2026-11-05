# Diario del proyecto

Apunta aquí decisiones, problemas y números. Es el material de la entrevista.

## Fase 1 · Leer los documentos

**Decisiones**
- PyMuPDF en vez de pdfplumber: más rápido con informes de 300+ páginas y trae
  detección de tablas (`page.find_tables()`) y exportación a Markdown.
- Guardar por página (no por documento): la página es la unidad de cita.
- Guardar `removed_lines` en cada página para poder auditar qué se ha borrado.

**Problemas que revisar con los PDF reales** (rellena con lo que veas)
- [ ] Tablas sin bordes (muy habituales en cuentas anuales): ¿se detectan?
      Mira páginas de la cuenta de resultados con `scripts/inspect_page.py`.
- [ ] Maquetación a dos columnas: ¿el orden de lectura es correcto?
- [ ] Páginas casi vacías: ¿son gráficos/infografías o PDF escaneado (requiere OCR)?
- [ ] Cabeceras que cambian por capítulo y no llegan al 30 %: ajustar `REPEAT_THRESHOLD`.
- [ ] Informe en inglés vs español: anotar el idioma de cada uno.

**Primera ingesta (28/10/2026)**
- Telefónica 2025: 410 páginas, 165 con tablas, 11 casi vacías. Tardó ~10 min.
- BBVA 2025: 758 páginas, 265 con tablas, 23 casi vacías.
- Total: 1170 páginas guardadas en `data/processed/pages.jsonl`.
- La detección de tablas es lo lento (~1 s por página). El programa no muestra
  progreso mientras procesa cada informe: parece colgado. Mejora pendiente.

**Errores y aprendizajes**
- El primer PDF de Ferrovial era un capítulo suelto de 2 páginas, no el informe.
  Lo delató el resumen de la ingesta ("2 páginas"). Lección: revisar siempre
  los números del resumen, no fiarse a ciegas.
- El informe completo de Ferrovial (474 páginas) está en inglés porque la sede
  está en Países Bajos. Tendremos documentos en dos idiomas: comprobar en la
  Fase 2 si el buscador encuentra textos en inglés con preguntas en español.

**Sospechas por revisar**
- La limpieza elimina números sueltos como '0', '10' o '1 2 3 4 5 6'. Pueden ser
  datos de tablas o gráficos, no números de página. Revisar con inspect_page.py.
- Páginas casi vacías: Telefónica 205-210 y 317-319, BBVA 434-443 y 747-750.
  ¿Separadores de capítulo, gráficos o algo que no se está extrayendo?

**Cierre de la Fase 1 (29/10)**
- Revisión a mano: las páginas casi vacías de Ferrovial son fotos a página completa
  con pie de foto (p. ej. p.17 "JFK Airport"): la extracción es correcta.
- El menú lateral de capítulos de Ferrovial se elimina bien como cabecera repetida.
- Problema en tablas: palabras pegadas ("Operaciónconjunta") y restos `<br>`.
  Medido con `scripts/quality_report.py`: 9-14 % de páginas afectadas, y el 100 %
  de ellas con tablas -> el fallo está solo en el detector de tablas.
- Arreglo: quitar `<br>` y "plan B" (si una tabla tiene palabras pegadas, se usa el
  texto normal de la página). Resultado: 0 páginas con `<br>` y 0 con palabras pegadas.
- La ingesta se cortaba con la suspensión del portátil -> ingesta reanudable
  (un archivo por informe + escritura atómica). BBVA tarda ~25 min.
- Resultado final: 1.642 páginas (Ferrovial 474, Telefónica 410, BBVA 758).

## Fase 2 · Trocear y vectorizar


**Troceado (30/10)**
- Fragmentos siempre dentro de una página: la cita es exacta.
- Corte por párrafos (y por frases si el párrafo es largo): no se parten ideas.
- Máx. 300 palabras con 50 de solapamiento: multilingual-e5 solo lee ~350 palabras.
- Resultado: 4.263 fragmentos, ~225 palabras de media.
- En BBVA cada línea venía como bloque separado: hubo que reconstruir los párrafos.

**Embeddings y base vectorial (30/10)**
- Modelo: `intfloat/multilingual-e5-base` (gratis, local, español + inglés, vectores de 768).
  Elegido frente a e5-small por calidad; e5-small queda como experimento para la Fase 4.
- Prefijos obligatorios del modelo: "query: " en preguntas y "passage: " en fragmentos.
- Cada fragmento se vectoriza con la cabecera "Empresa año, página N." delante.
- Base vectorial: Chroma en `data/chroma/`, distancia del coseno.
- Vectorizar todo con batería estimaba ~150 min; enchufado es mucho más rápido.
  La indexación es reanudable y además incremental (solo revectoriza lo que cambia).

**Primeras búsquedas (03/11)**
- "número de empleados" -> tabla de BBVA con 127.174 empleados: las tablas en
  Markdown se encuentran y se leen bien.
- "riesgos de tipos de interés" -> 4 de 5 resultados muy relevantes (BBVA).
- Las similitudes de e5 van en un rango estrecho (0,81-0,87): importa el orden,
  no el valor absoluto. No interpretarlas como probabilidades.
- Debilidad: confunde subtipos de riesgo (interés vs crédito vs tipo de cambio).
- Sin filtro de empresa, los resultados se concentran en BBVA (más fragmentos y en español).

**Limpieza de tablas rotas y duplicados (03/11)**
- Síntoma: buscando "riesgo de tipos de interés" en Ferrovial, 4 de 5 resultados eran
  copias de la misma tabla (p.396).
- Causa: tablas mal detectadas -> celdas combinadas copiadas en cada columna,
  "sopa de números" en una sola celda, entidades HTML (`&amp;#45;`) y negritas `**`.
- Descartado: filtrar fragmentos con muchos números (habría borrado ~380, incluidas
  tablas financieras valiosas). El problema eran las tablas rotas, no los números.
- Arreglo: limpiar tablas (`text_clean.py`), pasar a texto las tablas "sopa" y
  eliminar duplicados exactos y casi idénticos (>= 90 %) dentro de cada página.
- Antes -> después: 4.263 -> 4.007 fragmentos; duplicados 60 -> 0; entidades HTML
  635 -> 0; Ferrovial p.396: 20 -> 6 fragmentos.
- Reindexado incremental: solo 945 fragmentos revectorizados y 258 borrados (~5 min).

**Hallazgos que quedan abiertos (03/11)**
- Pregunta en español sobre informe en inglés: la mejor respuesta (Ferrovial p.392)
  sale 1.ª preguntando en inglés, pero NI EN EL TOP 10 preguntando en español.
  Similitudes casi empatadas (0,809-0,833): el modelo no distingue bien.
- Una tabla larga (p.396) ocupa 4 de los 10 primeros puestos.
- Ruido nuevo: índices con letras separadas ("G L O B A L S T R A T E G Y").

## Fase 3 · El asistente con Groq (03/11)

**Decisiones**
- LLM vía Groq (gratis) con la librería `openai` apuntando a la dirección de Groq: el
  mismo código serviría para OpenAI o Azure OpenAI (cambiar dirección, clave y modelo).
- Selección de fragmentos: 20 candidatos -> 6 enviados, máximo 2 por página.
- Si la pregunta nombra varias empresas (o dice "compara"/"las tres"), se busca en
  cada una por separado y se reparten los huecos.
- Citas por NÚMERO: el LLM cita [1], [2]... y es el código quien convierte cada número
  en "Empresa año, página N" con los metadatos. El LLM no puede inventarse una página,
  y el código avisa si cita un número que no existe.
- Frase fija para "no lo sé": "No encuentro esta información en los informes
  disponibles." -> se puede detectar automáticamente en la Fase 4.
- Temperatura 0: respuestas estables y reproducibles.

**Problemas encontrados**
- Los modelos Llama ya no estaban disponibles en la cuenta, aunque la documentación
  los listaba. Solución: comando `python -m rag_informes.llm`, que pregunta a la API
  qué modelos hay, en vez de fiarse de la documentación. Modelo final: openai/gpt-oss-120b.
- gpt-oss-120b "razona" antes de responder y ese razonamiento gasta tokens: se subió el
  límite a 2.000 tokens y se le pide razonar poco (reasoning_effort="low").
- gpt-oss cita con corchetes chinos 【2】 en vez de [2]: el código no las reconocía y
  decía "no cita ninguna fuente". Arreglado aceptando ambos formatos.

**Primeras preguntas**
- "¿Cuántos empleados tenía BBVA en 2025?" -> 127.174, citado. Bien.
- "¿Qué riesgos de tipos de interés menciona BBVA?" -> repreciación, curva, opcionalidad,
  carteras de negociación; citas coherentes con los fragmentos (p.549 y p.556).
- "Compara... las tres empresas" -> trae información de las tres, cada una citada.
- "¿Quién ganó la última Champions League?" -> "No encuentro esta información". Bien:
  el modelo no usa lo que "sabe" por su cuenta.
- "¿Cuál fue la deuda neta de Ferrovial en 2025?" -> "No encuentro esta información",
  pero es un FALSO NEGATIVO: en inglés ("What was Ferrovial's net debt in 2025?") sí la
  encuentra (p.7: -1.300 M€, excluidos proyectos de infraestructura = caja neta).
  Con --show-context se ve que en español los 6 fragmentos eran irrelevantes
  (similitudes empatadas ~0,84). El fallo es del buscador, no del LLM.
- Distinción importante: falso negativo (dice "no lo sé" aunque está) es molesto pero
  no engaña; alucinación (se inventa el dato) es mucho más grave. Ninguna alucinación
  en estas preguntas.

## Fase 4 · Evaluación: medir antes de mejorar (05/11)

Idea clave: no ajustar el sistema a base de búsquedas sueltas. Primero un conjunto
de preguntas con su respuesta correcta, luego medir, y cada mejora se queda solo si
mejora los números.

### El conjunto de prueba (`eval/preguntas.yaml`)
- 40 preguntas **congeladas**: cifra 17, idioma 7 (español sobre el informe en inglés
  de Ferrovial y al revés), trampa 5, descriptiva 3, comparación 3, sin respuesta 5.
- Cada una con respuesta esperada, páginas y "claves" (cifras o palabras que deben
  aparecer; `a | b` = vale cualquiera de las dos).
- Verificadas sobre el PDF. Lección: **yo también me equivoqué** al escribir respuestas
  (tef-01: 100.870 era el dato de 2024; el de 2025 es 82.655). Un conjunto de prueba mal
  hecho mide mal: hay que comprobarlo con la página real.
- Parejas de control (fer-01/fer-07, fer-02/fer-08): misma pregunta en español y en
  inglés, para aislar el efecto del idioma.

### Las métricas (`python -m rag_informes.evaluate`)
- **Búsqueda**: ¿llegó al LLM algún fragmento de una página correcta? (mide el buscador)
- **Cita**: ¿citó una página correcta?
- **Claves**: ¿aparecen las cifras/palabras clave? (las cifras se comparan en cualquier
  formato: 127.174 = 127,174 = 127 174)
- **Rechazo**: ¿dijo "no lo encuentro"? En las preguntas sin respuesta es lo correcto;
  en las demás es un **falso negativo**. Responder a una sin respuesta = **alucinación**.
- **Páginas de evidencia**: un mismo dato sale en varias páginas (resumen, tablas...).
  Se cuentan como correctas las páginas de la misma empresa donde aparece la cifra
  clave (solo cifras "específicas": 3+ dígitos y que no sean un año).
- Acierto automático + **revisión manual** de los dudosos (`eval/revision_base.yaml`):
  la máquina no entiende si una respuesta descriptiva es buena o si un redondeo vale.

### Línea base (`--label base`): k=6, e5-base, gpt-oss-120b

| Tipo | N | Búsqueda | Cita | Acierto final |
|---|---|---|---|---|
| cifra | 17 | 76 % | 76 % | 14/17 (82 %) |
| idioma | 7 | 43 % | 29 % | 4/7 (57 %) |
| trampa | 5 | 40 % | 20 % | 1/5 (20 %) |
| descriptiva | 3 | 67 % | 67 % | 2/3 (67 %) |
| comparación | 3 | 33 % | 33 % | 1/3 (33 %) |
| sin respuesta | 5 | — | — | 5/5 (100 %) |
| **TOTAL** | 40 | **60 %** | 54 % | **27/40 (68 %)** |

- **0 alucinaciones, 0 citas inventadas.** El sistema es prudente: falla por no
  responder, no por inventar.
- Falsos negativos (7): bbva-04, tef-06, tef-09, fer-05, fer-09, fer-10, comp-03.
  Casi todos porque el buscador **no trajo la página buena** (infografías como
  Telefónica p.13 y Ferrovial p.19 con letras espaciadas; español sobre inglés).
- Respuestas sin el dato clave (7): bbva-09, bbva-11, tef-02, tef-07, fer-03, fer-04
  (redondeo aceptado en revisión), comp-01. A veces el LLM usa un número parecido de
  otro fragmento (fer-03, comp-01): el problema vuelve a ser el contexto recibido.
- Criterios de la revisión manual: fer-06 y comp-02 cuentan como acierto aunque son
  genéricas; en comp-02 la conclusión generaliza las "tres líneas de defensa" a
  Telefónica sin fuente (vigilar en las comparaciones).

**Conclusión: el cuello de botella es la búsqueda (60 %), no el LLM.** Las mejoras van
ahí primero, y cada una con su propio `--label` para compararla con `base`.

### Mejoras a probar (una a una, contra `base`)
- [ ] Más fragmentos al LLM (k = 8–10). La más barata.
- [ ] Búsqueda híbrida: significado (embeddings) + palabras exactas (BM25).
      Debería ayudar con siglas, ratings y cifras ("Baa3", "IRRBB").
- [ ] Traducir la pregunta al idioma del documento antes de buscar.
      Caso claro: "deuda neta de Ferrovial" falla en español y acierta en inglés.
- [ ] Reranker: de 20 candidatos, un segundo modelo elige los mejores.
- [ ] Limpiar texto con letras separadas por espacios ("G L O B A L").
- [ ] Comparar e5-base frente a e5-small; probar fragmentos de 200 y 400 palabras.
- [x] Limitar fragmentos por página (máx. 2): hecho en la Fase 3.
- [x] Preguntas en español sobre Ferrovial y comparaciones: incluidas en el conjunto.
