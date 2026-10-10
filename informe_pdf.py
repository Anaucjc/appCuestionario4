"""Generación del informe en PDF (ReportLab + Matplotlib)."""
from __future__ import annotations

import io
import os
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph,  # noqa: E402
                                SimpleDocTemplate, Spacer, Table, TableStyle)
from xml.sax.saxutils import escape  # noqa: E402

from .cuantitativo import fmt_exacto, fmt_pct  # noqa: E402

# ----------------------------------------------------------------- tipografía
_FUENTES = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(_FUENTES, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", os.path.join(_FUENTES, "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont("DejaVu-Italic", os.path.join(_FUENTES, "DejaVuSans-Oblique.ttf")))
pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold", italic="DejaVu-Italic")

# ----------------------------------------------------------------- paleta
AZUL = colors.HexColor("#1F3A5F")
AZUL_CLARO = colors.HexColor("#E8EEF5")
GRIS = colors.HexColor("#5B6573")
GRIS_LINEA = colors.HexColor("#CBD3DD")
VERDE = colors.HexColor("#1E7B45")
VERDE_FONDO = colors.HexColor("#E3F2E8")
ROJO = colors.HexColor("#B42318")
ROJO_FONDO = colors.HexColor("#FBE7E5")
AMBAR_FONDO = colors.HexColor("#FFF4E0")

E = {
    "titulo": ParagraphStyle("titulo", fontName="DejaVu-Bold", fontSize=19, leading=24, textColor=colors.white),
    "subtitulo": ParagraphStyle("sub", fontName="DejaVu", fontSize=9.5, leading=13, textColor=colors.HexColor("#D6E0EC")),
    "h1": ParagraphStyle("h1", fontName="DejaVu-Bold", fontSize=13.5, leading=18, textColor=AZUL, spaceBefore=14, spaceAfter=6, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="DejaVu-Bold", fontSize=10.5, leading=14, textColor=AZUL, spaceBefore=9, spaceAfter=4, keepWithNext=1),
    "cuerpo": ParagraphStyle("cuerpo", fontName="DejaVu", fontSize=9.3, leading=13.5, textColor=colors.HexColor("#1D2430")),
    "celda": ParagraphStyle("celda", fontName="DejaVu", fontSize=8.4, leading=11, textColor=colors.HexColor("#1D2430")),
    "celda_b": ParagraphStyle("celda_b", fontName="DejaVu-Bold", fontSize=8.4, leading=11, textColor=colors.HexColor("#1D2430")),
    "cab": ParagraphStyle("cab", fontName="DejaVu-Bold", fontSize=8.4, leading=11, textColor=colors.white),
    "cita": ParagraphStyle("cita", fontName="DejaVu-Italic", fontSize=8.6, leading=12, textColor=colors.HexColor("#36404D"),
                           leftIndent=10, borderPadding=(4, 6, 4, 8), spaceBefore=3, spaceAfter=3),
    "nota": ParagraphStyle("nota", fontName="DejaVu", fontSize=7.4, leading=10, textColor=GRIS),
    "vinieta": ParagraphStyle("vin", fontName="DejaVu", fontSize=9.2, leading=13, leftIndent=12, bulletIndent=2),
    "nota_grande": ParagraphStyle("ng", fontName="DejaVu-Bold", fontSize=30, leading=34, textColor=AZUL, alignment=TA_CENTER),
    "centro": ParagraphStyle("centro", fontName="DejaVu", fontSize=8.5, leading=11, textColor=GRIS, alignment=TA_CENTER),
}


def P(texto, estilo="celda"):
    return Paragraph(escape(str(texto)), E[estilo])


def _nivel_celda(nivel: str):
    color = VERDE if nivel == "Satisfactorio" else ROJO if nivel == "No satisfactorio" else GRIS
    return Paragraph(f'<font color="{color.hexval()}"><b>{"● " if nivel != "Sin datos" else ""}{escape(nivel)}</b></font>',
                     E["celda"])


def _tabla(datos, anchos, cabecera=True, cebra=True, extra=None):
    t = Table(datos, colWidths=anchos, repeatRows=1 if cabecera else 0)
    estilo = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, GRIS_LINEA),
    ]
    if cabecera:
        estilo += [("BACKGROUND", (0, 0), (-1, 0), AZUL)]
    if cebra:
        for i in range(1 if cabecera else 0, len(datos)):
            if i % 2 == 0:
                estilo.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F6F8FB")))
    t.setStyle(TableStyle(estilo + (extra or [])))
    return t


def _grafico_apartados(cuant) -> io.BytesIO:
    aps = [a for a in cuant["apartados"] if a["media"] is not None][::-1]
    plt.rcParams["font.family"] = "DejaVu Sans"
    fig, ax = plt.subplots(figsize=(7.2, 0.42 * len(aps) + 0.9), dpi=200)
    etiquetas = [f"{a['num']}. {a['nombre']}" for a in aps]
    valores = [a["media"] for a in aps]
    col = ["#2E5E8C" if v >= 3 else "#B42318" for v in valores]
    barras = ax.barh(etiquetas, valores, color=col, height=0.55, zorder=3)
    ax.axvline(3, color="#5B6573", lw=1, ls=(0, (4, 3)), zorder=4)
    ax.set_ylim(-0.6, len(aps) - 0.1)
    ax.text(3, len(aps) - 0.1, "umbral satisfactorio (3,00)", fontsize=7, color="#5B6573", va="bottom", ha="center")
    for b, v in zip(barras, valores):  # valores alineados en una columna a la derecha
        ax.text(4.12, b.get_y() + b.get_height() / 2, fmt_exacto(v), va="center", ha="left", fontsize=7.5,
                color="#1D2430", fontweight="bold")
    ax.set_xlim(1, 4.45)
    ax.set_xticks([1, 2, 3, 4])
    ax.tick_params(axis="both", labelsize=7.5, colors="#36404D", length=0)
    ax.grid(axis="x", color="#E3E8EF", lw=0.6, zorder=0)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#CBD3DD")
    ax.set_xlabel("Puntuación media (escala 1–4)", fontsize=7.5, color="#5B6573")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


def generar_pdf(ficha: dict, cuant: dict, coment: dict, concl: dict, metodo: str = "reglas") -> bytes:
    buf = io.BytesIO()
    titulo = f"Informe Curso – {ficha['nombre']}"
    ancho = A4[0] - 3.6 * cm

    def pie(canvas, doc):
        canvas.saveState()
        canvas.setFont("DejaVu", 7.2)
        canvas.setFillColor(GRIS)
        canvas.drawString(1.8 * cm, 1.1 * cm, titulo[:95])
        canvas.drawRightString(A4[0] - 1.8 * cm, 1.1 * cm, f"Página {doc.page}")
        canvas.setStrokeColor(GRIS_LINEA)
        canvas.line(1.8 * cm, 1.4 * cm, A4[0] - 1.8 * cm, 1.4 * cm)
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                            topMargin=1.6 * cm, bottomMargin=1.8 * cm, title=titulo,
                            author="Técnico de formación", subject="Evaluación de la calidad de la acción formativa")
    h = []

    # ---------------------------------------------------------------- portada
    cab = Table([[Paragraph(escape(titulo), E["titulo"])],
                 [Paragraph(f"Evaluación de la calidad de la acción formativa · Emitido el "
                            f"{date.today().strftime('%d/%m/%Y')}", E["subtitulo"])]],
                colWidths=[ancho])
    cab.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), AZUL),
                             ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                             ("TOPPADDING", (0, 0), (-1, 0), 14), ("BOTTOMPADDING", (0, -1), (-1, -1), 12)]))
    h += [cab, Spacer(1, 10)]

    # ---------------------------------------------------------------- 1. Ficha
    h.append(Paragraph("1. Ficha del curso", E["h1"]))
    filas = [
        ["Nombre del curso", ficha["nombre"]],
        ["Sociedad bonificada (Nº Expediente)", ficha["expediente"] or "—"],
        ["Nº acción formativa / Grupo", f"{ficha['num_aaff'] or '—'} / {ficha['num_grupo'] or '—'}"],
        ["Nº cuestionarios", str(ficha["n_cuestionarios"])],
        ["Modalidad", ficha.get("modalidad") or "—"],
    ]
    h.append(_tabla([[P(a, "celda_b"), P(b)] for a, b in filas], [6.2 * cm, ancho - 6.2 * cm],
                    cabecera=False, extra=[("BACKGROUND", (0, 0), (0, -1), AZUL_CLARO)]))

    # ---------------------------------------------------------------- 2. Cuantitativo
    h.append(Paragraph("2. Análisis cuantitativo", E["h1"]))
    h.append(Paragraph("Valoración de los ítems 1 a 10 del apartado III del cuestionario (escala 1 = completamente "
                       "en desacuerdo a 4 = completamente de acuerdo). La puntuación de cada apartado es la media de "
                       "sus sub-ítems; las respuestas «No contesta» no se computan.", E["cuerpo"]))
    h.append(Spacer(1, 6))
    datos = [[P("Apartado principal", "cab"), P("Puntuación media", "cab"), P("Nivel de satisfacción", "cab")]]
    for a in cuant["apartados"]:
        media = fmt_exacto(a["media"]) if a["tipo"] == "escala" else f"{fmt_pct(a.get('pct_si'))} «Sí» *"
        datos.append([P(f"{a['num']}. {a['nombre']}"), P(media), _nivel_celda(a["nivel"])])
    h.append(_tabla(datos, [9.4 * cm, 3.4 * cm, ancho - 12.8 * cm]))
    notas = "Puntuaciones exactas, truncadas a dos decimales (sin redondeo). 1,00–2,99: No satisfactorio · " \
            "3,00–4,00: Satisfactorio."
    if any(a["tipo"] == "sino" for a in cuant["apartados"]):
        notas += " * El ítem 8 se responde con Sí/No: se muestra el % medio de «Sí» y se considera satisfactorio " \
                 "si es igual o superior al 50 %."
    if not any(a["num"] == 7 for a in cuant["apartados"]):
        notas += " El ítem 7 (modalidad telemática o mixta) no se valora en este informe."
    h += [Spacer(1, 3), Paragraph(notas, E["nota"]), Spacer(1, 8)]
    h.append(Image(_grafico_apartados(cuant), width=ancho, height=ancho * (0.42 * len(
        [a for a in cuant["apartados"] if a["media"] is not None]) + 0.9) / 7.2))

    # Sí / No
    if cuant["sino"]:
        h.append(Paragraph("Respuestas Sí / No (ítems 8 y 10)", E["h2"]))
        datos = [[P("Ítem", "cab"), P("% Sí", "cab"), P("% No", "cab"), P("Respuestas", "cab")]]
        for s in cuant["sino"]:
            datos.append([P(f"{s['codigo']} {s['texto']}"), P(fmt_pct(s["pct_si"])), P(fmt_pct(s["pct_no"])),
                          P(f"{s['n']} (sin respuesta: {s['sin_respuesta']})")])
        h.append(_tabla(datos, [8.6 * cm, 2 * cm, 2 * cm, ancho - 12.6 * cm]))

    # Subapartados
    for i, a in enumerate(cuant["apartados"], start=1):
        bloque = [Paragraph(f"2.{i}. {a['nombre']}", E["h2"])]
        if a["tipo"] == "escala":
            datos = [[P("Sub-ítem", "cab"), P("Media", "cab"), P("1", "cab"), P("2", "cab"), P("3", "cab"),
                      P("4", "cab"), P("N", "cab")]]
            for s in a["subitems"]:
                d = s["dist"]
                datos.append([P(f"{s['codigo']} {s['texto']}"), P(fmt_exacto(s["media"]), "celda_b"),
                              P(d[1]), P(d[2]), P(d[3]), P(d[4]), P(s["n"])])
            datos.append([P("Puntuación media del apartado", "celda_b"), P(fmt_exacto(a["media"]), "celda_b"),
                          _nivel_celda(a["nivel"]), "", "", "", ""])
            w = [ancho - 2 * cm - 5 * 1.15 * cm, 2 * cm] + [1.15 * cm] * 5
            t = _tabla(datos, w, extra=[("SPAN", (2, -1), (-1, -1)),
                                         ("BACKGROUND", (0, -1), (-1, -1), AZUL_CLARO)])
            bloque.append(t)
            bloque.append(Paragraph("Columnas 1–4: número de respuestas en cada valor de la escala. "
                                    "N: respuestas válidas.", E["nota"]))
        else:
            datos = [[P("Sub-ítem", "cab"), P("% Sí", "cab"), P("% No", "cab"), P("N", "cab")]]
            for s in a["subitems"]:
                datos.append([P(f"{s['codigo']} {s['texto']}"), P(fmt_pct(s["pct_si"]), "celda_b"),
                              P(fmt_pct(s["pct_no"])), P(s["n"])])
            datos.append([P("Nivel de satisfacción del apartado", "celda_b"), _nivel_celda(a["nivel"]), "", ""])
            bloque.append(_tabla(datos, [ancho - 6 * cm, 2.2 * cm, 2.2 * cm, 1.6 * cm],
                                 extra=[("SPAN", (1, -1), (-1, -1)), ("BACKGROUND", (0, -1), (-1, -1), AZUL_CLARO)]))
        for s in a.get("sino_subitems", []):
            bloque.append(Spacer(1, 4))
            bloque.append(_tabla([[P("Ítem", "cab"), P("% Sí", "cab"), P("% No", "cab"), P("N", "cab")],
                                  [P(f"{s['codigo']} {s['texto']}"), P(fmt_pct(s["pct_si"]), "celda_b"),
                                   P(fmt_pct(s["pct_no"])), P(s["n"])]],
                                 [ancho - 6 * cm, 2.2 * cm, 2.2 * cm, 1.6 * cm]))
        h.append(KeepTogether(bloque))

    # ---------------------------------------------------------------- 3. Comentarios
    h.append(PageBreak())
    h.append(Paragraph("3. Análisis de comentarios", E["h1"]))
    total = ficha["n_cuestionarios"]
    h.append(Paragraph(f"Análisis del texto del ítem 11 (sugerencias y observaciones). "
                       f"{coment['n_con_comentario']} de {total} participantes dejaron algún comentario. "
                       f"La frecuencia indica cuántos participantes distintos mencionan cada elemento con ese valor.",
                       E["cuerpo"]))
    h.append(Spacer(1, 6))
    if coment["filas"]:
        datos = [[P("Elemento valorado", "cab"), P("Valor", "cab"), P("Frec.", "cab"),
                  P("Comentarios ilustrativos", "cab")]]
        extra = []
        for r, f in enumerate(coment["filas"], start=1):
            citas = "<br/><br/>".join(f"«{escape(c)}»" for c in f["comentarios"][:2])
            datos.append([P(f["elemento"], "celda_b"), _valor_celda(f["valor"]), P(str(f["frecuencia"])),
                          Paragraph(f"<i>{citas}</i>", E["celda"])])
        h.append(_tabla(datos, [3.6 * cm, 2.5 * cm, 1.5 * cm, ancho - 7.6 * cm], extra=extra))
    else:
        h.append(Paragraph("No hay comentarios suficientes para realizar el análisis cualitativo.", E["cuerpo"]))

    # ---------------------------------------------------------------- 4. Conclusiones
    h.append(Paragraph("4. Conclusiones y recomendaciones", E["h1"]))
    color_nivel = VERDE if concl["nivel_general"] == "Satisfactorio" else ROJO
    fondo_nivel = VERDE_FONDO if concl["nivel_general"] == "Satisfactorio" else ROJO_FONDO
    caja = Table([[Paragraph(f"{fmt_exacto(concl['nota_10'], 1)}<font size=13 color='#5B6573'> / 10</font>",
                             E["nota_grande"]),
                   Paragraph(f"<font color='{color_nivel.hexval()}'><b>{escape(concl['nivel_general'])}</b></font>",
                             ParagraphStyle("niv", parent=E["nota_grande"], fontSize=15, leading=19))],
                  [Paragraph("Valoración global del curso", E["centro"]),
                   Paragraph("Nivel de satisfacción general", E["centro"])]],
                 colWidths=[ancho / 2, ancho / 2])
    caja.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), AZUL_CLARO), ("BACKGROUND", (1, 0), (1, -1), fondo_nivel),
                              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, 0), 12),
                              ("BOTTOMPADDING", (0, -1), (-1, -1), 10), ("LINEAFTER", (0, 0), (0, -1), 3, colors.white)]))
    h += [caja, Paragraph("Valoración 0–10 = (media de los apartados − 1) / 3 × 10, a partir de la escala 1–4.",
                          E["nota"])]

    h.append(Paragraph("Resumen ejecutivo", E["h2"]))
    h.append(Paragraph(escape(concl["resumen"]), E["cuerpo"]))

    h.append(Paragraph("Principales fortalezas", E["h2"]))
    h += _vinietas(concl["fortalezas"] or ["No se identifican fortalezas destacadas."])
    h += _citas(concl["comentarios_fortalezas"], VERDE_FONDO)

    h.append(Paragraph("Principales áreas de mejora", E["h2"]))
    h += _vinietas(concl["areas_mejora"] or ["No se identifican áreas de mejora relevantes."])
    h += _citas(concl["comentarios_mejora"], AMBAR_FONDO)

    h.append(Paragraph("Recomendaciones de ajuste", E["h2"]))
    if concl["recomendaciones"]:
        datos = [[P("Punto de mejora", "cab"), P("Comentario de un participante", "cab"), P("Acción recomendada", "cab")]]
        for r in concl["recomendaciones"]:
            datos.append([P(r["punto"], "celda_b"), Paragraph(f"<i>«{escape(r['comentario'])}»</i>", E["celda"]),
                          P(r["accion"])])
        h.append(_tabla(datos, [4 * cm, (ancho - 4 * cm) / 2, (ancho - 4 * cm) / 2]))
    else:
        h.append(Paragraph("No se requieren ajustes significativos.", E["cuerpo"]))

    h += [Spacer(1, 12), Paragraph(
        "Análisis cualitativo realizado con " + ("inteligencia artificial (Claude, Anthropic) sobre los comentarios "
                                                 "literales; las citas son textuales." if metodo == "ia" else
                                                 "un motor automático de detección de temas y opiniones; "
                                                 "las citas son textuales.") +
        " Se recomienda revisión por parte del técnico de formación.", E["nota"])]

    doc.build(h, onFirstPage=pie, onLaterPages=pie)
    return buf.getvalue()


def _valor_celda(valor):
    c = {"Positivo": VERDE, "Negativo": ROJO}.get(valor, GRIS)
    simbolo = {"Positivo": "▲", "Negativo": "▼"}.get(valor, "●")
    return Paragraph(f'<font color="{c.hexval()}"><b>{simbolo} {valor}</b></font>', E["celda"])


def _vinietas(items):
    return [Paragraph(escape(i), E["vinieta"], bulletText="•") for i in items]


def _citas(citas, fondo):
    out = []
    for c in citas:
        t = Table([[Paragraph(f"«{escape(c)}»", E["cita"])]], colWidths=[A4[0] - 3.6 * cm - 0.6 * cm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), fondo),
                               ("LINEBEFORE", (0, 0), (0, -1), 2.5, GRIS),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        out += [Spacer(1, 3), t]
    return out
