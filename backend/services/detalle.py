"""Servicio del detalle de imagen: etiquetas editables, edicion manual,
modelo por imagen, overlay del esqueleto y revision guiada. Sin HTTP.
"""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.db.models import (
    AnalisisPose, Carpeta, Categoria, ColaRevision, Imagen, ImagenModelo,
    ImagenOpcion, MedidasPose, Miniatura, Modelo, Opcion, Ubicacion,
)
from backend.services.galeria import agrupar, arbol_taxonomia
from backend.tagging.herencia import PRECEDENCIA


def _una_ubicacion(s, imagen_id):
    return s.execute(
        select(Ubicacion.nombre_archivo, Ubicacion.estado)
        .where(Ubicacion.imagen_id == imagen_id).order_by(Ubicacion.id).limit(1)
    ).first()


def _aplanar(opciones, prof=0):
    salida = []
    for o in opciones:
        salida.append({"id": o["id"], "codigo": o.get("codigo"), "nombre": o["nombre"], "prof": prof})
        if o["hijos"]:
            salida.extend(_aplanar(o["hijos"], prof + 1))
    return salida


def datos(s: Session, imagen_id: int):
    img = s.get(Imagen, imagen_id)
    if not img:
        return None
    ubic = _una_ubicacion(s, imagen_id)

    filas = s.execute(
        select(ImagenOpcion.categoria_id, ImagenOpcion.opcion_id, ImagenOpcion.origen)
        .where(ImagenOpcion.imagen_id == imagen_id)
    ).all()
    por_cat: dict = {}
    for cat, op, origen in filas:
        por_cat.setdefault(cat, {}).setdefault(op, []).append(origen)

    codemap = {c.codigo: c for c in s.scalars(select(Categoria))}
    categorias = []
    for cat in arbol_taxonomia(s):
        cmodel = codemap[cat["codigo"]]
        rows = por_cat.get(cmodel.id, {})
        manual_ids = {op for op, origs in rows.items() if "manual" in origs}
        if cmodel.es_multivalor:
            efect_ids = set(rows.keys())
        else:
            efect_ids = set()
            if rows:
                mejor = max(rows.items(),
                            key=lambda kv: max(PRECEDENCIA.get(o, 0) for o in kv[1]))
                efect_ids = {mejor[0]}
        opciones = [
            {**o, "sel": o["id"] in efect_ids, "manual": o["id"] in manual_ids}
            for o in _aplanar(cat["opciones"])
        ]
        categorias.append({
            "codigo": cat["codigo"], "nombre": cat["nombre"],
            "multivalor": cmodel.es_multivalor,
            "automatica": cmodel.detectable_automaticamente,
            "opciones": opciones,
            "tiene_valor": bool(efect_ids),
            "efect_codigos": {o["codigo"] for o in _aplanar(cat["opciones"])
                              if o["id"] in efect_ids},
        })

    # Composicion solo tiene sentido con dos o mas figuras (9.3).
    num_efectivo = next((c["efect_codigos"] for c in categorias
                         if c["codigo"] == "numero_figuras"), set())
    if not ({"dos", "tres_o_mas"} & num_efectivo):
        categorias = [c for c in categorias if c["codigo"] != "composicion"]

    grupos = agrupar(categorias)

    return {
        "id": imagen_id,
        "nombre": ubic[0] if ubic else f"imagen {imagen_id}",
        "disponible": (ubic[1] == "disponible") if ubic else False,
        "miniatura": s.scalar(select(Miniatura.ruta).where(Miniatura.imagen_id == imagen_id)),
        "tiene_overlay": bool(s.scalar(
            select(AnalisisPose.id).where(AnalisisPose.imagen_id == imagen_id,
                                          AnalisisPose.pose_detectada.is_(True)))),
        "categorias": categorias,
        "grupos": grupos,
        "modelo_actual": modelo_de(s, imagen_id),
        "modelos": [m for m in s.scalars(select(Modelo.nombre).order_by(Modelo.nombre))],
        "prev_id": s.scalar(select(func.max(Imagen.id)).where(Imagen.id < imagen_id)),
        "next_id": s.scalar(select(func.min(Imagen.id)).where(Imagen.id > imagen_id)),
    }


def set_manual(s: Session, imagen_id: int, opcion_id: int):
    op = s.get(Opcion, opcion_id)
    if not op:
        return
    cat = s.get(Categoria, op.categoria_id)
    if not cat.es_multivalor:
        s.execute(delete(ImagenOpcion).where(
            ImagenOpcion.imagen_id == imagen_id,
            ImagenOpcion.categoria_id == cat.id, ImagenOpcion.origen == "manual"))
    existe = s.scalar(select(ImagenOpcion).where(
        ImagenOpcion.imagen_id == imagen_id, ImagenOpcion.opcion_id == opcion_id,
        ImagenOpcion.origen == "manual"))
    if not existe:
        s.add(ImagenOpcion(imagen_id=imagen_id, categoria_id=cat.id, opcion_id=opcion_id,
                           origen="manual"))
    s.execute(delete(ColaRevision).where(
        ColaRevision.imagen_id == imagen_id, ColaRevision.categoria_id == cat.id))
    s.commit()


def quitar_manual(s: Session, imagen_id: int, categoria_codigo: str = None, opcion_id: int = None):
    cond = [ImagenOpcion.imagen_id == imagen_id, ImagenOpcion.origen == "manual"]
    if opcion_id:
        cond.append(ImagenOpcion.opcion_id == opcion_id)
    if categoria_codigo:
        cat = s.scalar(select(Categoria).where(Categoria.codigo == categoria_codigo))
        if cat:
            cond.append(ImagenOpcion.categoria_id == cat.id)
    s.execute(delete(ImagenOpcion).where(*cond))
    s.commit()


def modelo_de(s: Session, imagen_id: int) -> str:
    return s.scalar(
        select(Modelo.nombre).join(ImagenModelo, ImagenModelo.modelo_id == Modelo.id)
        .where(ImagenModelo.imagen_id == imagen_id).limit(1)) or ""


def _carpeta_subarbol_imagenes(s: Session, carpeta_id: int) -> list[int]:
    hijos: dict = {}
    for cid, padre in s.execute(select(Carpeta.id, Carpeta.carpeta_padre_id)):
        hijos.setdefault(padre, []).append(cid)
    carpetas, pila = set(), [carpeta_id]
    while pila:
        c = pila.pop()
        carpetas.add(c)
        pila.extend(hijos.get(c, []))
    return list(s.scalars(select(Ubicacion.imagen_id)
                          .where(Ubicacion.carpeta_id.in_(carpetas)).distinct()))


def set_modelo(s: Session, imagen_id: int, nombre: str, a_carpeta: bool = False) -> str:
    nombre = (nombre or "").strip()
    ids = [imagen_id]
    if a_carpeta:
        ubic = s.scalar(select(Ubicacion).where(
            Ubicacion.imagen_id == imagen_id, Ubicacion.carpeta_id.isnot(None))
            .order_by(Ubicacion.id))
        if ubic and ubic.carpeta_id:
            ids = _carpeta_subarbol_imagenes(s, ubic.carpeta_id) or ids
    # una imagen = una modelo: se reemplaza
    s.execute(delete(ImagenModelo).where(ImagenModelo.imagen_id.in_(ids)))
    if not nombre:
        s.commit()
        return ""
    modelo = s.scalar(select(Modelo).where(Modelo.nombre == nombre))
    if modelo is None:
        modelo = Modelo(nombre=nombre)
        s.add(modelo)
        s.flush()
    for iid in ids:
        s.add(ImagenModelo(imagen_id=iid, modelo_id=modelo.id))
    s.commit()
    return nombre


def review_lista(s: Session):
    """Orden de la revision guiada: primero las imagenes con revision pendiente
    (dudosas), luego el resto. Devuelve (lista_ids, n_dudosas)."""
    dudosas = sorted(set(s.scalars(
        select(ColaRevision.imagen_id).where(ColaRevision.estado == "pendiente"))))
    dud_set = set(dudosas)
    resto = [i for i in s.scalars(select(Imagen.id).order_by(Imagen.id)) if i not in dud_set]
    return dudosas + resto, len(dudosas)


def review_contexto(s: Session, imagen_id: int) -> dict:
    orden, n_dud = review_lista(s)
    if imagen_id not in orden:
        return {"pos": None, "total": len(orden), "next_rev": None,
                "es_dudosa": False, "dudosas_restantes": n_dud}
    idx = orden.index(imagen_id)
    return {
        "pos": idx + 1, "total": len(orden),
        "next_rev": orden[idx + 1] if idx + 1 < len(orden) else None,
        "es_dudosa": idx < n_dud, "dudosas_restantes": n_dud,
    }


def overlay_bytes(s: Session, imagen_id: int):
    """JPEG con el esqueleto dibujado sobre la imagen original. None si no se
    puede (imagen no disponible)."""
    import cv2

    from backend.tagging import overlay as ov

    ruta, _ = ov.ruta_imagen(s, imagen_id)
    if ruta is None or not ruta.exists():
        return None
    img = cv2.imread(str(ruta))
    if img is None:
        return None
    ana = s.scalar(select(AnalisisPose).where(AnalisisPose.imagen_id == imagen_id))
    med = s.scalar(select(MedidasPose).where(MedidasPose.imagen_id == imagen_id))
    if ana and ana.landmarks_2d:
        ov.dibujar(img, ana.landmarks_2d, med.angulos if med else None)
    ok, buf = cv2.imencode(".jpg", img)
    return buf.tobytes() if ok else None
