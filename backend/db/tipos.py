"""Tipo de columna para vectores.

En Postgres usa el tipo nativo de pgvector (permite busqueda vectorial y,
si algun dia hiciera falta, un indice). En otros dialectos (SQLite, para los
tests) cae a JSON. Asi el mismo modelo funciona en ambos.
"""

from sqlalchemy.types import JSON, TypeDecorator


class Vector(TypeDecorator):
    impl = JSON
    cache_ok = True

    def __init__(self, dim=None, **kw):
        self.dim = dim
        super().__init__(**kw)

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector as PGVector
            return dialect.type_descriptor(PGVector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        return None if value is None else list(value)

    def process_result_value(self, value, dialect):
        return None if value is None else list(value)
