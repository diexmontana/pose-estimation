"""Sincroniza la taxonomia de la base con las definiciones de los ficheros
de siembra (taxonomia_auto + taxonomia_manual).

Aplica de forma segura los cambios de taxonomia (renombres, opciones nuevas,
reordenaciones y eliminaciones) sin perder las etiquetas manuales cuyo codigo
no cambia. Para lo que se elimina, borra sus referencias e informa cuantas
asignaciones manuales se vieron afectadas.

Uso:
  python -m backend.tagging.sincronizar_taxonomia            # muestra el plan
  python -m backend.tagging.sincronizar_taxonomia --aplicar  # lo ejecuta
"""

import argparse

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.db.models import (
    Categoria, CarpetaOpcion, ImagenOpcion, ModeloOpcion, Opcion,
)
from backend.db.session import SessionLocal
from backend.tagging.taxonomia_auto import CATEGORIAS_AUTO
from backend.tagging.taxonomia_manual import CATEGORIAS_MANUAL


def _walk(opciones, cat_cod, padre_cod, acc, contador):
    for op in opciones:
        cod, nombre = op[0], op[1]
        hijos = op[2] if len(op) > 2 else []
        acc[(cat_cod, cod)] = {"nombre": nombre, "padre": padre_cod, "orden": contador[0]}
        contador[0] += 1
        if hijos:
            _walk(hijos, cat_cod, cod, acc, contador)


def desired():
    """Devuelve (cats, opts) esperados a partir de las definiciones."""
    cats: dict = {}
    opts: dict = {}
    for orden, (cod, nombre, multi, opciones) in enumerate(CATEGORIAS_AUTO):
        cats[cod] = {"nombre": nombre, "multi": multi, "detectable": True,
                     "nivel": "imagen", "orden": orden}
        for oorden, (ocod, onom) in enumerate(opciones):
            opts[(cod, ocod)] = {"nombre": onom, "padre": None, "orden": oorden}
    for i, (cod, nombre, multi, nivel, opciones) in enumerate(CATEGORIAS_MANUAL):
        cats[cod] = {"nombre": nombre, "multi": multi, "detectable": False,
                     "nivel": nivel, "orden": 100 + i}
        _walk(opciones, cod, None, opts, [0])
    return cats, opts


def _plan(s: Session):
    cats_d, opts_d = desired()
    cats_db = {c.codigo: c for c in s.scalars(select(Categoria))}
    opts_db = {}  # (cat_codigo, op_codigo) -> Opcion
    cat_por_id = {c.id: c.codigo for c in cats_db.values()}
    for o in s.scalars(select(Opcion)):
        opts_db[(cat_por_id.get(o.categoria_id), o.codigo)] = o

    cats_nuevas = [c for c in cats_d if c not in cats_db]
    cats_obsoletas = [c for c in cats_db if c not in cats_d]
    opts_nuevas = [k for k in opts_d if k not in opts_db]
    opts_obsoletas = [k for k in opts_db if k not in opts_d and k[0] in cats_d]
    return cats_d, opts_d, cats_db, opts_db, {
        "cats_nuevas": cats_nuevas, "cats_obsoletas": cats_obsoletas,
        "opts_nuevas": opts_nuevas, "opts_obsoletas": opts_obsoletas,
    }


def _manuales_afectadas(s, opcion_ids):
    if not opcion_ids:
        return 0
    return s.scalar(select(func.count(ImagenOpcion.id)).where(
        ImagenOpcion.opcion_id.in_(opcion_ids), ImagenOpcion.origen == "manual")) or 0


def sincronizar(aplicar: bool = False):
    with SessionLocal() as s:
        cats_d, opts_d, cats_db, opts_db, plan = _plan(s)

        # opciones a eliminar (de categorias que se conservan)
        ops_borrar = [opts_db[k] for k in plan["opts_obsoletas"]]
        # categorias a eliminar -> tambien sus opciones
        for cod in plan["cats_obsoletas"]:
            cat = cats_db[cod]
            ops_borrar += list(s.scalars(select(Opcion).where(Opcion.categoria_id == cat.id)))
        ids_borrar = [o.id for o in ops_borrar]
        manuales = _manuales_afectadas(s, ids_borrar)

        print("Plan de sincronizacion:")
        print(f"  categorias nuevas:    {len(plan['cats_nuevas'])} {plan['cats_nuevas']}")
        print(f"  categorias obsoletas: {len(plan['cats_obsoletas'])} {plan['cats_obsoletas']}")
        print(f"  opciones nuevas:      {len(plan['opts_nuevas'])}")
        print(f"  opciones obsoletas:   {len(plan['opts_obsoletas'])} "
              f"{[k[1] for k in plan['opts_obsoletas']]}")
        print(f"  etiquetas MANUALES que se perderian: {manuales}")

        if not aplicar:
            print("\n(vista previa; ejecuta con --aplicar para hacerlo)")
            return

        # 1) upsert categorias
        for cod, spec in cats_d.items():
            cat = cats_db.get(cod)
            if cat is None:
                cat = Categoria(codigo=cod)
                s.add(cat)
                cats_db[cod] = cat
            cat.nombre = spec["nombre"]
            cat.es_multivalor = spec["multi"]
            cat.detectable_automaticamente = spec["detectable"]
            cat.nivel_sugerido = spec["nivel"]
            cat.orden = spec["orden"]
        s.flush()

        # 2) upsert opciones (primero sin padre, luego padre)
        idmap = {}  # (cat,op) -> Opcion
        for (catc, opc), spec in opts_d.items():
            cat = cats_db[catc]
            op = opts_db.get((catc, opc))
            if op is None:
                op = Opcion(categoria_id=cat.id, codigo=opc)
                s.add(op)
            op.nombre = spec["nombre"]
            op.orden = spec["orden"]
            idmap[(catc, opc)] = op
        s.flush()
        for (catc, opc), spec in opts_d.items():
            op = idmap[(catc, opc)]
            op.id_padre = idmap[(catc, spec["padre"])].id if spec["padre"] else None
        s.flush()

        # 3) eliminar obsoletas (referencias primero)
        if ids_borrar:
            for modelo in (ImagenOpcion, ModeloOpcion, CarpetaOpcion):
                s.execute(delete(modelo).where(modelo.opcion_id.in_(ids_borrar)))
            s.execute(delete(Opcion).where(Opcion.id.in_(ids_borrar)))
        for cod in plan["cats_obsoletas"]:
            s.execute(delete(Categoria).where(Categoria.id == cats_db[cod].id))

        s.commit()
        print(f"\nAplicado. Manuales eliminadas: {manuales}. "
              "Recuerda re-etiquetar para regenerar lo geometrico.")


def main():
    p = argparse.ArgumentParser(description="Sincroniza la taxonomia")
    p.add_argument("--aplicar", action="store_true")
    args = p.parse_args()
    sincronizar(aplicar=args.aplicar)


if __name__ == "__main__":
    main()
