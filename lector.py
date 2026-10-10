"""
Lectura de cuestionarios SEPE/FUNDAE (formularios PDF rellenables) desde un .zip.

Cada cuestionario se lee a partir de los CAMPOS del formulario PDF (no del texto
impreso), lo que hace la extracción exacta. Para los botones de opción se toma
el valor del campo (/V) y, si no existe, el estado activo del widget (/AS).
"""
from __future__ import annotations

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


def _buscar(valores: dict, campo: str):
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
        v = _buscar(valores, campo)
        q.ficha[clave] = v.strip() if isinstance(v, str) else v
    if q.ficha.get("modalidad"):
        m = normalizar(q.ficha["modalidad"])
        q.ficha["modalidad"] = {"presencial": "Presencial", "teleformacion": "Teleformación",
                                "mixta": "Mixta"}.get(m, q.ficha["modalidad"])

    for ap in APARTADOS:
        destino = q.sino if ap["tipo"] == "sino" else q.escala
        for _, _, campo in ap["items"]:
            destino[campo] = _convertir(_buscar(valores, campo), ap["tipo"])
        for _, _, campo in ap.get("sino_items", []):
            q.sino[campo] = _convertir(_buscar(valores, campo), "sino")

    q.comentario = " ".join((_buscar(valores, CAMPO_COMENTARIO) or "").split())
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
