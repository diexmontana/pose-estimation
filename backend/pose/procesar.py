"""Fase 3: pasa MediaPipe sobre las imagenes indexadas y guarda lo crudo.

No etiqueta nada; solo extrae y almacena landmarks 2D, world landmarks 3D
y visibilidad por zonas. Procesa solo imagenes en estado 'registrada' (o
las que se le pidan con --reanalizar), en lotes pequenos con commit
frecuente para no acumular memoria.

Uso:
  python -m backend.pose.procesar
  python -m backend.pose.procesar --limite 10
  python -m backend.pose.procesar --reanalizar   (reprocesa todo)
"""

import argparse
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import AnalisisPose, Imagen, Raiz, Ubicacion
from backend.db.session import SessionLocal
from backend.pose.landmarker import VERSION_MODELO, DetectorPose
from backend.pose.seleccion import elegir_figura_principal, visibilidad_por_zonas

LOTE_COMMIT = 20


def ruta_de_imagen(sesion: Session, imagen: Imagen) -> Path | None:
    """Primera ubicacion disponible de la imagen, resuelta a ruta absoluta."""
    fila = sesion.execute(
        select(Ubicacion, Raiz)
        .join(Raiz, Raiz.id == Ubicacion.raiz_id)
        .where(Ubicacion.imagen_id == imagen.id, Ubicacion.estado == "disponible")
        .order_by(Ubicacion.id)
    ).first()
    if fila is None:
        return None
    ubic, raiz = fila
    return Path(raiz.ruta_montaje) / ubic.ruta_relativa


def procesar(limite: int | None = None, reanalizar: bool = False) -> None:
    detector = DetectorPose()
    procesadas = errores = sin_deteccion = 0
    pendientes = 0

    with SessionLocal() as sesion:
        consulta = select(Imagen)
        if not reanalizar:
            consulta = consulta.where(Imagen.estado_analisis == "registrada")
        consulta = consulta.order_by(Imagen.id)
        if limite:
            consulta = consulta.limit(limite)
        imagenes = list(sesion.scalars(consulta))
        total = len(imagenes)
        print(f"Imagenes a analizar: {total}")

        for i, imagen in enumerate(imagenes, 1):
            ruta = ruta_de_imagen(sesion, imagen)
            if ruta is None or not ruta.exists():
                print(f"[{i}/{total}] id {imagen.id}: sin archivo disponible, se salta")
                continue
            try:
                if reanalizar:
                    prev = sesion.scalar(
                        select(AnalisisPose).where(AnalisisPose.imagen_id == imagen.id)
                    )
                    if prev is not None:
                        sesion.delete(prev)
                        sesion.flush()

                figuras_2d, figuras_3d = detector.detectar(ruta)

                if not figuras_2d:
                    analisis = AnalisisPose(
                        imagen_id=imagen.id,
                        version_modelo=VERSION_MODELO,
                        num_figuras=0,
                        pose_detectada=False,
                        motivo="sin_deteccion",
                    )
                    sin_deteccion += 1
                else:
                    idx = elegir_figura_principal(figuras_2d)
                    lm2d = figuras_2d[idx]
                    lm3d = figuras_3d[idx] if idx < len(figuras_3d) else None
                    analisis = AnalisisPose(
                        imagen_id=imagen.id,
                        version_modelo=VERSION_MODELO,
                        num_figuras=len(figuras_2d),
                        figura_principal=idx,
                        pose_detectada=True,
                        landmarks_2d=lm2d,
                        world_landmarks_3d=lm3d,
                        visibilidad_zonas=visibilidad_por_zonas(lm2d),
                    )
                sesion.add(analisis)
                imagen.estado_analisis = "analizada"
                procesadas += 1

                pendientes += 1
                if pendientes >= LOTE_COMMIT:
                    sesion.commit()
                    pendientes = 0
                if i % 10 == 0 or i == total:
                    print(f"[{i}/{total}] procesadas")
            except Exception as e:
                errores += 1
                imagen.estado_analisis = "error"
                sesion.commit()
                pendientes = 0
                print(f"[{i}/{total}] id {imagen.id} ERROR: {e}")

        sesion.commit()

    detector.cerrar()
    print(
        f"\nHecho. Procesadas: {procesadas} | "
        f"sin deteccion: {sin_deteccion} | errores: {errores}"
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Pasa MediaPipe y guarda lo crudo")
    p.add_argument("--limite", type=int, help="Analizar solo N imagenes")
    p.add_argument("--reanalizar", action="store_true", help="Reprocesar todas")
    args = p.parse_args()
    procesar(limite=args.limite, reanalizar=args.reanalizar)


if __name__ == "__main__":
    main()
