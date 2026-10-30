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

## Fase 2 · Trocear y vectorizar


**Troceado (30/10)**
- Fragmentos siempre dentro de una página: la cita es exacta.
- Corte por párrafos (y por frases si el párrafo es largo): no se parten ideas.
- Máx. 300 palabras con 50 de solapamiento: multilingual-e5 solo lee ~350 palabras.
- Resultado: 4.263 fragmentos, ~225 palabras de media.
- En BBVA cada línea venía como bloque separado: hubo que reconstruir los párrafos.