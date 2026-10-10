"""Conclusiones y recomendaciones (apartado 4 del informe)."""
from __future__ import annotations

from .comentarios import ACCIONES, ACCIONES_APARTADO, ELEMENTO_DE_APARTADO
from .cuantitativo import UMBRAL_SATISFACTORIO, fmt_exacto, fmt_pct

SIN_COMENTARIO = "No hay comentarios de los participantes que hagan referencia a este aspecto."


def _lista_humana(items: list[str]) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " y " + items[-1]


def elaborar(ficha: dict, cuant: dict, coment: dict) -> dict:
    escalas = [a for a in cuant["apartados"] if a["media"] is not None]
    ordenados = sorted(escalas, key=lambda a: -a["media"])
    filas = coment["filas"]
    positivos = [f for f in filas if f["valor"] == "Positivo"]
    negativos = [f for f in filas if f["valor"] == "Negativo"]

    recomienda = next((s for s in cuant["sino"] if s["codigo"] == "10.1"), None)
    satisf = next((a for a in cuant["apartados"] if a["num"] == 10), None)

    # ---------------- Fortalezas ----------------
    fortalezas = []
    for a in ordenados[:3]:
        if a["media"] >= UMBRAL_SATISFACTORIO:
            fortalezas.append(f"{a['nombre']} (media {fmt_exacto(a['media'])} sobre 4)")
    for f in positivos[:3]:
        fortalezas.append(f"{f['elemento']}: valorado positivamente por {f['frecuencia']} "
                          f"participante{'s' if f['frecuencia'] != 1 else ''} en los comentarios")
    com_fortalezas = _recoger_citas(positivos, 2)

    # ---------------- Áreas de mejora ----------------
    bajos = [a for a in ordenados[::-1] if a["media"] < UMBRAL_SATISFACTORIO]
    relativos = False
    if not bajos and not negativos:
        bajos = ordenados[::-1][:2]  # sin suspensos: se señalan los dos apartados con menor media
        relativos = True
    areas = []
    for a in bajos[:4]:
        etiqueta = "menor puntuación relativa" if relativos else "por debajo del umbral satisfactorio"
        areas.append(f"{a['nombre']} (media {fmt_exacto(a['media'])}, {etiqueta})")
    sino_bajos = [s for s in cuant["sino"] if s["pct_si"] is not None and s["pct_si"] < 50]
    for s in sino_bajos:
        areas.append(f"{s['codigo']} {s['texto']} (solo un {fmt_pct(s['pct_si'])} responde «Sí»)")
    for f in negativos[:3]:
        areas.append(f"{f['elemento']}: señalado como mejorable por {f['frecuencia']} "
                     f"participante{'s' if f['frecuencia'] != 1 else ''}")
    com_mejora = _recoger_citas(negativos, 2)

    # ---------------- Recomendaciones ----------------
    recomendaciones, vistos = [], set()
    for f in negativos:
        if f["elemento"] in vistos:
            continue
        vistos.add(f["elemento"])
        recomendaciones.append({
            "punto": f"{f['elemento']} ({f['frecuencia']} {'mención negativa' if f['frecuencia'] == 1 else 'menciones negativas'})",
            "comentario": f["comentarios"][0],
            "accion": ACCIONES.get(f["elemento"], ACCIONES["Valoración general"]),
        })
    for a in bajos:
        elem = ELEMENTO_DE_APARTADO.get(a["num"])
        if elem in vistos:
            continue
        vistos.add(elem)
        cita = next((f["comentarios"][0] for f in negativos if f["apartado"] == a["num"]), SIN_COMENTARIO)
        recomendaciones.append({
            "punto": f"{a['nombre']} (media {fmt_exacto(a['media'])})",
            "comentario": cita,
            "accion": ACCIONES_APARTADO[a["num"]],
        })
    for s in sino_bajos:
        if "Evaluación y acreditación" in vistos and s["codigo"].startswith("8"):
            continue
        clave = "Evaluación y acreditación" if s["codigo"].startswith("8") else "Valoración general"
        vistos.add(clave)
        recomendaciones.append({
            "punto": f"{s['codigo']} {s['texto']} ({fmt_pct(s['pct_si'])} «Sí»)",
            "comentario": next((f["comentarios"][0] for f in negativos if f["elemento"] == clave), SIN_COMENTARIO),
            "accion": ACCIONES[clave],
        })

    # ---------------- Resumen ejecutivo ----------------
    n = ficha["n_cuestionarios"]
    lineas = [
        f"Se han analizado {n} cuestionario{'s' if n != 1 else ''} de la acción formativa «{ficha['nombre']}» "
        f"(AAFF {ficha['num_aaff']} / grupo {ficha['num_grupo']}).",
        f"La valoración global alcanza {fmt_exacto(cuant['nota_10'], 1)} sobre 10 "
        f"(media {fmt_exacto(cuant['media_global'])} sobre 4), con un nivel de satisfacción general "
        f"«{cuant['nivel_global']}».",
    ]
    if satisf and satisf["media"] is not None:
        txt = f"El grado de satisfacción general con el curso obtiene una media de {fmt_exacto(satisf['media'])}"
        if recomienda and recomienda["pct_si"] is not None:
            txt += f" y el {fmt_pct(recomienda['pct_si'])} de quienes responden recomendaría el curso"
        lineas.append(txt + ".")
    if ordenados:
        lineas.append(f"Los apartados mejor valorados son {_lista_humana([a['nombre'] for a in ordenados[:2]])}, "
                      f"mientras que {_lista_humana([a['nombre'] for a in ordenados[::-1][:2]])} "
                      f"obtienen las puntuaciones más bajas.")
    if coment["n_con_comentario"]:
        txt = f"{coment['n_con_comentario']} participante{'s' if coment['n_con_comentario'] != 1 else ''} " \
              f"aportaron observaciones abiertas"
        if positivos:
            txt += f"; destacan positivamente {_lista_humana([f['elemento'].lower() for f in positivos[:2]])}"
        if negativos:
            txt += f", y se señalan como mejorables {_lista_humana([f['elemento'].lower() for f in negativos[:2]])}"
        lineas.append(txt + ".")
    else:
        lineas.append("No se recibieron observaciones abiertas en el ítem 11.")
    if recomendaciones:
        lineas.append(f"Se proponen {len(recomendaciones)} ajuste{'s' if len(recomendaciones) != 1 else ''} "
                      f"para próximas ediciones, priorizando {recomendaciones[0]['punto'].split(' (')[0].lower()}.")
    else:
        lineas.append("No se detectan aspectos críticos; se recomienda mantener el diseño actual de la acción.")

    return {
        "nota_10": cuant["nota_10"],
        "nivel_general": cuant["nivel_global"],
        "resumen": " ".join(lineas),
        "fortalezas": fortalezas,
        "comentarios_fortalezas": com_fortalezas,
        "areas_mejora": areas,
        "comentarios_mejora": com_mejora,
        "recomendaciones": recomendaciones,
    }


def _recoger_citas(filas: list[dict], n: int) -> list[str]:
    citas = []
    for f in filas:
        for c in f["comentarios"]:
            if c not in citas:
                citas.append(c)
                break
        if len(citas) >= n:
            break
    if len(citas) < n:
        for f in filas:
            for c in f["comentarios"]:
                if c not in citas and len(citas) < n:
                    citas.append(c)
    return citas
