"""Fase 4: geometria derivada a partir de los landmarks crudos.

Funciones puras, sin base de datos ni MediaPipe, para poder testearlas
aisladas. Todo lo que no se puede calcular con fiabilidad queda en None,
nunca inventado (seccion 7.1). No pone etiquetas: eso es la fase 5. Aqui
solo se producen numeros.

Dos marcos de referencia (7.2):
- Marco de la imagen (pixeles): para la relacion con la vertical y las
  inclinaciones. Se corrige la deformacion de las coordenadas normalizadas
  multiplicando por el ancho y el alto reales.
- Marco 3D (world landmarks, metros): para los angulos articulares, que son
  invariantes al sistema de ejes.
"""

import math

import numpy as np

VERSION_REGLAS = "v1"
VIS_MIN = 0.5  # visibilidad minima para usar un landmark

# Indices de los 33 landmarks de MediaPipe Pose.
NARIZ = 0
OREJA_IZQ, OREJA_DER = 7, 8
HOMBRO_IZQ, HOMBRO_DER = 11, 12
CODO_IZQ, CODO_DER = 13, 14
MUNECA_IZQ, MUNECA_DER = 15, 16
CADERA_IZQ, CADERA_DER = 23, 24
RODILLA_IZQ, RODILLA_DER = 25, 26
TOBILLO_IZQ, TOBILLO_DER = 27, 28


# --- utilidades ---

def _arrays(lm2d, lm3d, ancho, alto):
    """Devuelve (P2 pixeles, P3 metros, V visibilidad)."""
    P2 = np.array([[p["x"] * ancho, p["y"] * alto] for p in lm2d], dtype=float)
    V = np.array([p.get("visibility", 0.0) for p in lm2d], dtype=float)
    P3 = None
    if lm3d:
        P3 = np.array([[p["x"], p["y"], p["z"]] for p in lm3d], dtype=float)
    return P2, P3, V


def _vis(V, *idx):
    return all(V[i] >= VIS_MIN for i in idx)


def _angulo(P, a, b, c):
    """Angulo en grados en el vertice b formado por a-b-c."""
    u = P[a] - P[b]
    v = P[c] - P[b]
    nu, nv = np.linalg.norm(u), np.linalg.norm(v)
    if nu == 0 or nv == 0:
        return None
    cos = np.clip(np.dot(u, v) / (nu * nv), -1.0, 1.0)
    return round(math.degrees(math.acos(cos)), 1)


def _inclinacion_vertical(P2, a, b):
    """Angulo en grados del vector a->b respecto de la vertical de la imagen
    (0 = totalmente vertical, hacia arriba)."""
    v = P2[b] - P2[a]
    n = np.linalg.norm(v)
    if n == 0:
        return None
    vertical = np.array([0.0, -1.0])  # arriba (y crece hacia abajo)
    cos = np.clip(np.dot(v, vertical) / n, -1.0, 1.0)
    return round(math.degrees(math.acos(cos)), 1)


def _tilt_con_signo(P2, izq, der):
    """Inclinacion de una linea (hombros o caderas) respecto de la
    horizontal, en [-90, 90]. Positivo = el lado izquierdo esta mas alto."""
    dx = P2[izq][0] - P2[der][0]
    dy = P2[izq][1] - P2[der][1]
    mag = math.degrees(math.atan2(abs(dy), abs(dx)))
    # y crece hacia abajo: izquierda mas alta => y_izq < y_der => dy < 0
    signo = 1.0 if dy < 0 else -1.0
    return round(signo * mag, 1)


def _dist(P, a, b):
    return float(np.linalg.norm(P[a] - P[b]))


# --- triaje (7.1) ---

def torso_fiable(V) -> bool:
    """Hay torso fiable si hombros y caderas son visibles: sin ellos no hay
    escala ni origen para el marco del cuerpo."""
    return _vis(V, HOMBRO_IZQ, HOMBRO_DER, CADERA_IZQ, CADERA_DER)


# --- medidas geometricas ---

def _angulos_articulares(P3, V):
    if P3 is None:
        return None
    defs = {
        "codo_izq": (HOMBRO_IZQ, CODO_IZQ, MUNECA_IZQ),
        "codo_der": (HOMBRO_DER, CODO_DER, MUNECA_DER),
        "rodilla_izq": (CADERA_IZQ, RODILLA_IZQ, TOBILLO_IZQ),
        "rodilla_der": (CADERA_DER, RODILLA_DER, TOBILLO_DER),
        "hombro_izq": (CODO_IZQ, HOMBRO_IZQ, CADERA_IZQ),
        "hombro_der": (CODO_DER, HOMBRO_DER, CADERA_DER),
        "cadera_izq": (HOMBRO_IZQ, CADERA_IZQ, RODILLA_IZQ),
        "cadera_der": (HOMBRO_DER, CADERA_DER, RODILLA_DER),
    }
    out = {}
    for nombre, (a, b, c) in defs.items():
        out[nombre] = _angulo(P3, a, b, c) if _vis(V, a, b, c) else None
    return out


def _senales_ordinales(P2, V):
    s = {}
    mid_sh = (P2[HOMBRO_IZQ] + P2[HOMBRO_DER]) / 2
    mid_hip = (P2[CADERA_IZQ] + P2[CADERA_DER]) / 2

    if _vis(V, HOMBRO_IZQ, HOMBRO_DER, CADERA_IZQ, CADERA_DER):
        # inclinacion de torso respecto de la vertical
        v = mid_sh - mid_hip
        n = np.linalg.norm(v)
        vertical = np.array([0.0, -1.0])
        s["inclinacion_torso"] = (
            round(math.degrees(math.acos(np.clip(np.dot(v, vertical) / n, -1, 1))), 1)
            if n else None
        )

    s["inclinacion_hombros"] = (
        _tilt_con_signo(P2, HOMBRO_IZQ, HOMBRO_DER)
        if _vis(V, HOMBRO_IZQ, HOMBRO_DER) else None
    )
    s["inclinacion_caderas"] = (
        _tilt_con_signo(P2, CADERA_IZQ, CADERA_DER)
        if _vis(V, CADERA_IZQ, CADERA_DER) else None
    )
    if s["inclinacion_hombros"] is not None and s["inclinacion_caderas"] is not None:
        s["contraposto"] = round(s["inclinacion_hombros"] - s["inclinacion_caderas"], 1)
    else:
        s["contraposto"] = None

    if _vis(V, MUNECA_IZQ, MUNECA_DER):
        # y menor = mas arriba
        s["mano_mas_alta"] = "izquierda" if P2[MUNECA_IZQ][1] < P2[MUNECA_DER][1] else "derecha"
    else:
        s["mano_mas_alta"] = None

    # manos sobre la cabeza: muñeca por encima de la nariz
    if _vis(V, NARIZ):
        n = 0
        for m in (MUNECA_IZQ, MUNECA_DER):
            if V[m] >= VIS_MIN and P2[m][1] < P2[NARIZ][1]:
                n += 1
        s["manos_sobre_cabeza"] = ["ninguna", "una", "ambas"][n]
    else:
        s["manos_sobre_cabeza"] = None

    # manos cerca del rostro: muñeca a menos de un ancho de cabeza de la nariz
    s["manos_cerca_rostro"] = _manos_cerca_rostro(P2, V)

    # piernas cruzadas: orden horizontal de tobillos invertido respecto de caderas
    if _vis(V, TOBILLO_IZQ, TOBILLO_DER, CADERA_IZQ, CADERA_DER):
        signo_tob = np.sign(P2[TOBILLO_IZQ][0] - P2[TOBILLO_DER][0])
        signo_cad = np.sign(P2[CADERA_IZQ][0] - P2[CADERA_DER][0])
        s["piernas_cruzadas"] = bool(signo_tob != 0 and signo_tob != signo_cad)
    else:
        s["piernas_cruzadas"] = None

    return s


def _ancho_cabeza(P2, V):
    if _vis(V, OREJA_IZQ, OREJA_DER):
        return _dist(P2, OREJA_IZQ, OREJA_DER)
    return None


def _manos_cerca_rostro(P2, V):
    if not _vis(V, NARIZ):
        return None
    ancho = _ancho_cabeza(P2, V)
    if not ancho:
        return None
    n = 0
    for m in (MUNECA_IZQ, MUNECA_DER):
        if V[m] >= VIS_MIN and np.linalg.norm(P2[m] - P2[NARIZ]) <= 1.5 * ancho:
            n += 1
    return ["ninguna", "una", "ambas"][n]


def _escorzo(P2, P3, V):
    """Ratio (proyectado_2d / torso_2d) / (real_3d / torso_3d) por miembro.
    Cercano a 1: sin escorzo. Menor que 1: el miembro se ve mas corto de lo
    que mide -> escorzado hacia/desde la camara (seccion 7.3)."""
    if P3 is None:
        return None
    torso2d = (_dist(P2, HOMBRO_IZQ, CADERA_IZQ) + _dist(P2, HOMBRO_DER, CADERA_DER)) / 2
    torso3d = (_dist(P3, HOMBRO_IZQ, CADERA_IZQ) + _dist(P3, HOMBRO_DER, CADERA_DER)) / 2
    if torso2d == 0 or torso3d == 0:
        return None
    miembros = {
        "brazo_izq": (HOMBRO_IZQ, CODO_IZQ, MUNECA_IZQ),
        "brazo_der": (HOMBRO_DER, CODO_DER, MUNECA_DER),
        "pierna_izq": (CADERA_IZQ, RODILLA_IZQ, TOBILLO_IZQ),
        "pierna_der": (CADERA_DER, RODILLA_DER, TOBILLO_DER),
    }
    out = {}
    for nombre, (a, b, c) in miembros.items():
        if not _vis(V, a, b, c):
            out[nombre] = None
            continue
        l2 = (_dist(P2, a, b) + _dist(P2, b, c)) / torso2d
        l3 = (_dist(P3, a, b) + _dist(P3, b, c)) / torso3d
        out[nombre] = round(l2 / l3, 3) if l3 else None
    return out


def _extension_dispersion(P2, V):
    """Extension/compacidad (base de dinamismo) y dispersion vertical y
    horizontal (deteccion de acostado, mas robusta que el angulo de cadera)."""
    mid_sh = (P2[HOMBRO_IZQ] + P2[HOMBRO_DER]) / 2
    mid_hip = (P2[CADERA_IZQ] + P2[CADERA_DER]) / 2
    torso = float(np.linalg.norm(mid_sh - mid_hip))
    if torso == 0:
        return None, None, None, None
    centro = (mid_sh + mid_hip) / 2

    extremos = [MUNECA_IZQ, MUNECA_DER, TOBILLO_IZQ, TOBILLO_DER]
    dists = [float(np.linalg.norm(P2[i] - centro)) / torso for i in extremos if V[i] >= VIS_MIN]
    extension = round(sum(dists) / len(dists), 3) if dists else None

    visibles = [i for i in range(len(P2)) if V[i] >= VIS_MIN]
    if len(visibles) >= 3:
        pts = P2[visibles]
        disp_v = round(float(np.std(pts[:, 1])) / torso, 3)
        disp_h = round(float(np.std(pts[:, 0])) / torso, 3)
    else:
        disp_v = disp_h = None
    return extension, disp_v, disp_h, torso


def _orientacion(P2, V, torso):
    """Señales crudas de orientacion corporal (7.4), sin interpretar."""
    o = {}
    if torso and _vis(V, HOMBRO_IZQ, HOMBRO_DER):
        o["ratio_hombros_torso"] = round(_dist(P2, HOMBRO_IZQ, HOMBRO_DER) / torso, 3)
    else:
        o["ratio_hombros_torso"] = None
    o["vis_nariz"] = round(float(V[NARIZ]), 3)
    o["vis_oreja_izq"] = round(float(V[OREJA_IZQ]), 3)
    o["vis_oreja_der"] = round(float(V[OREJA_DER]), 3)
    # Señal de espaldas: signo de la diferencia en X de los hombros (anatomicos).
    # Se invierte al girarse; se guarda cruda para que la regla la interprete.
    if _vis(V, HOMBRO_IZQ, HOMBRO_DER):
        o["dx_hombros"] = round(float(P2[HOMBRO_IZQ][0] - P2[HOMBRO_DER][0]), 2)
    else:
        o["dx_hombros"] = None
    # Ratio en 2D (solo landmarks visibles, sin eje z): largo del torso entre el
    # largo de las piernas. La pierna se mide POR SEGMENTOS (cadera->rodilla +
    # rodilla->tobillo), no en linea recta, para que la flexion de la rodilla no
    # acorte la medida: asi solo el escorzo por el angulo de camara mueve el
    # ratio. En un picado las piernas se ven mas cortas y este ratio sube; en
    # contrapicado baja. Base para el angulo de camara.
    piernas = []
    if _vis(V, CADERA_IZQ, RODILLA_IZQ, TOBILLO_IZQ):
        piernas.append(_dist(P2, CADERA_IZQ, RODILLA_IZQ) + _dist(P2, RODILLA_IZQ, TOBILLO_IZQ))
    if _vis(V, CADERA_DER, RODILLA_DER, TOBILLO_DER):
        piernas.append(_dist(P2, CADERA_DER, RODILLA_DER) + _dist(P2, RODILLA_DER, TOBILLO_DER))
    if torso and piernas:
        o["ratio_torso_piernas"] = round(torso / (sum(piernas) / len(piernas)), 3)
    else:
        o["ratio_torso_piernas"] = None
    return o


def calcular_medidas(lm2d, lm3d, ancho, alto) -> dict:
    """Punto de entrada. Devuelve un dict con las mismas claves que las
    columnas de MedidasPose. Si no hay torso fiable, marca primer plano y
    solo calcula manos cerca del rostro."""
    P2, P3, V = _arrays(lm2d, lm3d, ancho, alto)
    fiable = torso_fiable(V)

    base = {
        "version_reglas": VERSION_REGLAS,
        "torso_fiable": fiable,
        "es_primer_plano": not fiable,
        "angulos": None,
        "senales": None,
        "escorzo": None,
        "orientacion": None,
        "extension": None,
        "compacidad": None,
        "dispersion_vertical": None,
        "dispersion_horizontal": None,
    }

    if not fiable:
        # Primer plano: solo manos cerca del rostro, normalizado por cabeza.
        base["senales"] = {"manos_cerca_rostro": _manos_cerca_rostro(P2, V)}
        return base

    extension, disp_v, disp_h, torso = _extension_dispersion(P2, V)
    base["angulos"] = _angulos_articulares(P3, V)
    base["senales"] = _senales_ordinales(P2, V)
    base["escorzo"] = _escorzo(P2, P3, V)
    base["orientacion"] = _orientacion(P2, V, torso)
    base["extension"] = extension
    base["compacidad"] = round(1.0 / extension, 3) if extension else None
    base["dispersion_vertical"] = disp_v
    base["dispersion_horizontal"] = disp_h
    return base
