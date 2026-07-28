"""Servicio del modo práctica (fase 10, parte de la interfaz).

Reúne el conjunto de imágenes de la sesión (según colección, modelo y filtros)
y define los presets del "modo clase" (réplica de Line of Action). El
temporizador y las herramientas sobre la imagen viven en el cliente.
"""

import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Imagen, ImagenColeccion, ImagenModelo, Miniatura, Ubicacion
from backend.services.galeria import imagenes_filtradas

# Presets del modo clase: lista de fases (nº de poses, segundos por pose).
# El de 30 min es el de Line of Action; los largos son progresivos (los
# descansos quedan pendientes).
CLASES = {
    "30 min": [(10, 30), (5, 60), (2, 300), (1, 600)],
    "1 h": [(10, 30), (8, 60), (6, 120), (3, 300), (2, 600)],
    "1 h 30": [(10, 30), (10, 60), (10, 120), (5, 300), (3, 600)],
    "2 h": [(12, 30), (12, 60), (10, 120), (8, 300), (5, 600)],
    "3 h": [(15, 30), (15, 60), (15, 120), (12, 300), (8, 600)],
}

# Opciones de intervalo estándar (etiqueta, segundos).
INTERVALOS = [("30 s", 30), ("1 min", 60), ("2 min", 120), ("5 min", 300), ("10 min", 600)]


def clases_descritas() -> list[dict]:
    salida = []
    for nombre, fases in CLASES.items():
        total_seg = sum(p * s for p, s in fases)
        detalle = [f"{p} poses, {_fmt(s)}" for p, s in fases]
        salida.append({"nombre": nombre, "fases": detalle, "total_min": total_seg // 60})
    return salida


def _fmt(seg: int) -> str:
    if seg < 60:
        return f"{seg} s"
    m = seg // 60
    return f"{m} min"


def pool(s: Session, coleccion_ids=None, modelo_ids=None, opcion_ids=None,
         orden="aleatorio") -> list[int]:
    """IDs de imágenes de la sesión. El origen es la UNIÓN de las colecciones y
    los modelos elegidos; luego se acota (intersección) con los filtros de
    etiquetas. Sin origen ni filtros -> todas."""
    coleccion_ids = coleccion_ids or []
    modelo_ids = modelo_ids or []

    origen = None
    if coleccion_ids or modelo_ids:
        origen = set()
        if coleccion_ids:
            origen |= set(s.scalars(select(ImagenColeccion.imagen_id)
                                    .where(ImagenColeccion.coleccion_id.in_(coleccion_ids))))
        if modelo_ids:
            origen |= set(s.scalars(select(ImagenModelo.imagen_id)
                                    .where(ImagenModelo.modelo_id.in_(modelo_ids))))
    filtro = imagenes_filtradas(s, opcion_ids or [])

    if origen is not None and filtro is not None:
        ids = list(origen & filtro)
    elif origen is not None:
        ids = list(origen)
    elif filtro is not None:
        ids = list(filtro)
    else:
        ids = list(s.scalars(select(Imagen.id)))

    excl = set(s.scalars(select(Imagen.id).where(Imagen.excluida.is_(True))))
    if excl:
        ids = [i for i in ids if i not in excl]

    if orden == "aleatorio":
        random.shuffle(ids)
    else:
        ids.sort()
    return ids


def muestra(s: Session, ids: list[int], n: int = 24) -> dict:
    """Total y una muestra (con miniatura) para la vista previa."""
    sub = ids[:n]
    minis = dict(s.execute(select(Miniatura.imagen_id, Miniatura.ruta)
                           .where(Miniatura.imagen_id.in_(sub))).all()) if sub else {}
    fotos = [{"id": i, "miniatura": minis.get(i)} for i in sub]
    return {"total": len(ids), "fotos": fotos, "mas": max(0, len(ids) - n)}


def plan_clase(nombre: str) -> dict:
    fases = CLASES.get(nombre)
    if not fases:
        return {}
    return {"tipo": "clase", "fases": [{"poses": p, "segundos": s} for p, s in fases]}


def plan_intervalo(segundos: int, numero: int | None) -> dict:
    return {"tipo": "intervalo", "segundos": max(1, segundos), "numero": numero}
