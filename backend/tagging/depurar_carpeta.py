"""Modo de depuración de la detección (sin base de datos).

Recibe una carpeta de imágenes y genera, en una carpeta hermana `<nombre>_debug`,
por cada imagen: una copia con el esqueleto y los ángulos dibujados, y un `.md`
que explica **por qué** salió cada etiqueta, nombrando el umbral y el valor
usados (para saber qué mover en `reglas.py`).

Las medidas se cachean: cambiar un umbral en `reglas.py` y reejecutar es
instantáneo (no vuelve a pasar MediaPipe). Usa `--reanalizar` para rehacer la
detección (p. ej. si cambian las imágenes o la geometría de `medidas.py`).

Uso:
  python -m backend.tagging.depurar_carpeta "C:\\ruta\\a\\carpeta"
  python -m backend.tagging.depurar_carpeta "C:\\ruta" "C:\\otra\\salida"
  python -m backend.tagging.depurar_carpeta "C:\\ruta" --reanalizar
"""

import argparse
import csv
import json
import time
from pathlib import Path

import cv2

from backend.tagging import overlay as ov
from backend.tagging.medidas import calcular_medidas
from backend.pose.seleccion import elegir_figura_principal, visibilidad_por_zonas
from backend.tagging.reglas import evaluar
from backend.tagging.taxonomia_auto import CATEGORIAS_AUTO
from backend.tagging.taxonomia_manual import CATEGORIAS_MANUAL

EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def _mapas_nombres():
    """{cat_cod: nombre} y {(cat_cod, opt_cod): nombre} para el reporte."""
    cats, opts = {}, {}

    def _walk(cat_cod, opciones):
        for op in opciones:
            opts[(cat_cod, op[0])] = op[1]
            if len(op) > 2:
                _walk(cat_cod, op[2])

    for cod, nombre, _multi, opciones in CATEGORIAS_AUTO:
        cats[cod] = nombre
        _walk(cod, opciones)
    for cod, nombre, _multi, _niv, opciones in CATEGORIAS_MANUAL:
        cats[cod] = nombre
        _walk(cod, opciones)
    return cats, opts


ZONAS_CUERPO = ["cabeza", "torso", "brazos", "manos", "piernas", "pies"]


def _detectada(cat, etiquetas, revisiones, opts):
    """Etiqueta legible asignada a una categoría, 'revisión' si quedó en la cola,
    o '' si no se emitió (n/a)."""
    for c, o, _conf in etiquetas:
        if c == cat:
            return opts.get((c, o), o)
    for c, _motivo in revisiones:
        if c == cat:
            return "revisión"
    return ""


def _deteccion_completa(a):
    """('sí'/'no', zonas faltantes) según la visibilidad por zonas del cuerpo."""
    if not a.get("pose_detectada"):
        return "no", "sin detección de pose"
    zonas = a.get("visibilidad_zonas") or {}
    faltan = [z for z in ZONAS_CUERPO if (zonas.get(z) or 0) < 0.6]
    return ("no" if faltan else "sí"), (", ".join(faltan) if faltan else "")


def _analizar(archivo: Path, detector) -> dict | None:
    """Pasa MediaPipe y calcula medidas. Devuelve dict cacheable, o None si no
    se pudo leer la imagen."""
    img = cv2.imread(str(archivo))
    if img is None:
        return None
    alto, ancho = img.shape[:2]
    figuras_2d, figuras_3d = detector.detectar(archivo)
    if not figuras_2d:
        return {"landmarks_2d": None, "m": {"es_primer_plano": False, "torso_fiable": False},
                "a": {"pose_detectada": False, "num_figuras": 0,
                      "visibilidad_zonas": {}, "ancho": ancho, "alto": alto}}
    idx = elegir_figura_principal(figuras_2d)
    lm2d = figuras_2d[idx]
    lm3d = figuras_3d[idx] if idx < len(figuras_3d) else None
    m = calcular_medidas(lm2d, lm3d, ancho, alto)
    a = {"pose_detectada": True, "num_figuras": len(figuras_2d),
         "visibilidad_zonas": visibilidad_por_zonas(lm2d), "ancho": ancho, "alto": alto}
    return {"landmarks_2d": lm2d, "m": m, "a": a}


def _rotular(img, etiquetas, revisiones, opts):
    """Escribe sobre la imagen las etiquetas clave (postura, orientación,
    encuadre, escorzo) para poder verlas de un vistazo sin abrir el .md."""
    efect = {c: opts.get((c, o), o) for c, o, _ in etiquetas}
    en_rev = {c for c, _ in revisiones}
    lineas = []
    for cat, etq in (("postura", "Postura"), ("orientacion_corporal", "Orient"),
                     ("encuadre", "Encuadre"), ("angulo_camara", "Cámara")):
        if cat in efect:
            lineas.append(f"{etq}: {efect[cat]}")
        elif cat in en_rev:
            lineas.append(f"{etq}: (revisión)")
    if not lineas:
        return
    h, w = img.shape[:2]
    esc = max(w, h) / 1000.0
    fs = 0.85 * esc
    dy = int(34 * esc)
    x, y0 = int(12 * esc), int(38 * esc)
    for k, txt in enumerate(lineas):
        y = y0 + k * dy
        cv2.putText(img, txt, (x, y), cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0),
                    int(6 * esc), cv2.LINE_AA)           # borde negro
        cv2.putText(img, txt, (x, y), cv2.FONT_HERSHEY_SIMPLEX, fs, (80, 255, 120),
                    max(1, int(2 * esc)), cv2.LINE_AA)   # texto verde


def _reporte_md(nombre, etiquetas, revisiones, expl, m, a, cats, opts) -> str:
    L = [f"# {nombre}", ""]
    if not a.get("pose_detectada"):
        L += ["**Sin detección de pose** (MediaPipe no encontró figura).", ""]
        return "\n".join(L)

    L.append("## Etiquetas automáticas")
    for cat, opt, conf in etiquetas:
        L.append(f"- **{cats.get(cat, cat)}** = {opts.get((cat, opt), opt)}  _(conf {conf})_")
    if revisiones:
        L.append("")
        L.append("## En revisión (ambiguas)")
        for cat, motivo in revisiones:
            L.append(f"- {cats.get(cat, cat) if cat else '(general)'}: {motivo}")

    L += ["", "## Por qué (umbral y valor usados)"]
    for cat, razon in expl.items():
        L.append(f"- **{cats.get(cat, cat)}**: {razon}")

    ang = m.get("angulos") or {}
    sen = m.get("senales") or {}
    ori = m.get("orientacion") or {}
    L += ["", "## Medidas", "```"]
    L.append("Ángulos: " + ", ".join(f"{k}={v}" for k, v in ang.items() if v is not None))
    L.append(f"Torso: {sen.get('inclinacion_torso')}°  ·  disp_v {m.get('dispersion_vertical')}  ·  disp_h {m.get('dispersion_horizontal')}")
    L.append(f"Extensión: {m.get('extension')}  ·  compacidad {m.get('compacidad')}")
    L.append(f"Orientación: ratio_hombros {ori.get('ratio_hombros_torso')}, dx_hombros {ori.get('dx_hombros')}, nariz {ori.get('vis_nariz')}, orejas {ori.get('vis_oreja_izq')}/{ori.get('vis_oreja_der')}")
    L.append("Escorzo: " + ", ".join(f"{k}={v}" for k, v in (m.get('escorzo') or {}).items()))
    L.append("```")
    return "\n".join(L)


def depurar(entrada: str, salida: str = None, reanalizar: bool = False):
    entrada = Path(entrada).resolve()
    if not entrada.is_dir():
        raise SystemExit(f"No existe la carpeta: {entrada}")
    salida = Path(salida).resolve() if salida else entrada.parent / f"{entrada.name}_debug"
    salida.mkdir(parents=True, exist_ok=True)

    cache_path = salida / "_cache_medidas.json"
    cache = {}
    if cache_path.exists() and not reanalizar:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    cats, opts = _mapas_nombres()
    archivos = sorted(p for p in entrada.rglob("*")
                      if p.is_file() and p.suffix.lower() in EXTENSIONES)
    print(f"Imágenes: {len(archivos)}  →  {salida}")

    detector = None
    filas_eval = []
    n_ok = n_cache = n_error = 0
    t0 = time.perf_counter()
    for i, archivo in enumerate(archivos, 1):
        rel = archivo.relative_to(entrada).as_posix()
        datos = cache.get(rel)
        if datos is None:
            if detector is None:
                from backend.pose.landmarker import DetectorPose
                detector = DetectorPose()
            datos = _analizar(archivo, detector)
            if datos is None:
                n_error += 1
                continue
            cache[rel] = datos
        else:
            n_cache += 1

        m, a, lm2d = datos["m"], datos["a"], datos["landmarks_2d"]
        etiquetas, revisiones, expl = evaluar(m, a)

        completa, faltan = _deteccion_completa(a)
        filas_eval.append([
            rel,
            _detectada("postura", etiquetas, revisiones, opts),
            _detectada("orientacion_corporal", etiquetas, revisiones, opts),
            _detectada("encuadre", etiquetas, revisiones, opts),
            _detectada("angulo_camara", etiquetas, revisiones, opts),
            completa, faltan,
        ])

        # imagen anotada
        img = cv2.imread(str(archivo))
        if img is not None and lm2d:
            ov.dibujar(img, lm2d, m.get("angulos"))
        if img is not None:
            _rotular(img, etiquetas, revisiones, opts)
        destino_stem = f"{i:04d}_{archivo.stem}"
        if img is not None:
            cv2.imwrite(str(salida / f"{destino_stem}.jpg"), img)
        # reporte
        md = _reporte_md(archivo.name, etiquetas, revisiones, expl, m, a, cats, opts)
        (salida / f"{destino_stem}.md").write_text(md, encoding="utf-8")
        n_ok += 1
        if i % 20 == 0 or i == len(archivos):
            print(f"[{i}/{len(archivos)}]")

    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    csv_path = salida / "evaluacion.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as fcsv:
        w = csv.writer(fcsv)
        w.writerow(["archivo", "postura_detectada", "orientacion_detectada",
                    "encuadre_detectada", "camara_detectada",
                    "deteccion_completa", "zonas_faltantes"])
        w.writerows(filas_eval)
    print(f"CSV de evaluación: {csv_path}  ({len(filas_eval)} filas)")

    elapsed = time.perf_counter() - t0
    fuente = "caché" if n_cache else "MediaPipe"
    print(f"\nHecho. {n_ok} imágenes ({n_cache} desde caché) · {n_error} ilegibles.")
    if n_ok:
        print(f"Tiempo: {elapsed:.1f} s total · {elapsed / n_ok * 1000:.0f} ms/imagen "
              f"({n_ok / elapsed:.1f} img/s). Incluye dibujar y escribir los archivos "
              f"de depuración, así que es un techo respecto al indexado normal.")
    print(f"Reejecuta tras cambiar umbrales en reglas.py (usa la {fuente}); "
          f"--reanalizar para rehacer la detección.")


def main():
    p = argparse.ArgumentParser(description="Depuración de la detección (imagen + por qué)")
    p.add_argument("entrada")
    p.add_argument("salida", nargs="?", default=None)
    p.add_argument("--reanalizar", action="store_true")
    args = p.parse_args()
    depurar(args.entrada, args.salida, args.reanalizar)


if __name__ == "__main__":
    main()
