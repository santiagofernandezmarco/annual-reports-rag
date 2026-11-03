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

## Pendiente para la Fase 4 (mejoras a medir, no a ojo)

Idea clave: no ajustar el sistema a base de búsquedas sueltas. Primero crear un
conjunto de preguntas con su respuesta correcta y medir; luego probar cada mejora
y quedarse solo con las que mejoren los números.

- [ ] Traducir la pregunta al idioma del documento antes de buscar (query translation).
- [ ] Búsqueda híbrida: significado (embeddings) + palabras exactas (BM25).
- [ ] Reranker: buscar ~20 candidatos y que un segundo modelo elija los 5 mejores.
- [ ] Limitar fragmentos por página (1-2) para diversificar resultados.
      (Se aplicará ya en la Fase 3, al montar el asistente.)
- [ ] Limpiar texto con letras separadas por espacios ("G L O B A L").
- [ ] Comparar e5-base frente a e5-small (calidad frente a velocidad).
- [ ] Probar otros tamaños de fragmento (p. ej. 200 y 400 palabras).
- [ ] Incluir en el conjunto de prueba preguntas en español sobre Ferrovial (inglés)
      y preguntas que comparen empresas.
