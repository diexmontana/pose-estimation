"""Fase 7: busqueda de imagenes de pose parecida.

Dada una imagen, calcula la distancia enmascarada (solo articulaciones
fiables en ambas, normalizada) a las demas, considerando tambien el espejo,
y devuelve las mas cercanas. A 7000 vectores la busqueda exacta en memoria
es instantanea, sin indice.

Uso:
  python -m backend.pose.similares 22
  python -m backend.pose.similares 22 --n 10
"""

import argparse

from sqlalchemy import select

from backend.db.models import Ubicacion, VectorPose
from backend.db.session import SessionLocal
from backend.pose.vector import distancia_mejor


def _nombre(s, imagen_id):
    return s.scalar(select(Ubicacion.nombre_archivo).where(
        Ubicacion.imagen_id == imagen_id).limit(1))


def buscar(imagen_id: int, n: int = 8):
    with SessionLocal() as s:
        q = s.scalar(select(VectorPose).where(VectorPose.imagen_id == imagen_id))
        if q is None:
            raise SystemExit(f"La imagen {imagen_id} no tiene vector (¿torso fiable?)")

        resultados = []
        for vp in s.scalars(select(VectorPose).where(VectorPose.imagen_id != imagen_id)):
            d = distancia_mejor(q.vector, q.mascara, vp.vector,
                                vp.vector_reflejado, vp.mascara)
            if d is not None:
                resultados.append((d, vp.imagen_id))
        resultados.sort()

        print(f"Similares a la imagen {imagen_id} ({_nombre(s, imagen_id)}):")
        for d, iid in resultados[:n]:
            print(f"  dist {d:.3f}  img {iid:3}  {_nombre(s, iid)}")


def main():
    p = argparse.ArgumentParser(description="Busca imagenes de pose parecida")
    p.add_argument("imagen_id", type=int)
    p.add_argument("--n", type=int, default=8, help="Cuantas devolver")
    args = p.parse_args()
    buscar(args.imagen_id, args.n)


if __name__ == "__main__":
    main()
