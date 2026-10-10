"""
App Streamlit · Informe de evaluación de acciones formativas
Carga un .zip con cuestionarios SEPE/FUNDAE en PDF y genera el informe en PDF.

Ejecutar en local:  streamlit run app.py
"""
from __future__ import annotations

import re
import pandas as pd
import streamlit as st

# ===========================================================================
#  LECTOR
# ===========================================================================
# Lectura de cuestionarios SEPE/FUNDAE (formularios PDF rellenables) desde un .zip.
#
# Cada cuestionario se lee a partir de los CAMPOS del formulario PDF (no del texto
# impreso), lo que hace la extracción exacta. Para los botones de opción se toma
# el valor del campo (/V) y, si no existe, el estado activo del widget (/AS).

import io
import logging
import unicodedata
import zipfile
from dataclasses import dataclass, field

from pypdf import PdfReader

logging.getLogger("pypdf").setLevel(logging.ERROR)

# --------------------------------------------------------------------------- #
#  Definición del cuestionario (apartado III)
# --------------------------------------------------------------------------- #
# Cada apartado principal: número, nombre, tipo y lista de (código, texto, campo PDF)
APARTADOS = [
    {"num": 1, "nombre": "Organización del curso", "tipo": "escala", "items": [
        ("1.1", "El curso ha estado bien organizado (información, fechas, horarios, material)", "ID_BUENA_ORGANIZACION"),
        ("1.2", "El número de alumnos del grupo ha sido adecuado", "ID_NUM_ALUMNOS_ADECUADO"),
    ]},
    {"num": 2, "nombre": "Contenidos y metodología de impartición", "tipo": "escala", "items": [
        ("2.1", "Los contenidos han respondido a mis necesidades formativas", "ID_CONTENIDOS_SEGUN_NECESIDADES"),
        ("2.2", "Combinación adecuada de teoría y aplicación práctica", "ID_CONTENIDOS_SEGUN_TEORIA_PRACTICA"),
    ]},
    {"num": 3, "nombre": "Duración y horario", "tipo": "escala", "items": [
        ("3.1", "La duración ha sido suficiente según objetivos y contenidos", "ID_DURACION_SUFICIENTE"),
        ("3.2", "El horario ha favorecido la asistencia", "ID_HORARIO_FAVORABLE"),
    ]},
    {"num": 4, "nombre": "Formadores y tutores", "tipo": "escala", "items": [
        ("4.1 F", "Formador: la forma de impartir ha facilitado el aprendizaje", "ID_FORMADOR_FACILITADOR"),
        ("4.2 F", "Formador: conoce los temas en profundidad", "ID_FORMADOR_CONOCE_TEMA"),
        ("4.1 T", "Tutor: la forma de tutorizar ha facilitado el aprendizaje", "ID_TUTOR_FACILITADOR"),
        ("4.2 T", "Tutor: conoce los temas en profundidad", "ID_TUTOR_CONOCE_TEMA"),
    ]},
    {"num": 5, "nombre": "Medios didácticos", "tipo": "escala", "items": [
        ("5.1", "Documentación y materiales comprensibles y adecuados", "ID_MEDIOS_COMPRENSIBLES"),
        ("5.2", "Los medios didácticos están actualizados", "ID_MEDIOS_ACTUALIZADOS"),
    ]},
    {"num": 6, "nombre": "Instalaciones y medios técnicos", "tipo": "escala", "items": [
        ("6.1", "Aula, taller o instalaciones apropiadas", "ID_INSTALACIONES_ADECUADAS"),
        ("6.2", "Medios técnicos adecuados", "ID_MEDIOS_TECNICOS_ADECUADOS"),
    ]},
    {"num": 7, "nombre": "Modalidad telemática o mixta", "tipo": "escala", "items": [
        ("7.1", "Guías tutoriales y materiales han facilitado realizar el curso", "ID_TELEFORMACION_GUIA"),
        ("7.2", "Medios de apoyo suficientes (tutorías, correo, videoconferencia...)", "ID_TELEFORMACION_MEDIOS"),
    ]},
    {"num": 8, "nombre": "Mecanismos para la evaluación del aprendizaje", "tipo": "sino", "items": [
        ("8.1", "Pruebas de evaluación y autoevaluación para conocer el nivel alcanzado", "ID_PRUEBAS_EVALUACION"),
        ("8.2", "El curso permite obtener una acreditación de mi cualificación", "ID_ACREDITACION"),
    ]},
    {"num": 9, "nombre": "Valoración general del curso", "tipo": "escala", "items": [
        ("9.1", "Puede contribuir a mi incorporación al mercado de trabajo", "ID_INCORPORACION_MERCADO"),
        ("9.2", "Nuevas habilidades/capacidades aplicables al puesto", "Habilidades_trabajar_en_formado"),
        ("9.3", "Ha mejorado mis posibilidades de cambiar de puesto", "ID_CONOCIMIENTOS_PUESTO_TRABAJO"),
        ("9.4", "He ampliado conocimientos para progresar en mi carrera", "ID_PROGRESAR_CARRERA"),
        ("9.5", "Ha favorecido mi desarrollo personal", "ID_DESARROLLO_PERSONAL"),
    ]},
    {"num": 10, "nombre": "Grado de satisfacción general con el curso", "tipo": "escala", "items": [
        ("10", "Grado de satisfacción general con el curso", "ID_GRADO_SATISFACCION"),
    ], "sino_items": [
        ("10.1", "¿Recomendaría este curso?", "ID_RECOMENDARIA_CURSO"),
    ]},
]

CAMPOS_FICHA = {
    "expediente": "D_NUM_EXPEDIENTE",
    "acceso": "D_EXPEDIENTE_DM",
    "cif": "D_CIF",
    "num_aaff": "D_COD_AAFF",
    "num_grupo": "D_COD_GRUPO",
    "denominacion": "D_ACCION_FORMATIVA",
    "modalidad": "ID_MODALIDAD",
    "fecha": "F_CUMPLIMENTACION",
}
CAMPO_COMENTARIO = "D_OBSERVACION"


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes ni espacios sobrantes."""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.lower().split())


ESCALA = {
    "completamente en desacuerdo": 1,
    "en desacuerdo": 2,
    "de acuerdo": 3,
    "completamente de acuerdo": 4,
    "1": 1, "2": 2, "3": 3, "4": 4,
}
SINO = {"si": "Sí", "s": "Sí", "1": "Sí", "yes": "Sí", "no": "No", "n": "No", "2": "No"}
SIN_RESPUESTA = {"", "off", "no contesta", "nc", "9", "none"}


def _limpiar_valor(v) -> str | None:
    if v is None:
        return None
    s = str(v)
    if s.startswith("/"):
        s = s[1:]
    s = s.strip()
    return s or None


@dataclass
class Cuestionario:
    archivo: str
    ficha: dict = field(default_factory=dict)
    escala: dict = field(default_factory=dict)   # campo -> 1..4 | None
    sino: dict = field(default_factory=dict)     # campo -> "Sí" | "No" | None
    comentario: str = ""

    @property
    def clave_curso(self) -> tuple:
        return (
            self.ficha.get("denominacion") or "(sin denominación)",
            self.ficha.get("num_aaff") or "",
            self.ficha.get("num_grupo") or "",
        )


def _leer_campos(reader: PdfReader) -> dict[str, str | None]:
    """Devuelve {nombre_campo: valor} combinando /V y el estado /AS de los widgets."""
    valores: dict[str, str | None] = {}
    try:
        for nombre, f in (reader.get_fields() or {}).items():
            valores[nombre] = _limpiar_valor(f.get("/V"))
    except Exception:
        pass
    # Respaldo: estado visual de los botones de opción
    for page in reader.pages:
        for annot in page.get("/Annots") or []:
            try:
                a = annot.get_object()
                if a.get("/Subtype") != "/Widget":
                    continue
                nombre = a.get("/T")
                if nombre is None and a.get("/Parent") is not None:
                    nombre = a["/Parent"].get_object().get("/T")
                if nombre is None:
                    continue
                estado = _limpiar_valor(a.get("/AS"))
                if estado and normalizar(estado) != "off" and not valores.get(str(nombre)):
                    valores[str(nombre)] = estado
            except Exception:
                continue
    return valores


def _buscar_campo(valores: dict, campo: str):
    """Búsqueda tolerante a mayúsculas/minúsculas del nombre del campo."""
    if campo in valores:
        return valores[campo]
    objetivo = campo.lower()
    for k, v in valores.items():
        if k.lower() == objetivo:
            return v
    return None


def leer_cuestionario(datos: bytes, archivo: str) -> Cuestionario:
    reader = PdfReader(io.BytesIO(datos))
    valores = _leer_campos(reader)
    if not any(k.startswith(("ID_", "D_")) for k in valores):
        raise ValueError("el PDF no contiene los campos del formulario SEPE (¿está escaneado o aplanado?)")

    q = Cuestionario(archivo=archivo)
    for clave, campo in CAMPOS_FICHA.items():
        v = _buscar_campo(valores, campo)
        q.ficha[clave] = v.strip() if isinstance(v, str) else v
    if q.ficha.get("modalidad"):
        m = normalizar(q.ficha["modalidad"])
        q.ficha["modalidad"] = {"presencial": "Presencial", "teleformacion": "Teleformación",
                                "mixta": "Mixta"}.get(m, q.ficha["modalidad"])

    for ap in APARTADOS:
        destino = q.sino if ap["tipo"] == "sino" else q.escala
        for _, _, campo in ap["items"]:
            destino[campo] = _convertir(_buscar_campo(valores, campo), ap["tipo"])
        for _, _, campo in ap.get("sino_items", []):
            q.sino[campo] = _convertir(_buscar_campo(valores, campo), "sino")

    q.comentario = " ".join((_buscar_campo(valores, CAMPO_COMENTARIO) or "").split())
    return q


def _convertir(valor, tipo):
    if valor is None:
        return None
    n = normalizar(valor)
    if n in SIN_RESPUESTA:
        return None
    if tipo == "sino":
        return SINO.get(n)
    return ESCALA.get(n)


def leer_zip(datos_zip: bytes, max_archivos: int = 2000):
    """Devuelve (cuestionarios, incidencias) a partir de un .zip con PDFs (admite subcarpetas)."""
    cuestionarios: list[Cuestionario] = []
    incidencias: list[tuple[str, str]] = []
    with zipfile.ZipFile(io.BytesIO(datos_zip)) as zf:
        nombres = [
            n for n in zf.namelist()
            if not n.endswith("/") and "__MACOSX" not in n and not n.split("/")[-1].startswith(".")
        ]
        for nombre in nombres[:max_archivos]:
            corto = nombre.split("/")[-1]
            if not corto.lower().endswith(".pdf"):
                incidencias.append((corto, "no es un PDF; se ignora"))
                continue
            try:
                info = zf.getinfo(nombre)
                if info.file_size > 50 * 1024 * 1024:
                    raise ValueError("archivo demasiado grande")
                cuestionarios.append(leer_cuestionario(zf.read(nombre), corto))
            except Exception as e:  # noqa: BLE001
                incidencias.append((corto, f"no se pudo leer: {e}"))
    return cuestionarios, incidencias

# ===========================================================================
#  CUANTITATIVO
# ===========================================================================
# Análisis cuantitativo de los ítems 1 a 10 del apartado III.

import math
from collections import Counter


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

# ===========================================================================
#  COMENTARIOS
# ===========================================================================
# Análisis de los comentarios abiertos (ítem 11).
#
# Motor por reglas (funciona sin conexión): divide cada comentario en fragmentos,
# detecta el elemento del curso al que se refiere cada fragmento mediante un
# diccionario temático y estima su valor (positivo / negativo / neutro) con un
# léxico de opinión en español que tiene en cuenta negaciones y sugerencias de
# mejora ("sería mejor...", "más tiempo...", "faltó...").

import re
from collections import defaultdict


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

# ===========================================================================
#  CONCLUSIONES
# ===========================================================================
# Conclusiones y recomendaciones (apartado 4 del informe).


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

# ===========================================================================
#  IA
# ===========================================================================
# Análisis opcional con IA (Claude, API de Anthropic).
#
# Mejora la detección de elementos, el resumen ejecutivo y las recomendaciones.
# Los comentarios se envían numerados (C1, C2...) y el modelo responde con esos
# identificadores: así las citas del informe son SIEMPRE textuales y la
# frecuencia se calcula contando participantes reales.
# Si la llamada falla, la app usa automáticamente el motor por reglas.

import json
import re


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

# ===========================================================================
#  INFORME_PDF
# ===========================================================================
# Generación del informe en PDF (ReportLab + Matplotlib).

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

# ===========================================================================
#  __INIT__
# ===========================================================================
# Motor de procesamiento de cuestionarios de evaluación de acciones formativas.

from collections import Counter




def agrupar_por_curso(cuestionarios: list[Cuestionario]) -> dict[tuple, list[Cuestionario]]:
    grupos: dict[tuple, list[Cuestionario]] = {}
    for q in cuestionarios:
        grupos.setdefault(q.clave_curso, []).append(q)
    return dict(sorted(grupos.items(), key=lambda kv: -len(kv[1])))


def _mas_comun(valores):
    valores = [v for v in valores if v]
    return Counter(valores).most_common(1)[0][0] if valores else None


def construir_ficha(cuestionarios: list[Cuestionario]) -> dict:
    f = [q.ficha for q in cuestionarios]
    modalidades = sorted({x["modalidad"] for x in f if x.get("modalidad")})
    return {
        "nombre": _mas_comun(x.get("denominacion") for x in f) or "Curso sin denominación",
        "expediente": _mas_comun(x.get("expediente") for x in f),
        "num_aaff": _mas_comun(x.get("num_aaff") for x in f),
        "num_grupo": _mas_comun(x.get("num_grupo") for x in f),
        "modalidad": " / ".join(modalidades) if modalidades else None,
        "n_cuestionarios": len(cuestionarios),
    }


def detectar_teleformacion(cuestionarios: list[Cuestionario]) -> bool:
    """True si la modalidad mayoritaria es Teleformación o Mixta."""
    m = _mas_comun(q.ficha.get("modalidad") for q in cuestionarios)
    return m in ("Teleformación", "Mixta")


def procesar(cuestionarios: list[Cuestionario], incluir_item7: bool, api_key: str | None = None,
             modelo: str | None = None) -> dict:
    """Ejecuta todo el análisis. Devuelve un dict con ficha, cuantitativo, comentarios, conclusiones y método."""
    ficha = construir_ficha(cuestionarios)
    cuant = analizar(cuestionarios, incluir_item7)
    textos = [q.comentario for q in cuestionarios]
    coment = analizar_comentarios(textos)
    concl = elaborar(ficha, cuant, coment)
    metodo, aviso = "reglas", None
    if api_key:
        try:
            coment_ia, concl_ia = analizar_con_ia(api_key, ficha, cuant, textos, modelo or MODELO_POR_DEFECTO)
            if coment_ia["filas"] or not coment["filas"]:
                coment = coment_ia
            for k, v in concl_ia.items():
                if v:
                    concl[k] = v
            metodo = "ia"
        except Exception as e:  # noqa: BLE001
            aviso = f"No se pudo usar la IA ({e}). Se ha aplicado el análisis automático por reglas."
    return {"ficha": ficha, "cuant": cuant, "coment": coment, "concl": concl, "metodo": metodo, "aviso": aviso}

# ===========================================================================
#  INTERFAZ STREAMLIT
# ===========================================================================
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
