"""Muestra un resumen del analisis de pose guardado, para comprobar la
fase 3.

Uso:  python -m backend.pose.ver
"""

from sqlalchemy import func, select

from backend.db.models import AnalisisPose, Imagen, Ubicacion
from backend.db.session import SessionLocal


def main() -> None:
    with SessionLocal() as s:
        total = s.scalar(select(func.count(AnalisisPose.id)))
        con_pose = s.scalar(
            select(func.count(AnalisisPose.id)).where(AnalisisPose.pose_detectada.is_(True))
        )
        print(f"Analisis guardados: {total} | con pose detectada: {con_pose}\n")

        filas = s.execute(
            select(AnalisisPose, Ubicacion.nombre_archivo)
            .join(Imagen, Imagen.id == AnalisisPose.imagen_id)
            .join(Ubicacion, Ubicacion.imagen_id == Imagen.id)
            .order_by(AnalisisPose.imagen_id)
        ).all()
        vistos = set()
        for a, nombre in filas:
            if a.imagen_id in vistos:
                continue
            vistos.add(a.imagen_id)
            etiquetas = {
                "cabeza": "cab", "torso": "tor", "brazos": "bra",
                "manos": "man", "piernas": "prn", "pies": "pie",
            }
            if a.pose_detectada:
                vz = a.visibilidad_zonas or {}
                zonas = " ".join(f"{etiquetas.get(k, k[:3])}={v:.2f}" for k, v in vz.items())
                print(
                    f"img {a.imagen_id:3} figs={a.num_figuras} "
                    f"principal={a.figura_principal}  {zonas}  {nombre}"
                )
            else:
                print(f"img {a.imagen_id:3} SIN POSE ({a.motivo})  {nombre}")


if __name__ == "__main__":
    main()
