"""Muestra el contenido indexado, para comprobar la fase 2.

Uso:  python -m backend.indexing.listar
"""

from sqlalchemy import func, select

from backend.db.models import Imagen, Miniatura, Raiz, Ubicacion
from backend.db.session import SessionLocal


def main() -> None:
    with SessionLocal() as s:
        for raiz in s.scalars(select(Raiz)):
            print(f"Raiz '{raiz.nombre}' ({raiz.tipo}) -> {raiz.ruta_montaje}")

        total_img = s.scalar(select(func.count(Imagen.id)))
        total_ubi = s.scalar(select(func.count(Ubicacion.id)))
        total_min = s.scalar(select(func.count(Miniatura.id)))
        print(f"\nImagenes: {total_img} | Ubicaciones: {total_ubi} | Miniaturas: {total_min}\n")

        filas = s.execute(
            select(Imagen, Ubicacion)
            .join(Ubicacion, Ubicacion.imagen_id == Imagen.id)
            .order_by(Imagen.id, Ubicacion.ruta_relativa)
        ).all()
        for imagen, ubic in filas:
            print(
                f"[{imagen.id:3}] {imagen.hash_contenido[:10]}  "
                f"{imagen.ancho}x{imagen.alto} {imagen.formato:5} "
                f"{ubic.estado:10} {ubic.ruta_relativa}"
            )


if __name__ == "__main__":
    main()
