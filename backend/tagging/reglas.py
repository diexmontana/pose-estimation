"""Fase 5: reglas geometricas que convierten medidas en etiquetas.

Funciones puras (sin base de datos) para poder testearlas. Cada regla usa
umbrales explicitos y **bandas de incertidumbre**: si un valor cae en la zona
muerta entre dos clases, no se etiqueta y se manda a la cola de revision (6.8).
Los umbrales son provisionales y estan todos aqui centralizados para poder
calibrarlos con el conjunto de 200-300 imagenes (7.6).

`evaluar(m, a)` devuelve:
  etiquetas  -> lista de (categoria_cod, opcion_cod, confianza)
  revisiones -> lista de (categoria_cod|None, motivo)

`m` y `a` son dicts con las medidas y el analisis crudo de una imagen.
"""

VERSION_REGLAS = "v1"

U = {
    "vis": 0.6,                 # visibilidad minima para dar una zona por visible
    "encuadre_pies": 0.25,      # un pie en cuadro (aunque parcial) -> cuerpo entero
    "encuadre_piernas": 0.5,    # o las piernas en cuadro
    "img_cuadrada": 0.06,       # margen para orientacion de imagen (|r-1|)
    "escorzo_cortes": [0.65, 0.85],   # <0.65 pronunciado, 0.65-0.85 leve, >0.85 ninguno
    "escorzo_banda": 0.03,
    "escorzo_miembro": 0.80,    # un miembro por debajo de esto se marca escorzado
    "dinamismo_cortes": [0.95, 1.40],  # extension: estatica / moderada / dinamica
    "dinamismo_banda": 0.06,
    "rodilla_flexion": 150,     # rodilla por debajo = flexionada
    "rodilla_flexion_banda": 8,
    "cuclillas_rodilla": 70,    # ambas rodillas muy dobladas (flexion profunda)
    "acostado_factor": 1.3,     # disp_horizontal > disp_vertical * factor -> acostado
    "acostado_torso": 55,       # ademas el torso debe estar tumbado (no vertical)
    "cadera_abierta": 150,      # al menos una cadera abierta -> de pie / inclinado
    "cadera_sentado": 130,      # caderas flexionadas -> sentado
    "de_pie_rodilla": 150,      # rodilla casi recta (para arrodillado)
    "postura_torso_vertical": 40,  # de pie (<) vs inclinado (>=)
    "orient_ratio_frente": 0.56,   # hombros anchos -> plano frontal (frente/espaldas)
    "orient_ratio_perfil": 0.35,   # hombros muy estrechos -> perfil (de canto)
    "orient_banda": 0.04,          # zona muerta alrededor de los cortes de orientacion
    "brazo_extendido": 150,     # codo casi recto
    "hombro_abierto": 55,       # brazo separado del torso
    # Angulo de camara (solo de pie; ratio torso/piernas 2D con la pierna medida
    # por segmentos). Cortes calibrados con el modo depuracion: contrapicado ~0.44,
    # a nivel ~0.6, picado 1.0-1.7.
    "camara_cortes": [0.55, 0.9],  # <0.55 contrapicado / 0.55-0.9 a nivel / >0.9 picado
    "camara_banda": 0.05,
}


def _clasificar(valor, cortes, etiquetas, banda):
    """Devuelve una etiqueta, o None si el valor cae en la zona muerta (a
    menos de `banda` de un corte) -> ambiguo, va a revision."""
    if valor is None:
        return None
    for c in cortes:
        if abs(valor - c) < banda:
            return None
    idx = sum(1 for c in cortes if valor >= c)
    return etiquetas[idx]


def _min_validos(d, claves):
    vals = [d[k] for k in claves if d.get(k) is not None]
    return min(vals) if vals else None


def evaluar(m: dict, a: dict):
    """Devuelve (etiquetas, revisiones, explicaciones). `explicaciones` es un
    dict {categoria: motivo} con el nombre del umbral y los valores usados, para
    el modo de depuracion."""
    etiquetas = []
    revisiones = []
    expl = {}

    def add(cat, opt, conf, razon=None):
        if opt is not None:
            etiquetas.append((cat, opt, round(conf, 2)))
            if razon:
                expl[cat] = razon

    def revisar(cat, motivo="ambiguo", razon=None):
        revisiones.append((cat, motivo))
        if cat and razon:
            expl[cat] = f"[revisión] {razon}"

    ancho = a.get("ancho") or 1
    alto = a.get("alto") or 1

    # --- Orientacion de la imagen (independiente de la pose) ---
    r = round(ancho / alto, 3)
    ori_img = _clasificar(r, [1 - U["img_cuadrada"], 1 + U["img_cuadrada"]],
                          ["vertical", "cuadrada", "horizontal"], 0.01)
    add("orientacion_imagen", ori_img, 1.0, f"ancho/alto = {r} (img_cuadrada ±{U['img_cuadrada']})")

    # --- Numero de figuras (poco fiable: MediaPipe fusiona cuerpos) ---
    n = a.get("num_figuras") or 0
    if n >= 1:
        add("numero_figuras", "una" if n == 1 else ("dos" if n == 2 else "tres_o_mas"), 0.6,
            f"MediaPipe detectó {n} figura(s)")

    # Sin deteccion: nada geometrico que hacer
    if not a.get("pose_detectada"):
        revisar(None, "sin_deteccion")
        return etiquetas, revisiones, expl

    zonas = a.get("visibilidad_zonas") or {}
    visible = {z: (v is not None and v >= U["vis"]) for z, v in zonas.items()}

    # --- Partes visibles (multivalor) ---
    for z in ("cabeza", "torso", "brazos", "manos", "piernas", "pies"):
        if visible.get(z):
            add("partes_visibles", z, round(zonas[z], 2))

    # --- Manos en el rostro ---
    sen = m.get("senales") or {}
    mcr = sen.get("manos_cerca_rostro")
    if mcr is not None:
        add("manos_rostro", {"ninguna": "ninguna", "una": "una_mano", "ambas": "ambas_manos"}[mcr], 0.7,
            f"muñecas cerca del rostro: {mcr}")

    # --- Encuadre ---
    pies_lvl = round(zonas.get("pies") or 0, 2)
    piernas_lvl = round(zonas.get("piernas") or 0, 2)
    if m.get("es_primer_plano"):
        add("encuadre", "primer_plano", 0.8, "sin torso fiable (triaje) → primer plano")
    elif pies_lvl >= U["encuadre_pies"] or piernas_lvl >= U["encuadre_piernas"]:
        add("encuadre", "cuerpo_completo", 0.75,
            f"pies {pies_lvl} ≥ encuadre_pies({U['encuadre_pies']}) o "
            f"piernas {piernas_lvl} ≥ encuadre_piernas({U['encuadre_piernas']})")
    elif visible.get("torso"):
        add("encuadre", "medio_cuerpo", 0.65, "torso visible pero sin piernas/pies")
    elif visible.get("cabeza"):
        add("encuadre", "primer_plano", 0.6, "solo cabeza visible")
    else:
        revisar("encuadre", razon="ni pies, ni piernas, ni torso, ni cabeza visibles")

    # A partir de aqui, solo con torso fiable hay geometria completa
    if m.get("es_primer_plano") or not m.get("torso_fiable"):
        return etiquetas, revisiones, expl

    angs = m.get("angulos") or {}
    esc = m.get("escorzo") or {}
    ori = m.get("orientacion") or {}
    ti = sen.get("inclinacion_torso")
    dv, dh = m.get("dispersion_vertical"), m.get("dispersion_horizontal")

    # --- Escorzo (unico) + miembro escorzado (multivalor) ---
    esc_min = _min_validos(esc, ["brazo_izq", "brazo_der", "pierna_izq", "pierna_der"])
    if esc_min is not None:
        et = _clasificar(esc_min, U["escorzo_cortes"], ["pronunciado", "leve", "ninguno"], U["escorzo_banda"])
        razon_e = f"escorzo mínimo {esc_min} (cortes escorzo_cortes={U['escorzo_cortes']}, banda ±{U['escorzo_banda']})"
        if et is None:
            revisar("escorzo", razon=razon_e + " → cerca de un corte")
        else:
            add("escorzo", et, 0.65, razon_e)
    for miembro in ("brazo_izq", "brazo_der", "pierna_izq", "pierna_der"):
        v = esc.get(miembro)
        if v is not None and v < U["escorzo_miembro"]:
            add("miembro_escorzado", miembro, 0.6)

    # --- Dinamismo (desde extension) ---
    ext = m.get("extension")
    din = _clasificar(ext, U["dinamismo_cortes"], ["estatica", "moderada", "dinamica"], U["dinamismo_banda"])
    razon_d = f"extensión {ext} (cortes dinamismo_cortes={U['dinamismo_cortes']}, banda ±{U['dinamismo_banda']})"
    if ext is not None and din is None:
        revisar("dinamismo", razon=razon_d + " → cerca de un corte")
    add("dinamismo", din, 0.55, razon_d)

    # --- Orientacion corporal (ratio hombros + asimetria de orejas) ---
    oc, conf, razon = _orientacion_corporal(ori)
    if oc == "REVISAR":
        revisar("orientacion_corporal", razon=razon)
    else:
        add("orientacion_corporal", oc, conf, razon)

    # --- Postura ---
    post, conf, razon = _postura(angs, ti, dv, dh, sen.get("piernas_cruzadas"))
    if post == "REVISAR":
        revisar("postura", razon=razon)
    else:
        add("postura", post, conf, razon)

    # --- Piernas (multivalor) ---
    rod = {k: angs.get(k) for k in ("rodilla_izq", "rodilla_der")}
    flex = [k for k, v in rod.items() if v is not None and v < U["rodilla_flexion"] - U["rodilla_flexion_banda"]]
    ambiguas = [k for k, v in rod.items() if v is not None and abs(v - U["rodilla_flexion"]) < U["rodilla_flexion_banda"]]
    if len(flex) == 2:
        add("piernas", "ambas_flexionadas", 0.6)
    elif len(flex) == 1 and not ambiguas:
        add("piernas", "una_flexionada", 0.55)
    elif ambiguas:
        revisar("piernas")
    if sen.get("piernas_cruzadas"):
        # fragil de espaldas: solo si la orientacion no es de espaldas
        if oc in ("de_espaldas", "tres_cuartos_espaldas", "REVISAR"):
            revisar("piernas")
        else:
            add("piernas", "cruzadas", 0.45)

    # --- Brazos (multivalor) ---
    if sen.get("manos_sobre_cabeza") in ("una", "ambas"):
        add("brazos", "sobre_la_cabeza", 0.7)
    codos = [angs.get("codo_izq"), angs.get("codo_der")]
    hombros = [angs.get("hombro_izq"), angs.get("hombro_der")]
    if all(c is not None and c > U["brazo_extendido"] for c in codos) and \
       any(h is not None and h > U["hombro_abierto"] for h in hombros):
        add("brazos", "extendidos", 0.55)

    # --- Angulo de camara (pista de baja confianza) ---
    # Solo de pie (sentado la geometria torso/piernas no aplica). La pierna se
    # mide por segmentos (ver medidas._orientacion), asi que la flexion de la
    # rodilla no confunde: solo el escorzo por el angulo de camara mueve el ratio,
    # y ya no hace falta exigir piernas rectas. Usa solo landmarks 2D visibles.
    ratio_tp = ori.get("ratio_torso_piernas")
    if post == "de_pie" and ratio_tp is not None:
        ac = _clasificar(ratio_tp, U["camara_cortes"],
                         ["contrapicado", "a_nivel", "picado"], U["camara_banda"])
        razon_c = (f"de pie; torso/piernas 2D (pierna por segmentos) = {ratio_tp} "
                   f"(cortes camara_cortes={U['camara_cortes']}, banda ±{U['camara_banda']})")
        if ac is None:
            revisar("angulo_camara", razon=razon_c + " → cerca de un corte")
        else:
            add("angulo_camara", ac, 0.4, razon_c)

    # Torsion: pendiente de una medida de rotacion transversal propia; no se
    # etiqueta automaticamente todavia (ver informe tecnico).

    return etiquetas, revisiones, expl


def _orientacion_corporal(ori: dict):
    """Orientación corporal a partir del ancho de hombros y el orden de los
    hombros en X.

    El `ratio_hombros_torso` (ancho de hombros / largo del torso en 2D) mide
    cuánto está "de canto" la figura: muy bajo en perfil, medio en tres cuartos
    y alto de frente o de espaldas. La nariz y las orejas de MediaPipe NO son
    fiables aquí (dan visibilidad ~1.0 incluso de espaldas), así que no se usan.
    Para separar frente de espaldas se usa el signo de `dx_hombros`: MediaPipe
    etiqueta los hombros por anatomía, de modo que su orden en X se invierte al
    darse la vuelta (dx > 0 de frente, dx < 0 de espaldas)."""
    ratio = ori.get("ratio_hombros_torso")
    dx = ori.get("dx_hombros")
    if ratio is None:
        return "REVISAR", 0.0, "falta el ratio de hombros para la orientación"

    perfil_c = U["orient_ratio_perfil"]
    frente_c = U["orient_ratio_frente"]
    banda = U["orient_banda"]

    # Zona muerta alrededor de un corte -> ambiguo, a revisión.
    for c in (perfil_c, frente_c):
        if abs(ratio - c) < banda:
            return "REVISAR", 0.0, (f"ratio_hombros {ratio} cerca del corte {c} "
                                    f"(orient_banda ±{banda})")

    # De canto: perfil (izquierdo/derecho se deja para más adelante).
    if ratio < perfil_c:
        return "perfil", 0.6, (f"ratio_hombros {ratio} < orient_ratio_perfil({perfil_c}): "
                               f"de canto (perfil)")

    de_frente = dx is None or dx >= 0
    señal_dx = f"dx_hombros {dx}" if dx is not None else "dx_hombros n/d → se asume de frente"

    # Plano frontal: de frente o de espaldas según el orden de hombros.
    if ratio >= frente_c:
        if de_frente:
            return "de_frente", 0.7, (f"ratio_hombros {ratio} ≥ orient_ratio_frente({frente_c}) "
                                      f"y orden de hombros frontal ({señal_dx})")
        return "de_espaldas", 0.6, (f"ratio_hombros {ratio} ≥ orient_ratio_frente({frente_c}) "
                                    f"y orden de hombros invertido ({señal_dx})")

    # Zona media: tres cuartos, con su sub-dirección frente/espaldas.
    if de_frente:
        return "tres_cuartos", 0.5, (f"ratio_hombros {ratio} entre orient_ratio_perfil({perfil_c}) "
                                     f"y orient_ratio_frente({frente_c}); orden de hombros frontal ({señal_dx})")
    return "tres_cuartos_espaldas", 0.5, (f"ratio_hombros {ratio} entre orient_ratio_perfil({perfil_c}) "
                                          f"y orient_ratio_frente({frente_c}); orden de hombros invertido ({señal_dx})")


def _postura(angs: dict, ti, dv, dh, cruzadas=None):
    """La cadera es la señal principal: abierta (~170) = de pie; flexionada
    (~90) = sentado. Las rodillas por si solas no distinguen (una figura de
    pie puede tener las rodillas algo dobladas)."""
    caderas = [angs.get("cadera_izq"), angs.get("cadera_der")]
    cad = [c for c in caderas if c is not None]
    rodillas = [angs.get("rodilla_izq"), angs.get("rodilla_der")]
    rod = [r for r in rodillas if r is not None]

    # acostado: torso tumbado Y mas ancho que alto (asi no confunde una pose
    # de accion ancha, que tiene el torso vertical)
    if (ti is not None and dv is not None and dh is not None
            and ti > U["acostado_torso"] and dh > dv * U["acostado_factor"]):
        return "acostado", 0.6, (f"torso {ti}° > acostado_torso({U['acostado_torso']}) y "
                                 f"disp_h {dh} > disp_v {dv}×acostado_factor({U['acostado_factor']})")

    if not cad and not rod:
        return "REVISAR", 0.0, "sin caderas ni rodillas fiables"

    cad_max = max(cad) if cad else None  # la cadera mas abierta
    rod_bajas = len(rod) == 2 and max(rod) <= U["cuclillas_rodilla"]

    # cuclillas: ambas rodillas muy dobladas (≤ 70°), pies NO cruzados y cadera
    # no abierta
    if rod_bajas and not cruzadas and (cad_max is None or cad_max < U["cadera_abierta"]):
        return "cuclillas", 0.6, (f"ambas rodillas {rodillas} ≤ cuclillas_rodilla({U['cuclillas_rodilla']}), "
                                  f"pies no cruzados y cadera no abierta (cadera_max {cad_max})")

    if cad_max is not None and cad_max >= U["cadera_abierta"]:
        margen = round(cad_max - U["cadera_abierta"], 1)
        if ti is None or ti < U["postura_torso_vertical"]:
            return "de_pie", 0.7, (f"cadera_max {cad_max}° ≥ cadera_abierta({U['cadera_abierta']}) "
                                   f"[+{margen}° sobre el corte] y torso {ti}° < "
                                   f"postura_torso_vertical({U['postura_torso_vertical']})")
        return "inclinado", 0.55, (f"cadera_max {cad_max}° ≥ cadera_abierta({U['cadera_abierta']}) "
                                   f"pero torso {ti}° ≥ postura_torso_vertical({U['postura_torso_vertical']})")

    if (len(rod) == 2 and min(rod) < U["cuclillas_rodilla"]
            and max(rod) >= U["de_pie_rodilla"]):
        return "arrodillado", 0.5, (f"una rodilla {min(rod)}° < cuclillas_rodilla({U['cuclillas_rodilla']}) "
                                    f"y la otra {max(rod)}° ≥ de_pie_rodilla({U['de_pie_rodilla']})")

    if cad_max is not None and cad_max <= U["cadera_sentado"]:
        falta = round(U["cadera_abierta"] - cad_max, 1)
        return "sentado", 0.55, (f"cadera_max {cad_max}° ≤ cadera_sentado({U['cadera_sentado']}) "
                                 f"[le faltan {falta}° para llegar a 'de pie']")

    return "REVISAR", 0.0, (f"cadera_max {cad_max}° en zona ambigua "
                            f"(entre cadera_sentado({U['cadera_sentado']}) y cadera_abierta({U['cadera_abierta']}))")
