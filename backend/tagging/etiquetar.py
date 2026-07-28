"""Fase 5: aplica las reglas geometricas y escribe las etiquetas.

Lee medidas_pose + analisis_pose, evalua las reglas y guarda en
imagen_opcion (origen='geometrico', con confianza y version de reglas). Los
casos ambiguos van a cola_revision. Regenerable: borra las etiquetas
geometricas previas y las de la cola antes de reescribir.

Uso:
  python -m backend.tagging.etiquetar
"""

from sqlalchemy import delete, select

from backend.db.models import (
    AnalisisPose, ColaRevision, Imagen, ImagenOpcion, MedidasPose,
)
from backend.db.session import SessionLocal
from backend.tagging.reglas import VERSION_REGLAS, evaluar
from backend.tagging.taxonomia_auto import mapa_opciones, sembrar

LOTE_COMMIT = 50


def etiquetar() -> None:
    total = con_etiquetas = en_revision = 0
    n_etiquetas = 0

    with SessionLocal() as s:
        sembrar(s)
        mapa = mapa_opciones(s)

        # limpiar lo geometrico anterior (regenerable)
        s.execute(delete(ImagenOpcion).where(ImagenOpcion.origen == "geometrico"))
        s.execute(delete(ColaRevision))
        s.commit()

        filas = s.execute(
            select(MedidasPose, AnalisisPose, Imagen)
            .join(AnalisisPose, AnalisisPose.imagen_id == MedidasPose.imagen_id)
            .join(Imagen, Imagen.id == MedidasPose.imagen_id)
            .order_by(MedidasPose.imagen_id)
        ).all()
        total = len(filas)
        print(f"Imagenes a etiquetar: {total}")

        pendientes = 0
        for i, (med, ana, img) in enumerate(filas, 1):
            m = {
                "torso_fiable": med.torso_fiable,
                "es_primer_plano": med.es_primer_plano,
                "angulos": med.angulos, "senales": med.senales,
                "escorzo": med.escorzo, "orientacion": med.orientacion,
                "extension": med.extension,
                "dispersion_vertical": med.dispersion_vertical,
                "dispersion_horizontal": med.dispersion_horizontal,
            }
            a = {
                "pose_detectada": ana.pose_detectada,
                "num_figuras": ana.num_figuras,
                "visibilidad_zonas": ana.visibilidad_zonas,
                "ancho": img.ancho, "alto": img.alto,
            }
            etiquetas, revisiones, _ = evaluar(m, a)

            for cat_cod, opt_cod, conf in etiquetas:
                clave = mapa.get((cat_cod, opt_cod))
                if clave is None:
                    continue
                cat_id, opt_id = clave
                s.add(ImagenOpcion(
                    imagen_id=med.imagen_id, categoria_id=cat_id, opcion_id=opt_id,
                    origen="geometrico", confianza=conf, version_reglas=VERSION_REGLAS,
                ))
                n_etiquetas += 1
            if etiquetas:
                con_etiquetas += 1

            for cat_cod, motivo in revisiones:
                cat_id = mapa.get((cat_cod, ""), (None, None))[0] if cat_cod else None
                # buscar categoria_id por codigo aunque no haya opcion concreta
                if cat_cod and cat_id is None:
                    cat_id = next((cid for (cc, _), (cid, _) in mapa.items() if cc == cat_cod), None)
                s.add(ColaRevision(imagen_id=med.imagen_id, categoria_id=cat_id, motivo=motivo))
                en_revision += 1

            img.estado_analisis = "etiquetada"
            pendientes += 1
            if pendientes >= LOTE_COMMIT:
                s.commit()
                pendientes = 0
            if i % 20 == 0 or i == total:
                print(f"[{i}/{total}] etiquetadas")

        s.commit()

    print(
        f"\nHecho. Imagenes con etiquetas: {con_etiquetas}/{total} | "
        f"etiquetas totales: {n_etiquetas} | entradas en revision: {en_revision}"
    )


if __name__ == "__main__":
    etiquetar()
