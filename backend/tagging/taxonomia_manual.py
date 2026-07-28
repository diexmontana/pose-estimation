"""Sembrado de la taxonomia manual (secciones 9.2 a 9.4).

Categorias que NO se detectan por geometria: se asignan a mano a nivel de
modelo, carpeta o imagen. Incluye ejes de vestuario y props **en arbol**
(id_padre): filtrar por un nodo padre incluye a sus descendientes (6.4).

Sembrar es idempotente.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Categoria, Opcion

# Cada opcion puede ser (codigo, nombre) o (codigo, nombre, [hijos...]).
# Categoria: (codigo, nombre, es_multivalor, nivel_sugerido, [opciones]).
CATEGORIAS_MANUAL = [
    # --- 9.2 Modelo ---
    ("rasgos_tono", "Rasgos", False, "modelo", [
        ("negra", "negra"), ("asiatica", "asiatica"), ("latina", "latina"),
        ("europea", "europea"), ("exotica", "exotica"), ("indigena", "indigena"),
    ]),
    ("contraposto", "Contraposto", False, "imagen", [
        ("con_contraposto", "con contraposto"),
    ]),
    ("color_cabello", "Color de cabello", False, "modelo", [
        ("rubia", "rubia"), ("castana", "castana"), ("morena", "morena"),
        ("pelirroja", "pelirroja"), ("otro", "otro"),
    ]),
    ("tipo_cuerpo", "Tipo de cuerpo", False, "modelo", [
        ("delgada", "delgada"), ("curvy", "curvy"), ("atletica", "atletica"),
    ]),
    ("altura", "Altura", False, "modelo", [
        ("petite", "petite"), ("media", "media"), ("alta", "alta"),
    ]),
    ("edad", "Edad", False, "modelo", [
        ("bebe", "bebe"), ("nino", "nino"), ("adolescente", "adolescente"),
        ("adulto", "adulto"), ("adulto_mayor", "adulto mayor"),
    ]),
    ("rasgos_destacados", "Rasgos destacados", True, "modelo", [
        ("dientes", "dientes"), ("lengua", "lengua"),
        ("thigh_gap", "thigh gap"), ("hip_dips", "hip dips"),
    ]),
    ("sexo", "Sexo", False, "modelo", [
        ("hombre", "hombre"), ("mujer", "mujer"),
    ]),
    # --- 9.3 Sesion (carpeta) ---
    ("vestimenta", "Vestimenta", False, "carpeta", [
        ("vestido", "vestido"), ("ropa_interior", "ropa interior"), ("desnudo", "desnudo"),
    ]),
    ("composicion", "Composicion", False, "carpeta", [
        ("dos_hombres", "dos hombres"), ("dos_mujeres", "dos mujeres"),
        ("hombre_y_mujer", "hombre y mujer"),
    ]),
    ("angulo_camara", "Angulo de camara", False, "carpeta", [
        ("a_nivel", "a nivel"), ("picado", "picado"),
        ("contrapicado", "contrapicado"), ("cenital", "cenital"),
    ]),
    ("estilo", "Estilo", False, "carpeta", [
        ("gotico", "gotico"), ("andino", "andino"),
        ("elegante_vintage", "elegante o vintage"), ("cosplay", "cosplay"),
    ]),
    ("grado_gotico", "Grado gotico", False, "carpeta", [
        ("goth_coded", "goth coded"), ("goth_influenced", "goth influenced"),
        ("goth_aesthetic", "goth aesthetic"),
    ]),
    ("accion", "Accion", True, "carpeta", [
        ("patada", "patada"), ("golpe", "golpe"), ("guardia", "guardia"),
        ("salto", "salto"), ("carrera", "carrera"), ("danza", "danza"),
        ("modelaje", "modelaje"), ("reposo", "reposo"),
    ]),
    ("iluminacion", "Iluminacion", False, "carpeta", [
        ("difusa", "difusa"), ("lateral", "lateral"), ("contraluz", "contraluz"),
        ("clave_alta", "clave alta"), ("clave_baja", "clave baja"),
    ]),
    ("peinado", "Peinado", False, "carpeta", [
        ("suelto", "suelto"), ("cola_caballo", "cola de caballo"),
        ("media_cola", "media cola"), ("coletas", "coletas"),
        ("mono", "mono"), ("medio_mono", "medio mono"),
    ]),
    ("maquillaje", "Maquillaje", False, "carpeta", [
        ("natural", "natural"), ("marcado", "marcado"), ("corrido", "corrido"),
    ]),
    ("estado", "Estado", False, "carpeta", [
        ("embarazada", "embarazada"),
    ]),
    # --- 9.4 Vestuario (ejes que se combinan) ---
    ("prenda", "Prenda", True, "carpeta", [
        ("ropa_interior_g", "Ropa interior", [
            ("sujetadores", "Sujetadores", [
                ("sujetador", "sujetador"), ("copa_abierta_p", "copa abierta"),
            ]),
            ("bragas", "Bragas", [("panty", "panty"), ("tanga", "tanga")]),
            ("medias", "Medias", [
                ("pantimedias", "pantimedias"), ("medias_muslo", "medias hasta el muslo"),
                ("medias_clasicas", "medias clasicas"),
            ]),
            ("calcetines_mallas", "Calcetines y mallas", [
                ("calcetas_muslo", "calcetas hasta el muslo"), ("calcetas_altas", "calcetas altas"),
                ("calcetas", "calcetas"), ("mallas", "mallas"),
            ]),
            ("ligueros", "Ligueros", [
                ("liguero_cintura", "liguero de cintura"), ("liga_muslo", "liga de muslo"),
            ]),
        ]),
        ("bodies_conjuntos", "Bodies y conjuntos", [
            ("body", "body"), ("catsuit", "catsuit"), ("conjunto_completo", "conjunto completo"),
        ]),
        ("corseteria_tops", "Corseteria y tops", [
            ("corse", "corse"), ("bustier", "bustier"), ("babydoll", "babydoll"),
            ("chemise", "chemise"), ("top", "top"),
        ]),
        ("vestidos", "Vestidos", [
            ("vestido_ajustado", "vestido ajustado"), ("mini_vestido", "mini vestido"),
        ]),
        ("calzado", "Calzado"),
        ("armaduras_cosplay", "Armaduras y cosplay"),
    ]),
    ("material_acabado", "Material y acabado", True, "imagen", [
        ("transparente", "transparente"), ("semitransparente", "semitransparente"),
        ("encaje", "encaje"), ("malla", "malla"), ("red", "red"), ("opaco", "opaco"),
    ]),
    ("mangas", "Mangas", False, "imagen", [
        ("sin_mangas", "sin mangas"), ("manga_corta", "manga corta"), ("manga_larga", "manga larga"),
    ]),
    ("corte_detalle", "Corte y detalle", True, "imagen", [
        ("copa_abierta", "copa abierta"), ("una_pierna", "una pierna"), ("con_ligas", "con ligas"),
    ]),
    ("props", "Props", True, "imagen", [
        ("armas", "Armas", [("espada", "espada"), ("otras_armas", "otras")]),
        ("libros", "libros"), ("camaras", "camaras"), ("instrumentos", "instrumentos"),
    ]),
    ("accesorios", "Accesorios", True, "imagen", [
        ("lazos", "lazos"), ("arneses", "arneses"), ("tobilleras", "tobilleras"),
        ("corbata_cinta", "corbata o cinta"), ("accesorios_cabello", "accesorios de cabello"),
    ]),
]


def _sembrar_opciones(sesion, categoria_id, opciones, id_padre=None):
    for orden, op in enumerate(opciones):
        codigo, nombre = op[0], op[1]
        hijos = op[2] if len(op) > 2 else []
        fila = sesion.scalar(
            select(Opcion).where(Opcion.categoria_id == categoria_id, Opcion.codigo == codigo)
        )
        if fila is None:
            fila = Opcion(categoria_id=categoria_id, id_padre=id_padre,
                          codigo=codigo, nombre=nombre, orden=orden)
            sesion.add(fila)
            sesion.flush()
        if hijos:
            _sembrar_opciones(sesion, categoria_id, hijos, id_padre=fila.id)


def sembrar_manual(sesion: Session, orden_base: int = 100) -> None:
    for i, (cod, nombre, multi, nivel, opciones) in enumerate(CATEGORIAS_MANUAL):
        cat = sesion.scalar(select(Categoria).where(Categoria.codigo == cod))
        if cat is None:
            cat = Categoria(codigo=cod, nombre=nombre, es_multivalor=multi,
                            detectable_automaticamente=False, nivel_sugerido=nivel,
                            orden=orden_base + i)
            sesion.add(cat)
            sesion.flush()
        _sembrar_opciones(sesion, cat.id, opciones)
    sesion.commit()
