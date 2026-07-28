"""Gestion del esquema sin Alembic.

Hasta la fase 6 se usaba para recrear todo (los datos eran regenerables). A
partir de la fase 6 el esquema lo gestiona Alembic; este script queda para
dos usos puntuales:

  python -m backend.db.reset_db               # recrea todo (drop + create)
  python -m backend.db.reset_db --solo-borrar # deja la base vacia, para
                                              # generar el baseline de Alembic
"""

import argparse

from sqlalchemy import inspect, text

from backend.db.models import Base
from backend.db.session import engine


def _extension_vector():
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


def borrar() -> None:
    Base.metadata.drop_all(engine)
    print(f"Base vaciada en {engine.url.render_as_string(hide_password=True)}")


def reset() -> None:
    _extension_vector()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    tablas = sorted(inspect(engine).get_table_names())
    print(f"Esquema recreado en {engine.url.render_as_string(hide_password=True)}")
    print(f"Tablas ({len(tablas)}): " + ", ".join(tablas))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--solo-borrar", action="store_true",
                   help="Vacia la base sin recrear (para el baseline de Alembic)")
    args = p.parse_args()
    if args.solo_borrar:
        _extension_vector()
        borrar()
    else:
        reset()
