"""Motor de procesamiento de cuestionarios de evaluación de acciones formativas."""
from __future__ import annotations

from collections import Counter

from .comentarios import analizar_comentarios
from .conclusiones import elaborar
from .cuantitativo import analizar
from .informe_pdf import generar_pdf
from .lector import Cuestionario, leer_zip

__all__ = ["leer_zip", "agrupar_por_curso", "construir_ficha", "procesar", "generar_pdf", "detectar_teleformacion"]


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
            from .ia import MODELO_POR_DEFECTO, analizar_con_ia
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
