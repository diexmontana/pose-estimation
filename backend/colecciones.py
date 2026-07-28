"""Colecciones estilo Pinterest (fase 6, trozo 3).

Colecciones estaticas: el usuario guarda imagenes en una o varias
colecciones, con creacion sobre la marcha. Las dinamicas (consulta de
filtros que se recalcula sola) se implementan despues de las estaticas y su
formato de consulta es una decision pendiente (seccion 13).

Uso:
  python -m backend.colecciones crear "Con armas" --descripcion "refs con espadas"
  python -m backend.colecciones agregar "Con armas" 1 22 35     # crea si no existe
  python -m backend.colecciones quitar "Con armas" 22
  python -m backend.colecciones listar
  python -m backend.colecciones ver "Con armas"
"""

import argparse

from sqlalchemy import delete, func, select

from backend.db.models import Coleccion, Imagen, ImagenColeccion, Ubicacion
from backend.db.session import SessionLocal


def _coleccion(s, nombre, crear=False):
    col = s.scalar(select(Coleccion).where(Coleccion.nombre == nombre))
    if col is None and crear:
        col = Coleccion(nombre=nombre, tipo="estatica")
        s.add(col)
        s.flush()
        print(f"Coleccion creada: {nombre}")
    return col


def crear(nombre, descripcion=None):
    with SessionLocal() as s:
        if _coleccion(s, nombre):
            print(f"La coleccion '{nombre}' ya existe")
            return
        s.add(Coleccion(nombre=nombre, descripcion=descripcion, tipo="estatica"))
        s.commit()
        print(f"Coleccion creada: {nombre}")


def agregar(nombre, imagen_ids):
    with SessionLocal() as s:
        col = _coleccion(s, nombre, crear=True)  # sobre la marcha
        # siguiente orden
        maxo = s.scalar(select(func.max(ImagenColeccion.orden)).where(
            ImagenColeccion.coleccion_id == col.id)) or 0
        n = 0
        for iid in imagen_ids:
            if not s.get(Imagen, iid):
                print(f"  imagen {iid} no existe, se salta")
                continue
            ya = s.get(ImagenColeccion, {"imagen_id": iid, "coleccion_id": col.id})
            if ya:
                continue
            maxo += 1
            s.add(ImagenColeccion(imagen_id=iid, coleccion_id=col.id, orden=maxo))
            n += 1
        s.commit()
        print(f"Agregadas {n} imagenes a '{nombre}'")


def quitar(nombre, imagen_id):
    with SessionLocal() as s:
        col = _coleccion(s, nombre)
        if not col:
            raise SystemExit(f"No existe la coleccion '{nombre}'")
        n = s.execute(delete(ImagenColeccion).where(
            ImagenColeccion.coleccion_id == col.id,
            ImagenColeccion.imagen_id == imagen_id)).rowcount
        s.commit()
        print(f"Quitadas {n} de '{nombre}'")


def listar():
    with SessionLocal() as s:
        filas = s.execute(
            select(Coleccion.nombre, Coleccion.tipo, func.count(ImagenColeccion.imagen_id))
            .outerjoin(ImagenColeccion, ImagenColeccion.coleccion_id == Coleccion.id)
            .group_by(Coleccion.id, Coleccion.nombre, Coleccion.tipo)
            .order_by(Coleccion.nombre)
        ).all()
        if not filas:
            print("No hay colecciones")
        for nombre, tipo, n in filas:
            print(f"  {n:4}  {nombre}  ({tipo})")


def ver(nombre):
    with SessionLocal() as s:
        col = _coleccion(s, nombre)
        if not col:
            raise SystemExit(f"No existe la coleccion '{nombre}'")
        print(f"Coleccion '{nombre}':")
        filas = s.execute(
            select(ImagenColeccion.orden, ImagenColeccion.imagen_id, Ubicacion.nombre_archivo)
            .outerjoin(Ubicacion, Ubicacion.imagen_id == ImagenColeccion.imagen_id)
            .where(ImagenColeccion.coleccion_id == col.id)
            .order_by(ImagenColeccion.orden)
        ).all()
        vistos = set()
        for orden, iid, nombre_arch in filas:
            if iid in vistos:
                continue
            vistos.add(iid)
            print(f"  {orden:3}. img {iid} {nombre_arch}")


def main():
    p = argparse.ArgumentParser(description="Colecciones estaticas")
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("crear"); q.add_argument("nombre"); q.add_argument("--descripcion")
    q = sub.add_parser("agregar"); q.add_argument("nombre"); q.add_argument("imagen_ids", nargs="+", type=int)
    q = sub.add_parser("quitar"); q.add_argument("nombre"); q.add_argument("imagen_id", type=int)
    sub.add_parser("listar")
    q = sub.add_parser("ver"); q.add_argument("nombre")
    args = p.parse_args()

    if args.cmd == "crear": crear(args.nombre, args.descripcion)
    elif args.cmd == "agregar": agregar(args.nombre, args.imagen_ids)
    elif args.cmd == "quitar": quitar(args.nombre, args.imagen_id)
    elif args.cmd == "listar": listar()
    elif args.cmd == "ver": ver(args.nombre)


if __name__ == "__main__":
    main()
