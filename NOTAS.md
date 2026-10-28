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

## Fase 2 · Trocear y vectorizar
_pendiente_
