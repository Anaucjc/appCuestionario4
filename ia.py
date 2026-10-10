"""
Análisis opcional con IA (Claude, API de Anthropic).

Mejora la detección de elementos, el resumen ejecutivo y las recomendaciones.
Los comentarios se envían numerados (C1, C2...) y el modelo responde con esos
identificadores: así las citas del informe son SIEMPRE textuales y la
frecuencia se calcula contando participantes reales.
Si la llamada falla, la app usa automáticamente el motor por reglas.
"""
from __future__ import annotations

import json
import re

from .comentarios import es_comentario_valido
from .cuantitativo import fmt_exacto, fmt_pct

MODELO_POR_DEFECTO = "claude-sonnet-5-5"

INSTRUCCIONES = """Eres un técnico de formación experto en evaluación de la calidad de acciones formativas
(cuestionarios SEPE/FUNDAE). Analiza los comentarios abiertos de los participantes y los resultados
cuantitativos, y responde EXCLUSIVAMENTE con un objeto JSON válido (sin texto adicional) con esta forma:

{
  "elementos": [
    {"elemento": "nombre breve del aspecto del curso (p. ej. Formador / tutor, Duración del curso, Ritmo de impartición, Contenidos, Enfoque práctico, Materiales didácticos, Organización, Instalaciones y medios técnicos, Plataforma / formación online, Evaluación y acreditación, Aplicabilidad al puesto, Valoración general)",
     "valor": "Positivo" | "Negativo" | "Neutro",
     "ids": ["C1", "C4"],          // TODOS los comentarios que mencionan ese aspecto con ese valor
     "ejemplos": ["C1", "C4"]}     // los 2 comentarios que mejor lo ilustran (o 1 si solo hay uno)
  ],
  "resumen_ejecutivo": "Entre 5 y 8 líneas, en tono profesional, integrando datos cuantitativos y cualitativos.",
  "fortalezas": ["frase breve", "..."],
  "comentarios_fortalezas": ["Cx", "Cy"],
  "areas_mejora": ["frase breve", "..."],
  "comentarios_mejora": ["Cx", "Cy"],
  "recomendaciones": [
    {"punto": "punto de mejora", "comentario": "Cx" o null, "accion": "una acción concreta y realista para corregirlo"}
  ]
}

Reglas:
- Un mismo comentario puede mencionar varios aspectos con valores distintos (p. ej. positivo del profesor y negativo de la duración).
- Usa solo identificadores existentes. No inventes citas.
- Las áreas de mejora deben apoyarse en apartados con media < 3,00, en porcentajes bajos de «Sí» o en comentarios negativos.
- Escribe en español de España.
"""


def _contexto_cuantitativo(ficha: dict, cuant: dict) -> str:
    lineas = [f"Curso: {ficha['nombre']} · Cuestionarios: {ficha['n_cuestionarios']}",
              f"Valoración global: {fmt_exacto(cuant['nota_10'], 1)}/10 (media {fmt_exacto(cuant['media_global'])}/4)"]
    for a in cuant["apartados"]:
        if a["media"] is not None:
            lineas.append(f"- {a['num']}. {a['nombre']}: media {fmt_exacto(a['media'])} ({a['nivel']})")
    for s in cuant["sino"]:
        lineas.append(f"- {s['codigo']} {s['texto']}: Sí {fmt_pct(s['pct_si'])} / No {fmt_pct(s['pct_no'])}")
    return "\n".join(lineas)


def analizar_con_ia(api_key: str, ficha: dict, cuant: dict, comentarios: list[str],
                    modelo: str = MODELO_POR_DEFECTO) -> tuple[dict, dict]:
    """Devuelve (analisis_comentarios, conclusiones_parciales) con la misma forma que el motor por reglas."""
    import anthropic  # importación diferida: solo necesaria si se usa la IA

    validos = [(i, c) for i, c in enumerate(comentarios) if c and es_comentario_valido(c)]
    mapa = {f"C{k + 1}": (i, c) for k, (i, c) in enumerate(validos)}
    bloque = "\n".join(f"{cid}: {c}" for cid, (_, c) in mapa.items()) or "(sin comentarios)"

    cliente = anthropic.Anthropic(api_key=api_key)
    respuesta = cliente.messages.create(
        model=modelo,
        max_tokens=6000,
        system=INSTRUCCIONES,
        messages=[{"role": "user", "content":
                   f"RESULTADOS CUANTITATIVOS\n{_contexto_cuantitativo(ficha, cuant)}\n\n"
                   f"COMENTARIOS DEL ÍTEM 11\n{bloque}"}],
    )
    texto = "".join(b.text for b in respuesta.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", texto, re.DOTALL)
    if not m:
        raise ValueError("La IA no devolvió un JSON válido")
    datos = json.loads(m.group(0))

    def cita(cid):
        return mapa[cid][1] if cid in mapa else None

    filas = []
    for e in datos.get("elementos", []):
        ids = [x for x in dict.fromkeys(e.get("ids", [])) if x in mapa]
        if not ids:
            continue
        ejemplos = [cita(x) for x in e.get("ejemplos", []) if cita(x)] or [cita(ids[0])]
        valor = str(e.get("valor", "Neutro")).capitalize()
        filas.append({
            "elemento": str(e.get("elemento", "Otro")), "apartado": None,
            "valor": valor if valor in ("Positivo", "Negativo", "Neutro") else "Neutro",
            "frecuencia": len(ids), "comentarios": ejemplos[:2], "ids": [mapa[x][0] for x in ids],
        })
    filas.sort(key=lambda f: (-f["frecuencia"], f["elemento"]))

    conclusiones = {
        "resumen": datos.get("resumen_ejecutivo", "").strip(),
        "fortalezas": [str(x) for x in datos.get("fortalezas", [])],
        "comentarios_fortalezas": [cita(x) for x in datos.get("comentarios_fortalezas", []) if cita(x)][:2],
        "areas_mejora": [str(x) for x in datos.get("areas_mejora", [])],
        "comentarios_mejora": [cita(x) for x in datos.get("comentarios_mejora", []) if cita(x)][:2],
        "recomendaciones": [
            {"punto": str(r.get("punto", "")),
             "comentario": cita(r.get("comentario")) or
             "No hay comentarios de los participantes que hagan referencia a este aspecto.",
             "accion": str(r.get("accion", ""))}
            for r in datos.get("recomendaciones", [])
        ],
    }
    return {"filas": filas, "n_con_comentario": len(validos)}, conclusiones
