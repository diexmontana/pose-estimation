"""Definicion y sembrado de las categorias automaticas (seccion 9.1).

Solo las que el sistema puede detectar por geometria. El arbol manual rico
(9.2 a 9.5) se agrega en la fase 6. Sembrar es idempotente.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Categoria, Opcion

# (codigo, nombre, es_multivalor, [(opcion_codigo, opcion_nombre), ...])
CATEGORIAS_AUTO = [
    ("encuadre", "Encuadre", False, [
        ("cuerpo_completo", "cuerpo completo"),
        ("plano_americano", "plano americano"),
        ("medio_cuerpo", "plano medio"),
        ("primer_plano", "primer plano"),
        ("detalle", "plano de detalle"),
    ]),
    ("postura", "Postura", False, [
        ("de_pie", "de pie"), ("sentado", "sentado"), ("acostado", "acostado"),
        ("cuclillas", "en cuclillas"), ("arrodillado", "arrodillado"),
        ("inclinado", "inclinado"), ("en_el_aire", "en el aire"),
    ]),
    ("orientacion_corporal", "Orientacion corporal", False, [
        ("de_frente", "de frente"), ("tres_cuartos", "tres cuartos"),
        ("perfil", "perfil"), ("tres_cuartos_espaldas", "tres cuartos de espaldas"),
        ("de_espaldas", "de espaldas"),
    ]),
    ("orientacion_imagen", "Orientacion de la imagen", False, [
        ("vertical", "vertical"), ("horizontal", "horizontal"), ("cuadrada", "cuadrada"),
    ]),
    ("partes_visibles", "Partes visibles", True, [
        ("cabeza", "cabeza"), ("torso", "torso"), ("brazos", "brazos"),
        ("manos", "manos"), ("piernas", "piernas"), ("pies", "pies"),
    ]),
    ("manos_rostro", "Manos en el rostro", False, [
        ("ninguna", "ninguna"), ("una_mano", "una mano"), ("ambas_manos", "ambas manos"),
    ]),
    ("brazos", "Pose de brazos", True, [
        ("cruzados", "cruzados"), ("en_jarras", "en jarras"),
        ("sobre_la_cabeza", "sobre la cabeza"), ("extendidos", "extendidos"),
        ("tras_la_espalda", "tras la espalda"),
    ]),
    ("piernas", "Pose de pierna", True, [
        ("juntas", "juntas"), ("separadas", "separadas"), ("cruzadas", "cruzadas"),
        ("una_flexionada", "una flexionada"), ("ambas_flexionadas", "ambas flexionadas"),
        ("una_levantada", "una pierna levantada"),
    ]),
    ("torsion", "Torsion", False, [
        ("sin_torsion", "sin torsion"), ("leve", "leve"), ("marcada", "marcada"),
    ]),
    ("dinamismo", "Dinamismo", False, [
        ("estatica", "estatica"), ("moderada", "moderada"), ("dinamica", "dinamica"),
    ]),
    ("escorzo", "Nivel de escorzo", False, [
        ("ninguno", "ninguno"), ("leve", "leve"), ("pronunciado", "pronunciado"),
    ]),
    ("miembro_escorzado", "Miembro escorzado", True, [
        ("brazo_izq", "brazo izquierdo"), ("brazo_der", "brazo derecho"),
        ("pierna_izq", "pierna izquierda"), ("pierna_der", "pierna derecha"),
        ("mayoria_cuerpo", "mayoria del cuerpo"),
    ]),
    ("numero_figuras", "Numero de figuras", False, [
        ("una", "una"), ("dos", "dos"), ("tres_o_mas", "tres o mas"),
    ]),
]


def sembrar(sesion: Session) -> None:
    for orden_cat, (cod, nombre, multi, opciones) in enumerate(CATEGORIAS_AUTO):
        cat = sesion.scalar(select(Categoria).where(Categoria.codigo == cod))
        if cat is None:
            cat = Categoria(
                codigo=cod, nombre=nombre, es_multivalor=multi,
                detectable_automaticamente=True, nivel_sugerido="imagen", orden=orden_cat,
            )
            sesion.add(cat)
            sesion.flush()
        for orden_op, (ocod, onom) in enumerate(opciones):
            existe = sesion.scalar(
                select(Opcion).where(Opcion.categoria_id == cat.id, Opcion.codigo == ocod)
            )
            if existe is None:
                sesion.add(Opcion(categoria_id=cat.id, codigo=ocod, nombre=onom, orden=orden_op))
    sesion.commit()


def mapa_opciones(sesion: Session) -> dict[tuple[str, str], tuple[int, int]]:
    """Devuelve {(categoria_codigo, opcion_codigo): (categoria_id, opcion_id)}."""
    filas = sesion.execute(
        select(Categoria.codigo, Categoria.id, Opcion.codigo, Opcion.id)
        .join(Opcion, Opcion.categoria_id == Categoria.id)
    ).all()
    return {(cc, oc): (cid, oid) for cc, cid, oc, oid in filas}
