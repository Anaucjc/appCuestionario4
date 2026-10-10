"""Análisis cuantitativo de los ítems 1 a 10 del apartado III."""
from __future__ import annotations

import math
from collections import Counter

from .lector import APARTADOS, Cuestionario

UMBRAL_SATISFACTORIO = 3.0  # 1,00–2,99 No satisfactorio · 3,00–4,00 Satisfactorio


def nivel(media: float | None) -> str:
    if media is None:
        return "Sin datos"
    return "Satisfactorio" if media >= UMBRAL_SATISFACTORIO else "No satisfactorio"


def fmt_exacto(x: float | None, dec: int = 2) -> str:
    """Formato con coma decimal TRUNCANDO (no redondea): 2,996 -> '2,99'."""
    if x is None:
        return "—"
    factor = 10 ** dec
    t = math.floor(x * factor + 1e-9) / factor
    return f"{t:.{dec}f}".replace(".", ",")


def fmt_pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.1f} %".replace(".", ",")


def _sino_stats(valores: list) -> dict:
    validos = [v for v in valores if v in ("Sí", "No")]
    n = len(validos)
    si = sum(1 for v in validos if v == "Sí")
    return {
        "n": n,
        "si": si,
        "no": n - si,
        "pct_si": (si / n * 100) if n else None,
        "pct_no": ((n - si) / n * 100) if n else None,
        "sin_respuesta": len(valores) - n,
    }


def analizar(cuestionarios: list[Cuestionario], incluir_item7: bool) -> dict:
    """Devuelve la estructura completa del análisis cuantitativo."""
    resultado = {"apartados": [], "sino": []}
    for ap in APARTADOS:
        if ap["num"] == 7 and not incluir_item7:
            continue
        bloque = {"num": ap["num"], "nombre": ap["nombre"], "tipo": ap["tipo"], "subitems": []}

        if ap["tipo"] == "escala":
            medias = []
            for cod, texto, campo in ap["items"]:
                vals = [q.escala.get(campo) for q in cuestionarios]
                validos = [v for v in vals if isinstance(v, int)]
                dist = Counter(validos)
                media = sum(validos) / len(validos) if validos else None
                if media is not None:
                    medias.append(media)
                bloque["subitems"].append({
                    "codigo": cod, "texto": texto, "media": media, "n": len(validos),
                    "sin_respuesta": len(vals) - len(validos),
                    "dist": {k: dist.get(k, 0) for k in (1, 2, 3, 4)},
                })
            # Media del apartado = media de las medias de sus sub-ítems
            bloque["media"] = sum(medias) / len(medias) if medias else None
            bloque["nivel"] = nivel(bloque["media"])
        else:  # Sí / No (ítem 8)
            pcts = []
            for cod, texto, campo in ap["items"]:
                st = _sino_stats([q.sino.get(campo) for q in cuestionarios])
                st.update({"codigo": cod, "texto": texto})
                bloque["subitems"].append(st)
                resultado["sino"].append({**st, "apartado": ap["nombre"]})
                if st["pct_si"] is not None:
                    pcts.append(st["pct_si"])
            bloque["media"] = None
            bloque["pct_si"] = sum(pcts) / len(pcts) if pcts else None
            bloque["nivel"] = ("Sin datos" if bloque["pct_si"] is None
                               else "Satisfactorio" if bloque["pct_si"] >= 50 else "No satisfactorio")

        for cod, texto, campo in ap.get("sino_items", []):  # 10.1 ¿Recomendaría?
            st = _sino_stats([q.sino.get(campo) for q in cuestionarios])
            st.update({"codigo": cod, "texto": texto})
            bloque.setdefault("sino_subitems", []).append(st)
            resultado["sino"].append({**st, "apartado": ap["nombre"]})

        resultado["apartados"].append(bloque)

    escalas = [a for a in resultado["apartados"] if a["media"] is not None]
    media_global = sum(a["media"] for a in escalas) / len(escalas) if escalas else None
    resultado["media_global"] = media_global
    # Escala 1–4 convertida linealmente a 0–10
    resultado["nota_10"] = (media_global - 1) / 3 * 10 if media_global is not None else None
    resultado["nivel_global"] = nivel(media_global)
    return resultado
