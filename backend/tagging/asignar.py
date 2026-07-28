"""CLI minimo de etiquetado manual a nivel de modelo y carpeta (fase 6,
trozo 1). La interfaz completa llega mas adelante; esto permite ya asignar
atributos, propagar y comprobar la herencia.

Ejemplos:
  # crear una modelo y asignarla en bloque a todas las fotos de una carpeta
  python -m backend.tagging.asignar modelo-crear "Ana"
  python -m backend.tagging.asignar carpeta-modelo "modelo_a" "Ana"

  # asignar atributos (fuente de verdad)
  python -m backend.tagging.asignar modelo-opcion "Ana" tipo_cuerpo delgada
  python -m backend.tagging.asignar carpeta-opcion "modelo_b/sesion1" estilo cosplay

  # propagar a las imagenes y ver el resultado
  python -m backend.tagging.asignar rematerializar
  python -m backend.tagging.asignar efectivas 22
"""

import argparse

from sqlalchemy import select

from sqlalchemy import delete

from backend.db.models import (
    Carpeta, Categoria, CarpetaOpcion, ColaRevision, Imagen, ImagenModelo,
    ImagenOpcion, Modelo, ModeloOpcion, Opcion, Ubicacion,
)
from backend.db.session import SessionLocal
from backend.tagging.herencia import rematerializar, resolver_efectivas
from backend.tagging.taxonomia_auto import sembrar as sembrar_auto
from backend.tagging.taxonomia_manual import sembrar_manual


def _buscar_carpeta(s, ruta):
    """Busca una carpeta por su ruta relativa exacta o, si no, por el nombre
    de la ultima carpeta (hoja). Si el nombre de hoja es ambiguo, lista las
    opciones para que se de la ruta completa."""
    c = s.scalar(select(Carpeta).where(Carpeta.ruta_relativa == ruta))
    if c:
        return c
    cand = list(s.scalars(select(Carpeta).where(Carpeta.ruta_relativa.like(f"%/{ruta}"))))
    if len(cand) == 1:
        return cand[0]
    if not cand:
        raise SystemExit(f"No existe la carpeta '{ruta}'")
    rutas = "\n  ".join(sorted(c.ruta_relativa for c in cand))
    raise SystemExit(f"'{ruta}' es ambiguo. Usa la ruta completa:\n  {rutas}")


def _descendientes(s, carpeta_id):
    """IDs de la carpeta y todas sus subcarpetas."""
    hijos = {}
    for c in s.scalars(select(Carpeta)):
        hijos.setdefault(c.carpeta_padre_id, []).append(c.id)
    out, pila = set(), [carpeta_id]
    while pila:
        cid = pila.pop()
        out.add(cid)
        pila.extend(hijos.get(cid, []))
    return out


def _opcion(s, cat_cod, opt_cod):
    fila = s.execute(
        select(Categoria, Opcion).join(Opcion, Opcion.categoria_id == Categoria.id)
        .where(Categoria.codigo == cat_cod, Opcion.codigo == opt_cod)
    ).first()
    if fila is None:
        raise SystemExit(f"No existe categoria/opcion: {cat_cod}/{opt_cod}")
    return fila  # (Categoria, Opcion)


def modelo_crear(nombre):
    with SessionLocal() as s:
        if s.scalar(select(Modelo).where(Modelo.nombre == nombre)):
            print(f"La modelo '{nombre}' ya existe")
            return
        s.add(Modelo(nombre=nombre)); s.commit()
        print(f"Modelo creada: {nombre}")


def carpeta_modelo(ruta, nombre):
    """Asigna una modelo en bloque a todas las imagenes de una carpeta."""
    with SessionLocal() as s:
        modelo = s.scalar(select(Modelo).where(Modelo.nombre == nombre))
        if not modelo:
            raise SystemExit(f"No existe la modelo '{nombre}' (crea con modelo-crear)")
        carpeta = _buscar_carpeta(s, ruta)
        # incluye la carpeta y sus subcarpetas (una modelo suele abarcar todo)
        carpetas = _descendientes(s, carpeta.id)
        img_ids = set(s.scalars(
            select(Ubicacion.imagen_id).where(Ubicacion.carpeta_id.in_(carpetas))
        ))
        n = 0
        for iid in img_ids:
            if not s.get(ImagenModelo, {"imagen_id": iid, "modelo_id": modelo.id}):
                s.add(ImagenModelo(imagen_id=iid, modelo_id=modelo.id)); n += 1
        s.commit()
        print(f"Modelo '{nombre}' asignada a {n} imagenes de '{ruta}'")


def modelo_opcion(nombre, cat_cod, opt_cod):
    with SessionLocal() as s:
        modelo = s.scalar(select(Modelo).where(Modelo.nombre == nombre))
        if not modelo:
            raise SystemExit(f"No existe la modelo '{nombre}'")
        cat, op = _opcion(s, cat_cod, opt_cod)
        if not s.scalar(select(ModeloOpcion).where(
                ModeloOpcion.modelo_id == modelo.id, ModeloOpcion.opcion_id == op.id)):
            s.add(ModeloOpcion(modelo_id=modelo.id, categoria_id=cat.id, opcion_id=op.id))
            s.commit()
        print(f"Modelo '{nombre}': {cat_cod}={opt_cod}")


def carpeta_opcion(ruta, cat_cod, opt_cod):
    with SessionLocal() as s:
        carpeta = _buscar_carpeta(s, ruta)
        cat, op = _opcion(s, cat_cod, opt_cod)
        if not s.scalar(select(CarpetaOpcion).where(
                CarpetaOpcion.carpeta_id == carpeta.id, CarpetaOpcion.opcion_id == op.id)):
            s.add(CarpetaOpcion(carpeta_id=carpeta.id, categoria_id=cat.id, opcion_id=op.id))
            s.commit()
        print(f"Carpeta '{ruta}': {cat_cod}={opt_cod}")


def cmd_rematerializar():
    with SessionLocal() as s:
        # asegurar taxonomia sembrada
        sembrar_auto(s); sembrar_manual(s)
        r = rematerializar(s)
        print(f"Materializadas: {r['carpeta']} por carpeta, {r['modelo']} por modelo")


def imagen_opcion(imagen_id, cat_cod, opt_cod):
    """Etiqueta manual a nivel de imagen (origen='manual'). Gana a la
    geometrica por precedencia; la geometrica NO se borra (queda la traza).
    Para categorias de valor unico reemplaza la manual anterior."""
    with SessionLocal() as s:
        if not s.get(Imagen, imagen_id):
            raise SystemExit(f"No existe la imagen {imagen_id}")
        cat, op = _opcion(s, cat_cod, opt_cod)
        if not cat.es_multivalor:
            s.execute(delete(ImagenOpcion).where(
                ImagenOpcion.imagen_id == imagen_id,
                ImagenOpcion.categoria_id == cat.id,
                ImagenOpcion.origen == "manual",
            ))
        ya = s.scalar(select(ImagenOpcion).where(
            ImagenOpcion.imagen_id == imagen_id, ImagenOpcion.opcion_id == op.id,
            ImagenOpcion.origen == "manual"))
        if not ya:
            s.add(ImagenOpcion(imagen_id=imagen_id, categoria_id=cat.id, opcion_id=op.id,
                               origen="manual"))
        # resolver cualquier revision pendiente de esa categoria
        s.execute(
            delete(ColaRevision).where(
                ColaRevision.imagen_id == imagen_id, ColaRevision.categoria_id == cat.id)
        )
        s.commit()
        print(f"Imagen {imagen_id}: {cat_cod}={opt_cod} (manual)")


def imagen_quitar(imagen_id, cat_cod, opt_cod=None):
    """Quita etiquetas manuales de una imagen (toda la categoria, o una
    opcion concreta). No toca las geometricas."""
    with SessionLocal() as s:
        cat = s.scalar(select(Categoria).where(Categoria.codigo == cat_cod))
        if not cat:
            raise SystemExit(f"No existe la categoria '{cat_cod}'")
        cond = [ImagenOpcion.imagen_id == imagen_id,
                ImagenOpcion.categoria_id == cat.id, ImagenOpcion.origen == "manual"]
        if opt_cod:
            op = s.scalar(select(Opcion).where(Opcion.categoria_id == cat.id, Opcion.codigo == opt_cod))
            if not op:
                raise SystemExit(f"No existe la opcion '{opt_cod}'")
            cond.append(ImagenOpcion.opcion_id == op.id)
        n = s.execute(delete(ImagenOpcion).where(*cond)).rowcount
        s.commit()
        print(f"Imagen {imagen_id}: quitadas {n} etiquetas manuales de {cat_cod}")


def revision():
    """Lista las imagenes con revisiones pendientes, agrupadas."""
    with SessionLocal() as s:
        filas = s.execute(
            select(ColaRevision.imagen_id, Categoria.codigo, ColaRevision.motivo)
            .outerjoin(Categoria, Categoria.id == ColaRevision.categoria_id)
            .where(ColaRevision.estado == "pendiente")
            .order_by(ColaRevision.imagen_id)
        ).all()
        print(f"Revisiones pendientes: {len(filas)}")
        for iid, cat, motivo in filas:
            nombre = s.scalar(select(Ubicacion.nombre_archivo).where(Ubicacion.imagen_id == iid).limit(1))
            print(f"  img {iid:3} {cat or '(general)':22} {motivo:14} {nombre}")


def efectivas(imagen_id):
    with SessionLocal() as s:
        nombre = s.scalar(select(Ubicacion.nombre_archivo).where(Ubicacion.imagen_id == imagen_id).limit(1))
        print(f"Etiqueta efectiva de la imagen {imagen_id} ({nombre}):")
        for cat, ops in sorted(resolver_efectivas(s, imagen_id).items()):
            print(f"  {cat:22} = {', '.join(ops)}")


def main():
    p = argparse.ArgumentParser(description="Etiquetado manual modelo/carpeta")
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("modelo-crear"); q.add_argument("nombre")
    q = sub.add_parser("carpeta-modelo"); q.add_argument("ruta"); q.add_argument("nombre")
    q = sub.add_parser("modelo-opcion"); q.add_argument("nombre"); q.add_argument("categoria"); q.add_argument("opcion")
    q = sub.add_parser("carpeta-opcion"); q.add_argument("ruta"); q.add_argument("categoria"); q.add_argument("opcion")
    sub.add_parser("rematerializar")
    q = sub.add_parser("imagen-opcion"); q.add_argument("imagen_id", type=int); q.add_argument("categoria"); q.add_argument("opcion")
    q = sub.add_parser("imagen-quitar"); q.add_argument("imagen_id", type=int); q.add_argument("categoria"); q.add_argument("opcion", nargs="?")
    sub.add_parser("revision")
    q = sub.add_parser("efectivas"); q.add_argument("imagen_id", type=int)
    args = p.parse_args()

    # asegurar que la taxonomia esta sembrada antes de cualquier asignacion
    with SessionLocal() as s:
        sembrar_auto(s); sembrar_manual(s)

    if args.cmd == "modelo-crear": modelo_crear(args.nombre)
    elif args.cmd == "carpeta-modelo": carpeta_modelo(args.ruta, args.nombre)
    elif args.cmd == "modelo-opcion": modelo_opcion(args.nombre, args.categoria, args.opcion)
    elif args.cmd == "carpeta-opcion": carpeta_opcion(args.ruta, args.categoria, args.opcion)
    elif args.cmd == "rematerializar": cmd_rematerializar()
    elif args.cmd == "imagen-opcion": imagen_opcion(args.imagen_id, args.categoria, args.opcion)
    elif args.cmd == "imagen-quitar": imagen_quitar(args.imagen_id, args.categoria, args.opcion)
    elif args.cmd == "revision": revision()
    elif args.cmd == "efectivas": efectivas(args.imagen_id)


if __name__ == "__main__":
    main()
