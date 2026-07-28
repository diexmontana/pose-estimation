"""Borra todo lo indexado y conserva la taxonomia.

Vacia imagenes, ubicaciones, poses, medidas, vectores, etiquetas por imagen,
colecciones, modelos, carpetas y raices. NO toca los archivos del disco ni la
taxonomia (categoria / opcion), para poder empezar de cero tras reorganizar
las carpetas sin perder la estructura de etiquetado.

Uso:
  python -m backend.db.borrar_indexado            # muestra que se borraria
  python -m backend.db.borrar_indexado --si        # lo ejecuta
"""

import argparse

from sqlalchemy import delete, func, select

from backend.db.models import (
    AliasModelo, AnalisisPose, Carpeta, CarpetaOpcion, ColaRevision, Coleccion,
    Imagen, ImagenColeccion, ImagenModelo, ImagenOpcion, MedidasPose, Miniatura,
    Modelo, ModeloOpcion, Raiz, Ubicacion, VectorPose,
)
from backend.db.session import SessionLocal

# Orden de borrado: primero lo que referencia a otras tablas.
TABLAS = [
    ImagenOpcion, ImagenColeccion, ImagenModelo, ModeloOpcion, CarpetaOpcion,
    ColaRevision, VectorPose, MedidasPose, AnalisisPose, Miniatura, Ubicacion,
    AliasModelo, Coleccion, Modelo, Carpeta, Imagen, Raiz,
]


def _conteos(s):
    return {m.__tablename__: s.scalar(select(func.count()).select_from(m)) for m in TABLAS}


def borrar(aplicar: bool = False):
    with SessionLocal() as s:
        antes = _conteos(s)
        total = sum(antes.values())
        print("Se borraria (se conserva la taxonomia: categoria/opcion):")
        for t, n in antes.items():
            if n:
                print(f"  {t}: {n}")
        print(f"  TOTAL filas: {total}")

        if not aplicar:
            print("\n(vista previa; ejecuta con --si para borrar)")
            return

        for modelo in TABLAS:
            s.execute(delete(modelo))
        s.commit()
        print("\nIndexado borrado. La taxonomia se conserva.")


def main():
    p = argparse.ArgumentParser(description="Borra lo indexado, conserva la taxonomia")
    p.add_argument("--si", action="store_true", help="Confirmar y borrar")
    args = p.parse_args()
    borrar(aplicar=args.si)


if __name__ == "__main__":
    main()
