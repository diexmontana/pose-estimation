"""Exportar una colección completa a una carpeta destino (sección 11).

Copia los archivos originales (nunca miniaturas) con un prefijo numérico que
conserva el orden de la colección. Si alguna unidad está desconectada, exporta
lo disponible y reporta lo que faltó, sin fallar el proceso entero.
"""

import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import ImagenColeccion


def exportar_coleccion(s: Session, coleccion_id: int, destino: str) -> dict:
    from backend.tagging import overlay as ov

    ids = list(s.scalars(
        select(ImagenColeccion.imagen_id)
        .where(ImagenColeccion.coleccion_id == coleccion_id)
        .order_by(ImagenColeccion.orden)))
    dest = Path(destino)
    dest.mkdir(parents=True, exist_ok=True)

    copiadas = faltantes = 0
    for n, iid in enumerate(ids, 1):
        ruta, _ = ov.ruta_imagen(s, iid)
        if ruta and ruta.exists():
            try:
                shutil.copy2(str(ruta), str(dest / f"{n:03d}_{ruta.name}"))
                copiadas += 1
            except Exception:
                faltantes += 1
        else:
            faltantes += 1

    return {"copiadas": copiadas, "faltantes": faltantes,
            "total": len(ids), "destino": str(dest)}
