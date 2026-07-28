"""Fase 4: deriva medidas_pose a partir de analisis_pose.

No pasa MediaPipe: lee lo crudo ya guardado y calcula. Regenerable: con
--rederivar recalcula todo (por ejemplo tras mejorar una regla o subir la
version). Procesa por lotes con commit frecuente.

Uso:
  python -m backend.tagging.derivar
  python -m backend.tagging.derivar --rederivar
"""

import argparse

from sqlalchemy import select

from backend.db.models import AnalisisPose, Imagen, MedidasPose
from backend.db.session import SessionLocal
from backend.tagging.medidas import calcular_medidas

LOTE_COMMIT = 50


def derivar(rederivar: bool = False) -> None:
    procesadas = primeros_planos = sin_pose = 0
    pendientes = 0

    with SessionLocal() as sesion:
        consulta = select(AnalisisPose).join(Imagen, Imagen.id == AnalisisPose.imagen_id)
        if not rederivar:
            # solo las que aun no tienen medidas
            ya = set(sesion.scalars(select(MedidasPose.imagen_id)))
        else:
            sesion.query(MedidasPose).delete()
            sesion.commit()
            ya = set()

        analisis = list(sesion.scalars(consulta.order_by(AnalisisPose.imagen_id)))
        total = len(analisis)
        print(f"Analisis a derivar: {total}")

        for i, a in enumerate(analisis, 1):
            if a.imagen_id in ya:
                continue

            if not a.pose_detectada or not a.landmarks_2d:
                # sin deteccion: no hay geometria posible
                med = MedidasPose(
                    imagen_id=a.imagen_id,
                    version_reglas="v1",
                    torso_fiable=False,
                    es_primer_plano=False,
                )
                sin_pose += 1
            else:
                imagen = sesion.get(Imagen, a.imagen_id)
                ancho = imagen.ancho or 1
                alto = imagen.alto or 1
                m = calcular_medidas(a.landmarks_2d, a.world_landmarks_3d, ancho, alto)
                med = MedidasPose(imagen_id=a.imagen_id, **m)
                if med.es_primer_plano:
                    primeros_planos += 1
                imagen.estado_analisis = "medida"

            sesion.add(med)
            procesadas += 1
            pendientes += 1
            if pendientes >= LOTE_COMMIT:
                sesion.commit()
                pendientes = 0
            if i % 20 == 0 or i == total:
                print(f"[{i}/{total}] derivadas")

        sesion.commit()

    print(
        f"\nHecho. Medidas: {procesadas} | primeros planos: {primeros_planos} | "
        f"sin pose: {sin_pose}"
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Deriva medidas geometricas")
    p.add_argument("--rederivar", action="store_true", help="Recalcular todo")
    args = p.parse_args()
    derivar(rederivar=args.rederivar)


if __name__ == "__main__":
    main()
