"""Muestra un resumen de las medidas derivadas, para comprobar la fase 4.

Uso:
  python -m backend.tagging.ver_medidas
  python -m backend.tagging.ver_medidas --id 22   (detalle completo de una imagen)
"""

import argparse
import json

from sqlalchemy import func, select

from backend.db.models import Imagen, MedidasPose, Ubicacion
from backend.db.session import SessionLocal


def _nombre(sesion, imagen_id):
    return sesion.scalar(
        select(Ubicacion.nombre_archivo).where(Ubicacion.imagen_id == imagen_id).limit(1)
    )


def detalle(imagen_id: int) -> None:
    with SessionLocal() as s:
        m = s.scalar(select(MedidasPose).where(MedidasPose.imagen_id == imagen_id))
        if not m:
            print(f"No hay medidas para la imagen {imagen_id}")
            return
        print(f"Imagen {imagen_id}  ({_nombre(s, imagen_id)})")
        print(f"  torso_fiable={m.torso_fiable}  primer_plano={m.es_primer_plano}  reglas={m.version_reglas}")
        print(f"  extension={m.extension}  compacidad={m.compacidad}")
        print(f"  disp_vertical={m.dispersion_vertical}  disp_horizontal={m.dispersion_horizontal}")
        for etiqueta, valor in (
            ("angulos", m.angulos), ("senales", m.senales),
            ("escorzo", m.escorzo), ("orientacion", m.orientacion),
        ):
            print(f"  {etiqueta}: {json.dumps(valor, ensure_ascii=False)}")


def resumen() -> None:
    with SessionLocal() as s:
        total = s.scalar(select(func.count(MedidasPose.id)))
        fiables = s.scalar(select(func.count()).where(MedidasPose.torso_fiable.is_(True)))
        pp = s.scalar(select(func.count()).where(MedidasPose.es_primer_plano.is_(True)))
        print(f"Medidas: {total} | con torso fiable: {fiables} | primeros planos: {pp}\n")

        filas = s.execute(
            select(MedidasPose, Ubicacion.nombre_archivo)
            .join(Ubicacion, Ubicacion.imagen_id == MedidasPose.imagen_id)
            .order_by(MedidasPose.imagen_id)
        ).all()
        vistos = set()
        for m, nombre in filas:
            if m.imagen_id in vistos:
                continue
            vistos.add(m.imagen_id)
            if not m.torso_fiable:
                mcr = (m.senales or {}).get("manos_cerca_rostro")
                print(f"img {m.imagen_id:3} PRIMER PLANO  manos_rostro={mcr}  {nombre}")
            else:
                sen = m.senales or {}
                esc = m.escorzo or {}
                esc_min = min([v for v in esc.values() if v is not None], default=None)
                print(
                    f"img {m.imagen_id:3} ext={m.extension} "
                    f"contra={sen.get('contraposto')} "
                    f"manos_arriba={sen.get('manos_sobre_cabeza')} "
                    f"escorzo_min={esc_min}  {nombre}"
                )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--id", type=int, help="Detalle completo de una imagen")
    args = p.parse_args()
    if args.id:
        detalle(args.id)
    else:
        resumen()


if __name__ == "__main__":
    main()
