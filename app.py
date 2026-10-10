"""
App Streamlit · Informe de evaluación de acciones formativas
Carga un .zip con cuestionarios SEPE/FUNDAE en PDF y genera el informe en PDF.

Ejecutar en local:  streamlit run app.py
"""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from nucleo import agrupar_por_curso, detectar_teleformacion, generar_pdf, leer_zip, procesar
from nucleo.cuantitativo import fmt_exacto, fmt_pct
from nucleo.ia import MODELO_POR_DEFECTO

st.set_page_config(page_title="Informe de cursos", page_icon="📊", layout="wide")


# ------------------------------------------------------------------ utilidades
@st.cache_data(show_spinner=False)
def _leer(datos: bytes):
    return leer_zip(datos)


def _nombre_archivo(nombre_curso: str) -> str:
    limpio = re.sub(r'[\\/:*?"<>|]+', "", nombre_curso).strip()
    return f"Informe Curso – {limpio}.pdf"


def _clave_api_secrets() -> str:
    try:
        return st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:  # sin secrets.toml
        return ""


# ------------------------------------------------------------------ cabecera
st.title("📊 Informe de evaluación de acciones formativas")
st.caption("Sube un archivo .zip con los cuestionarios de evaluación (PDF rellenables SEPE/FUNDAE) "
           "y descarga el informe del curso en PDF.")

archivo = st.file_uploader("Cuestionarios en formato .zip", type=["zip"])

if not archivo:
    st.info("**Cómo funciona**\n\n"
            "1. Comprime en un único .zip los cuestionarios PDF del curso (se admiten subcarpetas).\n"
            "2. Súbelo aquí. La app lee automáticamente las respuestas de cada formulario.\n"
            "3. Revisa la vista previa, ajusta las opciones del panel lateral y descarga el informe.")
    st.stop()

with st.spinner("Leyendo cuestionarios…"):
    try:
        cuestionarios, incidencias = _leer(archivo.getvalue())
    except Exception as e:  # zip dañado
        st.error(f"No se pudo abrir el .zip: {e}")
        st.stop()

if incidencias:
    with st.expander(f"⚠️ {len(incidencias)} archivo(s) no procesado(s)"):
        st.dataframe(pd.DataFrame(incidencias, columns=["Archivo", "Motivo"]), hide_index=True,
                     use_container_width=True)
if not cuestionarios:
    st.error("No se ha encontrado ningún cuestionario válido en el .zip.")
    st.stop()

# Si el zip mezcla varios cursos/grupos, se elige cuál informar
grupos = agrupar_por_curso(cuestionarios)
claves = list(grupos.keys())
if len(claves) > 1:
    st.warning(f"El .zip contiene cuestionarios de {len(claves)} acciones formativas o grupos distintos.")
    elegida = st.selectbox("Selecciona el curso del que generar el informe", claves,
                           format_func=lambda k: f"{k[0]} · AAFF {k[1]} / Grupo {k[2]} "
                                                 f"({len(grupos[k])} cuestionarios)")
else:
    elegida = claves[0]
seleccion = grupos[elegida]

# ------------------------------------------------------------------ panel lateral
with st.sidebar:
    st.header("⚙️ Opciones del informe")
    es_tele = detectar_teleformacion(seleccion)
    incluir7 = st.toggle("Valorar ítem 7 · Modalidad telemática o mixta", value=es_tele,
                         help="Actívalo solo si el curso se ha impartido en teleformación o modalidad mixta.")
    st.caption(f"Modalidad detectada en los cuestionarios: **{'Teleformación / Mixta' if es_tele else 'Presencial'}**")

    st.divider()
    st.subheader("🤖 Análisis con IA (opcional)")
    clave_secrets = _clave_api_secrets()
    usar_ia = st.toggle("Mejorar el análisis de comentarios con Claude", value=False,
                        help="Usa la API de Anthropic para el análisis cualitativo, el resumen ejecutivo "
                             "y las recomendaciones. Sin IA se usa el motor automático por reglas.")
    api_key, modelo = "", MODELO_POR_DEFECTO
    if usar_ia:
        if clave_secrets:
            api_key = clave_secrets
            st.success("Clave de API cargada desde los secrets de la app.")
        else:
            api_key = st.text_input("Clave de API de Anthropic", type="password")
        modelo = st.text_input("Modelo", value=MODELO_POR_DEFECTO)
        st.caption("Los comentarios de los participantes se envían a la API de Anthropic.")

# ------------------------------------------------------------------ análisis
firma = (elegida, incluir7, bool(api_key), modelo, len(seleccion))
if st.session_state.get("firma") != firma:
    with st.spinner("Analizando cuestionarios…" + (" (con IA)" if api_key else "")):
        st.session_state["resultado"] = procesar(seleccion, incluir7, api_key or None, modelo)
        st.session_state["firma"] = firma
        st.session_state.pop("pdf", None)
r = st.session_state["resultado"]
ficha, cuant, coment, concl = r["ficha"], r["cuant"], r["coment"], r["concl"]
if r["aviso"]:
    st.warning(r["aviso"])

# ------------------------------------------------------------------ vista previa
st.subheader(f"Informe Curso – {ficha['nombre']}")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Cuestionarios", ficha["n_cuestionarios"])
c2.metric("Valoración global", f"{fmt_exacto(concl['nota_10'], 1)} / 10")
c3.metric("Nivel de satisfacción", concl["nivel_general"])
rec = next((s for s in cuant["sino"] if s["codigo"] == "10.1"), None)
c4.metric("Recomendaría el curso", fmt_pct(rec["pct_si"]) if rec else "—")

t1, t2, t3, t4 = st.tabs(["1. Ficha", "2. Análisis cuantitativo", "3. Comentarios", "4. Conclusiones"])
with t1:
    st.table(pd.DataFrame({
        "Campo": ["Nombre del curso", "Sociedad bonificada (Nº Expediente)", "Nº acción formativa / Grupo",
                  "Nº cuestionarios", "Modalidad"],
        "Valor": [ficha["nombre"], ficha["expediente"] or "—", f"{ficha['num_aaff']} / {ficha['num_grupo']}",
                  str(ficha["n_cuestionarios"]), ficha["modalidad"] or "—"],
    }).set_index("Campo"))
with t2:
    filas = []
    for a in cuant["apartados"]:
        media = fmt_exacto(a["media"]) if a["tipo"] == "escala" else f"{fmt_pct(a.get('pct_si'))} Sí"
        filas.append({"Apartado principal": f"{a['num']}. {a['nombre']}", "Puntuación media": media,
                      "Nivel de satisfacción": ("🟢 " if a["nivel"] == "Satisfactorio" else "🔴 ") + a["nivel"]})
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
    graf = pd.DataFrame({"Apartado": [f"{a['num']}. {a['nombre']}" for a in cuant["apartados"] if a["media"]],
                         "Media": [a["media"] for a in cuant["apartados"] if a["media"]]}).set_index("Apartado")
    st.bar_chart(graf, horizontal=True)
    st.markdown("**Respuestas Sí / No (ítems 8 y 10)**")
    st.dataframe(pd.DataFrame([{"Ítem": f"{s['codigo']} {s['texto']}", "% Sí": fmt_pct(s["pct_si"]),
                                "% No": fmt_pct(s["pct_no"]), "Respuestas": s["n"]} for s in cuant["sino"]]),
                 hide_index=True, use_container_width=True)
with t3:
    st.caption(f"{coment['n_con_comentario']} de {ficha['n_cuestionarios']} participantes dejaron comentarios.")
    if coment["filas"]:
        st.dataframe(pd.DataFrame([{
            "Elemento valorado": f["elemento"], "Valor": f["valor"], "Frecuencia": f["frecuencia"],
            "Comentarios ilustrativos": " ‖ ".join(f"«{c}»" for c in f["comentarios"][:2]),
        } for f in coment["filas"]]), hide_index=True, use_container_width=True)
    else:
        st.info("No hay comentarios para analizar.")
with t4:
    st.markdown(f"**Resumen ejecutivo.** {concl['resumen']}")
    a, b = st.columns(2)
    with a:
        st.markdown("**Principales fortalezas**")
        st.markdown("\n".join(f"- {x}" for x in concl["fortalezas"]) or "—")
        for c in concl["comentarios_fortalezas"]:
            st.caption(f"«{c}»")
    with b:
        st.markdown("**Principales áreas de mejora**")
        st.markdown("\n".join(f"- {x}" for x in concl["areas_mejora"]) or "—")
        for c in concl["comentarios_mejora"]:
            st.caption(f"«{c}»")
    st.markdown("**Recomendaciones de ajuste**")
    st.dataframe(pd.DataFrame([{"Punto de mejora": x["punto"], "Comentario": x["comentario"],
                                "Acción recomendada": x["accion"]} for x in concl["recomendaciones"]]),
                 hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ descarga
st.divider()
if "pdf" not in st.session_state:
    with st.spinner("Generando PDF…"):
        st.session_state["pdf"] = generar_pdf(ficha, cuant, coment, concl, r["metodo"])
st.download_button("⬇️ Descargar informe en PDF", data=st.session_state["pdf"],
                   file_name=_nombre_archivo(ficha["nombre"]), mime="application/pdf",
                   type="primary", use_container_width=True)
