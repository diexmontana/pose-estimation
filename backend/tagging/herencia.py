"""Herencia y materializacion (seccion 6.3).

Las asignaciones a nivel de modelo (`modelo_opcion`) y carpeta
(`carpeta_opcion`) son la fuente de verdad. Aqui se **materializan** hacia
`imagen_opcion` con su origen ('modelo' / 'carpeta'), de modo que las
consultas sobre imagenes sigan siendo simples.

Reglas:
- La herencia de carpeta **baja a las subcarpetas**. Una subcarpeta puede
  **contradecir** a su padre: si define la misma categoria, su valor gana
  para su subarbol (el ancestro mas cercano manda).
- Precedencia al resolver la etiqueta efectiva: imagen(manual) > carpeta >
  modelo > geometrico. Todo lo manual gana a lo geometrico.
- Es idempotente y regenerable: se puede rematerializar tras indexar imagenes
  nuevas (que asi heredan) o cambiar una asignacion.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.db.models import (
    Carpeta, Categoria, CarpetaOpcion, ImagenModelo, ImagenOpcion, ModeloOpcion,
    Opcion, Ubicacion,
)

PRECEDENCIA = {"manual": 3, "carpeta": 2, "modelo": 1, "geometrico": 0}


def _efectivas_por_carpeta(sesion: Session):
    """Para cada carpeta, opciones efectivas por categoria = las del ancestro
    mas cercano (incluida ella misma) que defina esa categoria."""
    carpetas = {c.id: c.carpeta_padre_id for c in sesion.scalars(select(Carpeta))}
    # capa propia: carpeta -> categoria -> set(opciones)
    capa: dict[int, dict[int, set[int]]] = {}
    for co in sesion.scalars(select(CarpetaOpcion)):
        capa.setdefault(co.carpeta_id, {}).setdefault(co.categoria_id, set()).add(co.opcion_id)

    efectivas: dict[int, dict[int, set[int]]] = {}
    for cid in carpetas:
        acc: dict[int, set[int]] = {}
        actual = cid
        visto = set()
        while actual is not None and actual not in visto:
            visto.add(actual)
            for cat_id, ops in capa.get(actual, {}).items():
                if cat_id not in acc:  # el mas cercano ya visto manda
                    acc[cat_id] = set(ops)
            actual = carpetas.get(actual)
        efectivas[cid] = acc
    return efectivas


def rematerializar(sesion: Session) -> dict:
    """Reconstruye todas las filas de imagen_opcion con origen modelo/carpeta
    desde las fuentes de verdad. No toca las geometricas ni las manuales."""
    multivalor = {c.id: c.es_multivalor for c in sesion.scalars(select(Categoria))}

    sesion.execute(delete(ImagenOpcion).where(ImagenOpcion.origen.in_(["modelo", "carpeta"])))
    sesion.flush()

    n_carpeta = n_modelo = 0

    # --- Carpeta ---
    efectivas = _efectivas_por_carpeta(sesion)
    # imagen -> carpetas donde vive (por sus ubicaciones)
    img_carpetas: dict[int, list[int]] = {}
    for ubic in sesion.scalars(select(Ubicacion).where(Ubicacion.carpeta_id.isnot(None))):
        img_carpetas.setdefault(ubic.imagen_id, [])
        if ubic.carpeta_id not in img_carpetas[ubic.imagen_id]:
            img_carpetas[ubic.imagen_id].append(ubic.carpeta_id)

    for imagen_id, carpetas in img_carpetas.items():
        acumulado: dict[int, set[int]] = {}
        for cid in carpetas:
            for cat_id, ops in efectivas.get(cid, {}).items():
                if multivalor.get(cat_id):
                    acumulado.setdefault(cat_id, set()).update(ops)
                else:
                    acumulado.setdefault(cat_id, set(ops))  # unico: primera carpeta gana
        for cat_id, ops in acumulado.items():
            for opt_id in ops:
                sesion.add(ImagenOpcion(imagen_id=imagen_id, categoria_id=cat_id,
                                        opcion_id=opt_id, origen="carpeta"))
                n_carpeta += 1

    # --- Modelo ---
    modelo_ops: dict[int, list[ModeloOpcion]] = {}
    for mo in sesion.scalars(select(ModeloOpcion)):
        modelo_ops.setdefault(mo.modelo_id, []).append(mo)
    for im in sesion.scalars(select(ImagenModelo)):
        for mo in modelo_ops.get(im.modelo_id, []):
            sesion.add(ImagenOpcion(imagen_id=im.imagen_id, categoria_id=mo.categoria_id,
                                    opcion_id=mo.opcion_id, origen="modelo"))
            n_modelo += 1

    sesion.commit()
    return {"carpeta": n_carpeta, "modelo": n_modelo}


def resolver_efectivas(sesion: Session, imagen_id: int) -> dict:
    """Etiqueta efectiva de una imagen por categoria, aplicando precedencia.
    Para categorias de valor unico deja solo la de mayor precedencia; para
    multivalor une todas las opciones de cualquier origen."""
    filas = sesion.execute(
        select(Categoria.codigo, Categoria.es_multivalor, Opcion.nombre,
               ImagenOpcion.origen)
        .join(Categoria, Categoria.id == ImagenOpcion.categoria_id)
        .join(Opcion, Opcion.id == ImagenOpcion.opcion_id)
        .where(ImagenOpcion.imagen_id == imagen_id)
    ).all()

    unico: dict[str, tuple[int, str]] = {}   # cat -> (precedencia, opcion)
    multi: dict[str, set[str]] = {}
    for cat, es_multi, opt, origen in filas:
        if es_multi:
            multi.setdefault(cat, set()).add(opt)
        else:
            p = PRECEDENCIA.get(origen, 0)
            if cat not in unico or p > unico[cat][0]:
                unico[cat] = (p, opt)

    resultado = {cat: [opt] for cat, (_, opt) in unico.items()}
    for cat, ops in multi.items():
        resultado[cat] = sorted(ops)
    return resultado
