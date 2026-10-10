"""
Análisis de los comentarios abiertos (ítem 11).

Motor por reglas (funciona sin conexión): divide cada comentario en fragmentos,
detecta el elemento del curso al que se refiere cada fragmento mediante un
diccionario temático y estima su valor (positivo / negativo / neutro) con un
léxico de opinión en español que tiene en cuenta negaciones y sugerencias de
mejora ("sería mejor...", "más tiempo...", "faltó...").
"""
from __future__ import annotations

import re
from collections import defaultdict

from .lector import normalizar

# Elemento -> (apartado relacionado, claves fuertes, claves débiles)
# Coincidencia por palabra completa; un "*" final indica raíz (p. ej. "explic*" = explica, explicaciones...).
# Las claves débiles solo cuentan si el fragmento no menciona ningún otro elemento.
ELEMENTOS = {
    "Formador / tutor": (4, ["profesor*", "profe", "profes", "docente*", "formador*", "tutor", "tutora",
                             "tutores", "tutoras", "tutoria*", "ponente*", "instructor*", "explic*",
                             "imparte", "impartido", "imparticion"], []),
    "Duración del curso": (3, ["duracion", "tiempo", "horas", "corto", "corta", "intensivo", "mas dias",
                               "mas sesiones", "pocas sesiones", "se queda corto", "largo", "larga"], []),
    "Horario": (3, ["horario*", "por la tarde", "por la manana", "jornada", "hora de inicio",
                    "a ultima hora"], []),
    "Ritmo de impartición": (2, ["ritmo", "demasiado rapido", "muy rapido", "deprisa", "despacio", "lento",
                                 "lenta", "prisa*", "seguirlo", "seguir el", "costado seguir", "acelerado",
                                 "con calma"], []),
    "Contenidos": (2, ["contenido*", "conceptos", "programa", "nivel avanzado", "nivel basico",
                       "muy basico", "muy avanzado"], ["temario", "tema", "temas", "materia", "nivel",
                                                       "avanzado", "basico", "actualizado*"]),
    "Enfoque práctico": (2, ["practica", "practicas", "practico", "ejercicio*", "casos", "caso real",
                             "ejemplo*", "taller*", "role play", "simulacion*", "demasiada teoria",
                             "mucha teoria", "muy teorico", "demasiado teorico", "teoria"], []),
    "Materiales didácticos": (5, ["material", "materiales", "documentacion", "manual", "manuales", "apuntes",
                                  "presentacion*", "diapositiva*", "recursos", "guia", "guias",
                                  "bibliografia", "plantilla*"], []),
    "Organización": (1, ["organizacion", "organizado", "desorganiz*", "informacion previa", "fechas",
                         "convocatoria", "coordinacion", "comunicacion"], ["grupo", "alumnos", "companeros"]),
    "Instalaciones y medios técnicos": (6, ["aula", "sala", "instalacion*", "proyector", "ordenador*",
                                            "pantalla*", "wifi", "sonido", "equipos informaticos",
                                            "equipamiento", "temperatura", "calefaccion", "aire acondicionado",
                                            "sillas", "mesas"], []),
    "Plataforma / formación online": (7, ["plataforma*", "campus", "online", "on line", "virtual",
                                          "conexion", "zoom", "teams", "videoconferencia*", "streaming",
                                          "telematic*"], []),
    "Evaluación y acreditación": (8, ["evaluacion", "examen", "examenes", "test", "certificado",
                                      "certificacion", "acreditacion", "diploma", "autoevaluacion"], []),
    "Aplicabilidad al puesto": (9, ["aplicar", "aplicable", "aplicarlo", "dia a dia", "puesto",
                                    "en mi trabajo", "mi trabajo", "trabajo diario", "mi empresa",
                                    "proyectos", "carrera profesional"], []),
    "Valoración general": (10, ["curso", "formacion", "recomiendo", "recomendable", "recomendaria"], []),
}

POSITIVAS = ["estupendo", "estupenda", "excelente", "excelentes", "genial", "muy bien", "muy bueno",
             "muy buena", "bueno", "buena", "buen", "buenos", "buenas", "bien", "ameno", "amena", "claro", "clara",
             "claridad", "util", "utiles", "interesante*", "recomendable", "lo recomiendo", "recomiendo",
             "perfecto", "perfecta", "encantado", "encantada", "me ha gustado", "me gusto", "magnifico*",
             "fantastico*", "satisfecho", "satisfecha", "dinamico", "dinamica", "mucha experiencia",
             "he aprendido", "aprendido mucho", "completo", "completa", "adecuado*", "adecuada*",
             "profesional", "cercano", "cercana", "facil", "enriquecedor*", "motivador*", "domina", "dominio",
             "gracias", "de 10", "brillante", "bien organizado", "bien estructurado", "aprovechable",
             "actualizado*", "comodo", "comoda", "funciono", "funciona bien", "resolvia", "respondia"]
NEGATIVAS = ["mal", "malo", "mala", "escaso", "escasa", "insuficiente*", "corto", "corta", "poco tiempo",
             "falta", "faltan", "faltado", "falto", "faltaron", "dificil", "costado", "complicado", "complicada",
             "aburrido", "aburrida", "lento", "lenta", "demasiado rapido", "muy rapido", "deprisa", "denso",
             "densa", "pesado", "pesada", "problema*", "fallo", "fallos", "fallaba*", "desorganiz*",
             "no funciona*", "mejorar", "mejorable", "deberia*", "habria que", "echo en falta", "eche en falta",
             "demasiado", "demasiada", "confuso", "confusa", "desactualizado*", "incomodo", "incomoda", "frio",
             "calor", "ruido", "repetitivo", "teorico en exceso", "se corta*", "cortes", "caida*", "no se oia",
             "no se veia", "retraso*", "cambios de fecha", "no me ha servido", "no aporta", "superficial",
             "prisas", "agobi*", "acelerado"]
SUGERENCIA = ["seria mejor", "habria sido mejor", "hubiera sido mejor", "seria conveniente", "seria bueno",
              "seria interesante", "me hubiera gustado", "me habria gustado", "convendria", "sugiero",
              "propongo", "mas tiempo", "mas practica", "mas practicas", "mas ejemplos", "mas casos",
              "mas horas", "mas dias", "ir mas despacio", "echo de menos", "eche de menos", "ampliar"]
# Expresiones positivas que contienen palabras negativas (se anulan mutuamente si no se tratan)
NEUTRALIZAN = ["por lo demas bien", "por lo demas todo bien"]
NEGADORES = {"no", "nunca", "ni", "tampoco", "sin", "nada", "poco"}

# Acción recomendada por elemento / apartado
ACCIONES = {
    "Formador / tutor": "Reforzar la coordinación pedagógica con el equipo docente: compartir los resultados, "
                        "acordar técnicas de dinamización y realizar observación de aula en la próxima edición.",
    "Duración del curso": "Revisar la carga lectiva frente a los objetivos: ampliar horas o redistribuir el "
                          "temario, priorizando los contenidos clave y moviendo los complementarios a material de consulta.",
    "Horario": "Consultar la disponibilidad del grupo antes de programar y ofrecer franjas alternativas "
               "(dentro de la jornada o sesiones más cortas y frecuentes).",
    "Ritmo de impartición": "Realizar un diagnóstico de nivel inicial y adaptar el ritmo: incluir sesiones de "
                            "repaso, pausas de consolidación y material previo para perfiles noveles.",
    "Contenidos": "Actualizar el programa a partir de un análisis de necesidades previo y ajustar el nivel "
                  "de los contenidos al perfil real de los participantes.",
    "Enfoque práctico": "Aumentar el peso práctico: incorporar casos reales del sector, ejercicios aplicados "
                        "y talleres en al menos el 40 % de las horas.",
    "Materiales didácticos": "Revisar y actualizar la documentación; entregar el material con antelación e "
                             "incluir guías de consulta rápida y plantillas reutilizables.",
    "Organización": "Mejorar la planificación y la comunicación previa: confirmar fechas, horarios y logística "
                    "con antelación y enviar una guía de bienvenida al grupo.",
    "Instalaciones y medios técnicos": "Verificar aula y equipos antes de cada sesión (proyector, conexión, "
                                       "climatización) mediante una lista de comprobación del centro.",
    "Plataforma / formación online": "Probar la plataforma antes del inicio, ofrecer una sesión de acogida "
                                     "técnica y reforzar los canales de soporte y tutoría.",
    "Evaluación y acreditación": "Incorporar pruebas de evaluación y autoevaluación a lo largo del curso e "
                                 "informar desde el inicio del tipo de certificado que se obtiene.",
    "Aplicabilidad al puesto": "Vincular los contenidos al puesto de trabajo con ejemplos del día a día y un "
                               "plan de transferencia (acciones concretas a aplicar tras el curso).",
    "Valoración general": "Revisar el diseño global de la acción con el proveedor y realizar un seguimiento "
                          "específico de los aspectos peor valorados en la siguiente edición.",
}
ACCIONES_APARTADO = {
    1: ACCIONES["Organización"],
    2: ACCIONES["Contenidos"],
    3: ACCIONES["Duración del curso"],
    4: ACCIONES["Formador / tutor"],
    5: ACCIONES["Materiales didácticos"],
    6: ACCIONES["Instalaciones y medios técnicos"],
    7: ACCIONES["Plataforma / formación online"],
    8: ACCIONES["Evaluación y acreditación"],
    9: ACCIONES["Aplicabilidad al puesto"],
    10: ACCIONES["Valoración general"],
}
ELEMENTO_DE_APARTADO = {
    1: "Organización", 2: "Contenidos", 3: "Duración del curso", 4: "Formador / tutor",
    5: "Materiales didácticos", 6: "Instalaciones y medios técnicos", 7: "Plataforma / formación online",
    8: "Evaluación y acreditación", 9: "Aplicabilidad al puesto", 10: "Valoración general",
}

_SEPARADORES = re.compile(r"[.;:!?\n]+|,|\s+pero\s+|\s+aunque\s+|\s+sin embargo\s+|\s+no obstante\s+"
                          r"|\s+y\s+(?=(?:el|la|los|las|me|nos|se)\s)",
                          re.IGNORECASE)
COMENTARIOS_VACIOS = {"", "-", "--", "ninguno", "ninguna", "nada", "no", "sin comentarios", "n/a", "na",
                      "ninguna sugerencia", "nada que añadir", "nada que anadir", "todo bien", "."}


def _patron(termino: str) -> str:
    if termino.endswith("*"):
        return rf"\b{re.escape(termino[:-1])}\w*"
    return rf"\b{re.escape(termino)}\b"


def _buscar(texto: str, termino: str):
    return re.search(_patron(termino), texto)


def _valor_fragmento(frag: str) -> int:
    t = frag
    for n in NEUTRALIZAN:
        t = t.replace(n, " ")
    puntuacion = 0
    usados = []  # evita contar "bien" dentro de "muy bien"
    for p in sorted(POSITIVAS, key=len, reverse=True):
        m = _buscar(t, p)
        if m and not any(a <= m.start() < b for a, b in usados):
            usados.append(m.span())
            previas = t[:m.start()].split()[-4:]
            puntuacion += -1 if any(w in NEGADORES for w in previas) else 1
    for n in sorted(NEGATIVAS, key=len, reverse=True):
        m = _buscar(t, n)
        if m and not any(a <= m.start() < b for a, b in usados):
            usados.append(m.span())
            puntuacion -= 1
    for s in SUGERENCIA:
        if _buscar(t, s):
            puntuacion -= 1
    return puntuacion


def _elementos_fragmento(frag: str) -> tuple[list[str], bool]:
    """Devuelve (elementos, es_solo_general)."""
    fuertes = [n for n, (_, claves, _) in ELEMENTOS.items()
               if n != "Valoración general" and any(_buscar(frag, c) for c in claves)]
    if fuertes:
        return fuertes, False
    debiles = [n for n, (_, _, claves) in ELEMENTOS.items() if any(_buscar(frag, c) for c in claves)]
    if debiles:
        return debiles, False
    if any(_buscar(frag, c) for c in ELEMENTOS["Valoración general"][1]):
        return ["Valoración general"], True
    return [], False


def es_comentario_valido(texto: str) -> bool:
    return normalizar(texto).strip(" .") not in COMENTARIOS_VACIOS and len(texto.strip()) > 3


def analizar_comentarios(comentarios: list[str]) -> dict:
    """
    comentarios: lista con el texto del ítem 11 de cada participante (uno por cuestionario).
    Devuelve {"filas": [...], "n_con_comentario": int, "menciones": {...}}
    """
    menciones = defaultdict(lambda: {"positivo": {}, "negativo": {}, "neutro": {}})
    n_validos = 0
    for idx, original in enumerate(comentarios):
        if not original or not es_comentario_valido(original):
            continue
        n_validos += 1
        fragmentos_orig = [f.strip() for f in _SEPARADORES.split(original) if f and f.strip()]
        ultimo = []
        for frag_o in fragmentos_orig:
            frag = normalizar(frag_o)
            elems, solo_general = _elementos_fragmento(frag)
            val = _valor_fragmento(frag)
            if (not elems or solo_general) and val != 0 and ultimo and ultimo != ["Valoración general"]:
                elems = ultimo  # "...se nota que tiene mucha experiencia" hereda "Formador"
            elif not elems and val != 0:
                elems = ["Valoración general"]  # "Todo perfecto, gracias"
            if not elems:
                continue
            ultimo = elems
            etiqueta = "positivo" if val > 0 else "negativo" if val < 0 else "neutro"
            for e in elems:
                # Un participante cuenta una sola vez por elemento y valor
                menciones[e][etiqueta].setdefault(idx, []).append(frag_o)

    filas = []
    for elemento, por_valor in menciones.items():
        for valor in ("positivo", "negativo", "neutro"):
            participantes = por_valor[valor]
            if not participantes:
                continue
            # Preferimos comentarios con fragmentos más ricos para ilustrar
            orden = sorted(participantes.items(), key=lambda kv: -len(" ".join(kv[1])))
            ejemplos = [comentarios[i] for i, _ in orden[:2]]
            filas.append({
                "elemento": elemento,
                "apartado": ELEMENTOS[elemento][0],
                "valor": valor.capitalize(),
                "frecuencia": len(participantes),
                "comentarios": ejemplos,
                "ids": list(participantes.keys()),
            })
    filas.sort(key=lambda f: (-f["frecuencia"], f["elemento"]))
    return {"filas": filas, "n_con_comentario": n_validos}
