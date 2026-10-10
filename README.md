# Informe de evaluación de acciones formativas (Streamlit)

App que procesa un `.zip` con cuestionarios SEPE/FUNDAE de evaluación de la calidad (PDF rellenables)
y genera el informe **«Informe Curso – [Nombre del curso]»** en PDF con 4 apartados:

1. **Ficha del curso**: denominación, Nº expediente, Nº AAFF / grupo, Nº de cuestionarios.
2. **Análisis cuantitativo**: ítems 1–10, con la media de cada apartado (media de sus sub-ítems,
   truncada a 2 decimales, sin redondeo) y el nivel (1,00–2,99 No satisfactorio · 3,00–4,00 Satisfactorio).
   Porcentajes Sí/No de los ítems 8 y 10. El ítem 7 se activa o desactiva en el panel lateral
   (por defecto se activa si los cuestionarios indican teleformación o modalidad mixta).
3. **Análisis de comentarios** (ítem 11): elemento, valor, frecuencia y 2 comentarios ilustrativos.
4. **Conclusiones y recomendaciones**: nota 0–10, resumen ejecutivo, nivel general, fortalezas,
   áreas de mejora y recomendaciones con comentario y acción.

## Ejecutar en local
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Desplegar en Streamlit Community Cloud
1. Sube esta carpeta a un repositorio de GitHub.
2. En share.streamlit.io → *Create app* → elige el repositorio y `app.py` como archivo principal.
3. (Opcional) En *Settings → Secrets* añade `ANTHROPIC_API_KEY = "..."` para el análisis con IA.

## Estructura
```
app.py                  Interfaz Streamlit
nucleo/lector.py        Lectura del .zip y de los campos de cada formulario PDF
nucleo/cuantitativo.py  Medias, niveles y porcentajes Sí/No
nucleo/comentarios.py   Análisis de comentarios por reglas + acciones recomendadas
nucleo/ia.py            Análisis opcional con Claude (API de Anthropic)
nucleo/conclusiones.py  Fortalezas, áreas de mejora, resumen y recomendaciones
nucleo/informe_pdf.py   Maquetación del PDF
```

## Notas
- Los datos se leen de los **campos del formulario** PDF. Los cuestionarios escaneados o «aplanados»
  (sin campos rellenables) aparecen en la lista de archivos no procesados.
- Las respuestas «No contesta» no computan en las medias.
- Valoración 0–10 = (media de los apartados − 1) / 3 × 10.
- Ítem 8 (Sí/No): el apartado se considera satisfactorio si el % medio de «Sí» es ≥ 50 %.
- Si el .zip contiene varios cursos o grupos, la app permite elegir cuál informar.
- Para adaptar el análisis de comentarios, edita las listas `ELEMENTOS`, `POSITIVAS`, `NEGATIVAS`
  y `ACCIONES` de `nucleo/comentarios.py`.
