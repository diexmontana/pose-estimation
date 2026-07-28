"""Comprobacion de la fase 1: conexion, extension pgvector y tablas.

Uso:  python -m backend.db.check_db
"""

from sqlalchemy import inspect, text

from backend.db.session import engine


def check() -> None:
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
        print(f"Conectado: {version}")

        vector = conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
        if vector:
            print(f"pgvector instalado, version {vector}")
        else:
            print("AVISO: la extension pgvector NO esta creada (ejecuta reset_db)")

    esperadas = {
        "raiz", "carpeta", "imagen", "ubicacion", "miniatura",
        "coleccion", "imagen_coleccion",
    }
    tablas = set(inspect(engine).get_table_names())
    faltan = esperadas - tablas
    if faltan:
        print(f"AVISO: faltan tablas: {', '.join(sorted(faltan))} (ejecuta reset_db)")
    else:
        print(f"Tablas correctas: {', '.join(sorted(esperadas))}")
    print("Fase 1 OK" if not faltan and vector else "Fase 1 incompleta")


if __name__ == "__main__":
    check()
