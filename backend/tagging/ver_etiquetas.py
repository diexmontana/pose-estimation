"""Muestra las etiquetas automaticas y la cola de revision (fase 5).

Uso:
  python -m backend.tagging.ver_etiquetas
  python -m backend.tagging.ver_etiquetas --id 22
  python -m backend.tagging.ver_etiquetas --cola          (solo la cola de revision)
  python -m backend.tagging.ver_etiquetas --resumen       (conteo por categoria/opcion)
"""

import argparse
from collections import Counter

from sqlalchemy import func, select

from backend.db.models import (
    Categoria, ColaRevision, Imagen, ImagenOpcion, Opcion, Ubicacion,
)
from backend.db.session import SessionLocal


def _nombre(s, imagen_id):
    return s.scalar(select(Ubicacion.nombre_archivo).where(Ubicacion.imagen_id == imagen_id).limit(1))


def _etiquetas_de(s, imagen_id):
    return s.execute(
        select(Categoria.codigo, Opcion.nombre, ImagenOpcion.confianza)
        .join(Categoria, Categoria.id == ImagenOpcion.categoria_id)
        .join(Opcion, Opcion.id == ImagenOpcion.opcion_id)
        .where(ImagenOpcion.imagen_id == imagen_id, ImagenOpcion.origen == "geometrico")
        .order_by(Categoria.orden)
    ).all()


def detalle(imagen_id):
    with SessionLocal() as s:
        print(f"Imagen {imagen_id} ({_nombre(s, imagen_id)})")
        for cat, opt, conf in _etiquetas_de(s, imagen_id):
            print(f"  {cat:22} = {opt:20} (conf {conf})")
        cola = s.execute(
            select(Categoria.codigo, ColaRevision.motivo)
            .outerjoin(Categoria, Categoria.id == ColaRevision.categoria_id)
            .where(ColaRevision.imagen_id == imagen_id)
        ).all()
        for cat, motivo in cola:
            print(f"  [revision] {cat or '(general)'}: {motivo}")


def cola():
    with SessionLocal() as s:
        total = s.scalar(select(func.count(ColaRevision.id)))
        print(f"En cola de revision: {total}\n")
        por_cat = Counter()
        filas = s.execute(
            select(ColaRevision.imagen_id, Categoria.codigo, ColaRevision.motivo)
            .outerjoin(Categoria, Categoria.id == ColaRevision.categoria_id)
            .order_by(ColaRevision.imagen_id)
        ).all()
        for imagen_id, cat, motivo in filas:
            por_cat[(cat or "(general)", motivo)] += 1
        for (cat, motivo), n in por_cat.most_common():
            print(f"  {n:3}  {cat:22} {motivo}")


def resumen():
    with SessionLocal() as s:
        total_img = s.scalar(select(func.count(func.distinct(ImagenOpcion.imagen_id))))
        total_et = s.scalar(select(func.count(ImagenOpcion.id)))
        print(f"Imagenes con etiquetas: {total_img} | etiquetas totales: {total_et}\n")
        filas = s.execute(
            select(Categoria.codigo, Opcion.nombre, func.count(ImagenOpcion.id))
            .join(Categoria, Categoria.id == ImagenOpcion.categoria_id)
            .join(Opcion, Opcion.id == ImagenOpcion.opcion_id)
            .group_by(Categoria.codigo, Categoria.orden, Opcion.nombre, Opcion.orden)
            .order_by(Categoria.orden, Opcion.orden)
        ).all()
        cat_actual = None
        for cat, opt, n in filas:
            if cat != cat_actual:
                print(f"\n{cat}:")
                cat_actual = cat
            print(f"  {n:3}  {opt}")


def lista():
    with SessionLocal() as s:
        ids = [r[0] for r in s.execute(
            select(ImagenOpcion.imagen_id).distinct().order_by(ImagenOpcion.imagen_id)
        ).all()]
        for imagen_id in ids:
            ets = _etiquetas_de(s, imagen_id)
            resumen_txt = " ".join(
                f"{opt}" for cat, opt, conf in ets
                if cat in ("encuadre", "postura", "orientacion_corporal", "escorzo", "dinamismo")
            )
            print(f"img {imagen_id:3} {resumen_txt}  ({_nombre(s, imagen_id)})")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--id", type=int)
    p.add_argument("--cola", action="store_true")
    p.add_argument("--resumen", action="store_true")
    args = p.parse_args()
    if args.id:
        detalle(args.id)
    elif args.cola:
        cola()
    elif args.resumen:
        resumen()
    else:
        lista()


if __name__ == "__main__":
    main()
