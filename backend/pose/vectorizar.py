"""Fase 7: construye y guarda el vector de similitud de cada imagen.

Lee los angulos de medidas_pose y escribe vector_pose. Regenerable: con
--revectorizar recalcula todo. Solo procesa imagenes con torso fiable (sin
angulos no hay vector util).

Uso:
  python -m backend.pose.vectorizar
  python -m backend.pose.vectorizar --revectorizar
"""

import argparse

from sqlalchemy import delete, select

from backend.db.models import MedidasPose, VectorPose
from backend.db.session import SessionLocal
from backend.pose.vector import VERSION_VECTOR, construir

LOTE_COMMIT = 100


def vectorizar(revectorizar: bool = False) -> None:
    creados = sin_angulos = 0
    with SessionLocal() as s:
        if revectorizar:
            s.execute(delete(VectorPose))
            s.commit()
            ya = set()
        else:
            ya = set(s.scalars(select(VectorPose.imagen_id)))

        medidas = list(s.scalars(select(MedidasPose).order_by(MedidasPose.imagen_id)))
        total = len(medidas)
        print(f"Medidas a vectorizar: {total}")

        pendientes = 0
        for i, med in enumerate(medidas, 1):
            if med.imagen_id in ya:
                continue
            if not med.torso_fiable or not med.angulos:
                sin_angulos += 1
                continue
            vector, reflejado, mascara = construir(med.angulos)
            if sum(mascara) == 0:
                sin_angulos += 1
                continue
            s.add(VectorPose(imagen_id=med.imagen_id, vector=vector,
                             vector_reflejado=reflejado, mascara=mascara,
                             version=VERSION_VECTOR))
            creados += 1
            pendientes += 1
            if pendientes >= LOTE_COMMIT:
                s.commit()
                pendientes = 0
            if i % 20 == 0 or i == total:
                print(f"[{i}/{total}] vectorizadas")
        s.commit()

    print(f"\nHecho. Vectores creados: {creados} | sin angulos utiles: {sin_angulos}")


def main():
    p = argparse.ArgumentParser(description="Construye vectores de pose")
    p.add_argument("--revectorizar", action="store_true")
    args = p.parse_args()
    vectorizar(revectorizar=args.revectorizar)


if __name__ == "__main__":
    main()
