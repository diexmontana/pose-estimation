"""Logica pura del vector de similitud de pose (seccion 8).

Sin base de datos, para poder testearla. El vector es un conjunto curado de
angulos articulares, cada uno como (seno, coseno). La distancia se calcula
solo sobre las articulaciones fiables en ambas imagenes, normalizando por
cuantas se compararon, y se queda con la mejor de las dos orientaciones
(directa y espejo).
"""

import math

VERSION_VECTOR = "v1"

# Conjunto curado de angulos (misma escala, todos flexiones articulares).
# NO se mezclan otras medidas: alimentan las reglas, no la distancia.
ANGULOS = [
    "hombro_izq", "hombro_der",
    "codo_izq", "codo_der",
    "cadera_izq", "cadera_der",
    "rodilla_izq", "rodilla_der",
]
# Permutacion espejo: intercambia izquierda y derecha.
MIRROR = [
    "hombro_der", "hombro_izq",
    "codo_der", "codo_izq",
    "cadera_der", "cadera_izq",
    "rodilla_der", "rodilla_izq",
]
_IDX = {a: i for i, a in enumerate(ANGULOS)}
_PERM = [_IDX[a] for a in MIRROR]  # indice de angulo -> indice reflejado

DIM = len(ANGULOS) * 2  # seno y coseno por angulo


def construir(angulos: dict):
    """Devuelve (vector[16], vector_reflejado[16], mascara[8]) a partir del
    dict de angulos en grados. Angulos ausentes -> componentes 0 y mascara 0."""
    vector = [0.0] * DIM
    mascara = [0] * len(ANGULOS)
    for i, nombre in enumerate(ANGULOS):
        v = angulos.get(nombre) if angulos else None
        if v is None:
            continue
        rad = math.radians(v)
        vector[2 * i] = round(math.sin(rad), 6)
        vector[2 * i + 1] = round(math.cos(rad), 6)
        mascara[i] = 1
    reflejado = [0.0] * DIM
    for i, j in enumerate(_PERM):
        reflejado[2 * i] = vector[2 * j]
        reflejado[2 * i + 1] = vector[2 * j + 1]
    return vector, reflejado, mascara


def mascara_reflejada(mascara: list) -> list:
    return [mascara[j] for j in _PERM]


def _distancia(vec_q, mask_q, vec_s, mask_s):
    """Distancia media por articulacion comun. None si no hay ninguna comun."""
    suma = 0.0
    comunes = 0
    for i in range(len(ANGULOS)):
        if mask_q[i] and mask_s[i]:
            d0 = vec_q[2 * i] - vec_s[2 * i]
            d1 = vec_q[2 * i + 1] - vec_s[2 * i + 1]
            suma += d0 * d0 + d1 * d1
            comunes += 1
    if comunes == 0:
        return None
    return math.sqrt(suma / comunes)


def distancia_mejor(vec_q, mask_q, vec_s, refl_s, mask_s):
    """Mejor (menor) distancia entre la consulta y la imagen almacenada,
    considerando su version directa y su espejo."""
    d1 = _distancia(vec_q, mask_q, vec_s, mask_s)
    d2 = _distancia(vec_q, mask_q, refl_s, mascara_reflejada(mask_s))
    ds = [d for d in (d1, d2) if d is not None]
    return min(ds) if ds else None
