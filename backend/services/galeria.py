"""Servicio de galeria y filtros (fase 8). Toda la logica vive aqui, sin
saber nada de HTTP: las rutas son una fachada delgada que llama a estas
funciones.
"""

import random

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.db.models import (
    Categoria, Coleccion, Imagen, ImagenColeccion, ImagenModelo, ImagenOpcion,
    Miniatura, Modelo, Opcion, Ubicacion,
)
from backend.tagging.herencia import PRECEDENCIA

# Categorias que se muestran como resumen bajo cada miniatura.
CATEGORIAS_RESUMEN = ["postura", "orientacion_corporal", "encuadre", "escorzo"]

# Categorias ocultas por ahora en la interfaz (siguen en la taxonomia).
CATEGORIAS_OCULTAS = {
    "accesorios", "props", "corte_detalle", "mangas", "material_acabado",
    "prenda", "maquillaje", "peinado", "grado_gotico", "estilo",
}

# Agrupacion para la interfaz. El primer grupo (nombre vacio) esta siempre
# visible; el resto se pliega. (nombre, abierto_por_defecto, [codigos]).
GRUPOS = [
    ("", True, ["encuadre", "postura", "orientacion_corporal", "dinamismo",
                "numero_figuras", "composicion", "angulo_camara", "vestimenta"]),
    ("Características del modelo", False, ["sexo", "edad"]),
    ("Configuración corporal", False, ["manos_rostro", "brazos", "piernas",
                                       "torsion", "contraposto"]),
    ("Escorzo", False, ["escorzo", "miembro_escorzado"]),
    ("Otras características del modelo", False, ["tipo_cuerpo", "altura", "estado",
                                                "rasgos_tono", "rasgos_destacados",
                                                "accion", "iluminacion"]),
    ("Apariencia - Look", False, ["color_cabello", "estilo", "grado_gotico",
                                  "peinado", "maquillaje", "prenda",
                                  "material_acabado", "mangas", "corte_detalle",
                                  "props", "accesorios"]),
    ("Otras características", False, ["partes_visibles", "orientacion_imagen"]),
]


def agrupar(categorias: list[dict]) -> list[dict]:
    """Reparte una lista de categorias (cada una con 'codigo') en los grupos
    de la interfaz, respetando el orden. Las que no encajen van a 'Sin agrupar'."""
    por_cod = {c["codigo"]: c for c in categorias}
    usados = set()
    grupos = []
    for nombre, abierto, codes in GRUPOS:
        cats = [por_cod[c] for c in codes if c in por_cod]
        usados.update(c for c in codes if c in por_cod)
        if cats:
            grupos.append({"nombre": nombre, "abierto": abierto, "categorias": cats})
    restantes = [c for cod, c in por_cod.items() if cod not in usados]
    if restantes:
        grupos.append({"nombre": "Sin agrupar", "abierto": False, "categorias": restantes})
    return grupos


def arbol_agrupado(s) -> list[dict]:
    return agrupar(arbol_taxonomia(s))


# --- taxonomia para el panel de filtros ---

def arbol_taxonomia(s: Session) -> list[dict]:
    """Categorias con sus opciones en arbol, para pintar el panel de filtros."""
    cats = list(s.scalars(select(Categoria).order_by(Categoria.orden)))
    ops = list(s.scalars(select(Opcion)))
    hijos: dict = {}
    for o in ops:
        hijos.setdefault((o.categoria_id, o.id_padre), []).append(o)

    def construir(cat_id, padre_id):
        nodos = []
        for o in sorted(hijos.get((cat_id, padre_id), []), key=lambda x: x.orden):
            nodos.append({"id": o.id, "codigo": o.codigo, "nombre": o.nombre,
                          "hijos": construir(cat_id, o.id)})
        return nodos

    salida = []
    for c in cats:
        if c.codigo in CATEGORIAS_OCULTAS:
            continue
        opciones = construir(c.id, None)
        if opciones:
            salida.append({
                "codigo": c.codigo, "nombre": c.nombre,
                "multivalor": c.es_multivalor,
                "automatica": c.detectable_automaticamente,
                "opciones": opciones,
            })
    return salida


# --- filtrado ---

def _hijos_por_padre(s: Session) -> dict:
    d: dict = {}
    for oid, padre in s.execute(select(Opcion.id, Opcion.id_padre)):
        d.setdefault(padre, []).append(oid)
    return d


def _con_descendientes(ids, hijos) -> set:
    out, pila = set(), list(ids)
    while pila:
        x = pila.pop()
        out.add(x)
        pila.extend(hijos.get(x, []))
    return out


def imagenes_filtradas(s: Session, opcion_ids: list[int]):
    """Conjunto de imagenes que cumplen el filtro, o None si no hay filtro.

    - Filtrar por un nodo padre incluye a sus descendientes (6.4).
    - Dentro de una categoria, varias opciones = OR. Entre categorias = AND.
    - Para categorias de valor unico se compara la etiqueta EFECTIVA (mayor
      precedencia: manual > carpeta > modelo > geometrico), de modo que una
      correccion manual mande sobre la automatica.
    """
    if not opcion_ids:
        return None

    info = {oid: (cat, multi) for oid, cat, multi in s.execute(
        select(Opcion.id, Categoria.id, Categoria.es_multivalor)
        .join(Categoria, Categoria.id == Opcion.categoria_id))}
    hijos = _hijos_por_padre(s)

    # seleccion expandida por categoria
    sel: dict = {}  # categoria_id -> {"multi":bool, "ops":set}
    for oid in opcion_ids:
        if oid not in info:
            continue
        cat, multi = info[oid]
        entry = sel.setdefault(cat, {"multi": multi, "ops": set()})
        entry["ops"] |= _con_descendientes([oid], hijos)

    if not sel:
        return None

    # filas relevantes: solo de las categorias filtradas
    filas = s.execute(
        select(ImagenOpcion.imagen_id, ImagenOpcion.categoria_id,
               ImagenOpcion.opcion_id, ImagenOpcion.origen)
        .where(ImagenOpcion.categoria_id.in_(sel.keys()))
    ).all()

    # imagen -> categoria -> lista de (opcion, precedencia)
    por_img: dict = {}
    for iid, cat, oid, origen in filas:
        por_img.setdefault(iid, {}).setdefault(cat, []).append((oid, PRECEDENCIA.get(origen, 0)))

    matching = set()
    for iid, cats in por_img.items():
        ok = True
        for cat, crit in sel.items():
            filas_cat = cats.get(cat)
            if not filas_cat:
                ok = False
                break
            if crit["multi"]:
                if not any(o in crit["ops"] for o, _ in filas_cat):
                    ok = False
                    break
            else:
                efectiva = max(filas_cat, key=lambda t: t[1])[0]
                if efectiva not in crit["ops"]:
                    ok = False
                    break
        if ok:
            matching.add(iid)
    return matching


# --- listado paginado ---

def _una_ubicacion(s: Session, imagen_id: int):
    return s.execute(
        select(Ubicacion.nombre_archivo, Ubicacion.estado)
        .where(Ubicacion.imagen_id == imagen_id).order_by(Ubicacion.id).limit(1)
    ).first()


def _etiquetas_resumen(s: Session, imagen_ids: list[int]) -> dict:
    if not imagen_ids:
        return {}
    filas = s.execute(
        select(ImagenOpcion.imagen_id, Categoria.codigo, Opcion.nombre, ImagenOpcion.origen)
        .join(Categoria, Categoria.id == ImagenOpcion.categoria_id)
        .join(Opcion, Opcion.id == ImagenOpcion.opcion_id)
        .where(ImagenOpcion.imagen_id.in_(imagen_ids),
               Categoria.codigo.in_(CATEGORIAS_RESUMEN))
    ).all()
    acc: dict = {}
    for iid, cat, nombre, origen in filas:
        p = PRECEDENCIA.get(origen, 0)
        d = acc.setdefault(iid, {})
        if cat not in d or p > d[cat][0]:
            d[cat] = (p, nombre)
    return {iid: {c: v[1] for c, v in cats.items()} for iid, cats in acc.items()}


def listar_colecciones(s: Session) -> list[dict]:
    filas = s.execute(
        select(Coleccion.id, Coleccion.nombre, func.count(ImagenColeccion.imagen_id))
        .outerjoin(ImagenColeccion, ImagenColeccion.coleccion_id == Coleccion.id)
        .group_by(Coleccion.id, Coleccion.nombre).order_by(Coleccion.nombre)
    ).all()
    return [{"id": i, "nombre": n, "n": c} for i, n, c in filas]


def colecciones_con_portada(s: Session) -> list[dict]:
    cols = listar_colecciones(s)
    for c in cols:
        c["portada"] = s.scalar(
            select(Miniatura.ruta)
            .join(ImagenColeccion, ImagenColeccion.imagen_id == Miniatura.imagen_id)
            .where(ImagenColeccion.coleccion_id == c["id"])
            .order_by(ImagenColeccion.orden).limit(1))
    return cols


def excluir(s: Session, imagen_id: int, excluida: bool = True) -> None:
    img = s.get(Imagen, imagen_id)
    if img:
        img.excluida = excluida
        s.commit()


def papelera(s: Session) -> list[dict]:
    filas = s.execute(
        select(Imagen.id, Miniatura.ruta)
        .outerjoin(Miniatura, Miniatura.imagen_id == Imagen.id)
        .where(Imagen.excluida.is_(True)).order_by(Imagen.id)
    ).all()
    items = []
    for iid, mini in filas:
        ubic = _una_ubicacion(s, iid)
        items.append({"id": iid, "miniatura": mini,
                      "nombre": ubic[0] if ubic else f"imagen {iid}"})
    return items


def colecciones_estado(s: Session, imagen_id: int) -> list[dict]:
    """Colecciones con un flag 'guardada' indicando si la imagen ya está en
    cada una. Las que ya la contienen salen primero (estilo Pinterest)."""
    cols = listar_colecciones(s)
    dentro = set(s.scalars(select(ImagenColeccion.coleccion_id)
                           .where(ImagenColeccion.imagen_id == imagen_id)))
    for c in cols:
        c["guardada"] = c["id"] in dentro
    cols.sort(key=lambda c: (not c["guardada"], c["nombre"].lower()))
    return cols


def borrar_coleccion(s: Session, coleccion_id: int) -> None:
    s.execute(delete(ImagenColeccion).where(ImagenColeccion.coleccion_id == coleccion_id))
    s.execute(delete(Coleccion).where(Coleccion.id == coleccion_id))
    s.commit()


def quitar_de_coleccion(s: Session, coleccion_id: int, imagen_id: int) -> None:
    s.execute(delete(ImagenColeccion).where(
        ImagenColeccion.coleccion_id == coleccion_id,
        ImagenColeccion.imagen_id == imagen_id))
    s.commit()


def listar_modelos(s: Session) -> list[dict]:
    filas = s.execute(
        select(Modelo.id, Modelo.nombre, func.count(ImagenModelo.imagen_id))
        .outerjoin(ImagenModelo, ImagenModelo.modelo_id == Modelo.id)
        .group_by(Modelo.id, Modelo.nombre).order_by(Modelo.nombre)
    ).all()
    return [{"id": i, "nombre": n, "n": c} for i, n, c in filas]


def guardar_en_coleccion(s: Session, imagen_id: int, coleccion_id: int | None = None,
                         nuevo_nombre: str | None = None) -> str:
    """Añade una imagen a una colección existente o a una nueva. Devuelve el
    nombre de la colección."""
    col = None
    if nuevo_nombre:
        nuevo_nombre = nuevo_nombre.strip()
        col = s.scalar(select(Coleccion).where(Coleccion.nombre == nuevo_nombre))
        if col is None:
            col = Coleccion(nombre=nuevo_nombre, tipo="estatica")
            s.add(col)
            s.flush()
    elif coleccion_id:
        col = s.get(Coleccion, coleccion_id)
    if col is None:
        raise ValueError("colección no válida")
    ya = s.get(ImagenColeccion, {"imagen_id": imagen_id, "coleccion_id": col.id})
    if not ya:
        maxo = s.scalar(select(func.max(ImagenColeccion.orden))
                        .where(ImagenColeccion.coleccion_id == col.id)) or 0
        s.add(ImagenColeccion(imagen_id=imagen_id, coleccion_id=col.id, orden=maxo + 1))
    s.commit()
    return col.nombre


def listar(s: Session, pagina: int = 1, por_pagina: int = 60,
           opcion_ids: list[int] | None = None, coleccion_id: int | None = None,
           modelo_id: int | None = None, seed: int | None = None) -> dict:
    pagina = max(1, pagina)

    conjuntos = []
    m = imagenes_filtradas(s, opcion_ids or [])
    if m is not None:
        conjuntos.append(m)
    if coleccion_id:
        conjuntos.append(set(s.scalars(select(ImagenColeccion.imagen_id)
                                       .where(ImagenColeccion.coleccion_id == coleccion_id))))
    if modelo_id:
        conjuntos.append(set(s.scalars(select(ImagenModelo.imagen_id)
                                       .where(ImagenModelo.modelo_id == modelo_id))))
    if conjuntos:
        ids_todos = list(set.intersection(*conjuntos))
    else:
        ids_todos = list(s.scalars(select(Imagen.id)))

    # quitar las excluidas (papelera)
    excl = set(s.scalars(select(Imagen.id).where(Imagen.excluida.is_(True))))
    if excl:
        ids_todos = [i for i in ids_todos if i not in excl]

    # orden: aleatorio estable con seed (para que "cargar mas" siga la misma
    # baraja), o por id si no hay seed
    if seed is not None:
        random.Random(seed).shuffle(ids_todos)
    else:
        ids_todos.sort()

    total = len(ids_todos)
    page_ids = ids_todos[(pagina - 1) * por_pagina: pagina * por_pagina]

    minis = dict(s.execute(
        select(Miniatura.imagen_id, Miniatura.ruta)
        .where(Miniatura.imagen_id.in_(page_ids))).all()) if page_ids else {}
    resumen = _etiquetas_resumen(s, page_ids)

    items = []
    for iid in page_ids:
        ubic = _una_ubicacion(s, iid)
        items.append({
            "id": iid,
            "miniatura": minis.get(iid),
            "nombre": ubic[0] if ubic else f"imagen {iid}",
            "disponible": (ubic[1] == "disponible") if ubic else False,
            "etiquetas": resumen.get(iid, {}),
        })

    qs = "".join(f"&op={o}" for o in (opcion_ids or []))
    if coleccion_id:
        qs += f"&coleccion={coleccion_id}"
    if modelo_id:
        qs += f"&modelo={modelo_id}"
    if seed is not None:
        qs += f"&seed={seed}"

    return {
        "items": items, "pagina": pagina, "por_pagina": por_pagina,
        "total": total, "hay_mas": pagina * por_pagina < total,
        "siguiente": pagina + 1, "filtro_qs": qs,
        "coleccion_id": coleccion_id, "modelo_id": modelo_id, "seed": seed,
    }
