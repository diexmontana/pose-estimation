"""Modo de depuracion visual (apoyo a la calibracion, seccion 7.6).

Genera una copia de cada imagen con el esqueleto dibujado y un panel de
las medidas detectadas, en una carpeta aparte. No toca los originales.
Sirve para comparar imagen a imagen que las reglas y umbrales tengan
sentido antes de convertir los numeros en etiquetas (fase 5).

Uso:
  python -m backend.tagging.overlay
  python -m backend.tagging.overlay --limite 10
  python -m backend.tagging.overlay --id 22
  python -m backend.tagging.overlay --salida "C:\\otra\\carpeta"
"""

import argparse
from pathlib import Path

import cv2
from sqlalchemy import select

from backend.db.models import AnalisisPose, Imagen, MedidasPose, Raiz, Ubicacion
from backend.db.session import SessionLocal

SALIDA_DEFECTO = Path(__file__).resolve().parents[2] / "data" / "debug"

# Conexiones del esqueleto (subconjunto legible de las de MediaPipe Pose).
CONEXIONES = [
    (11, 12), (11, 23), (12, 24), (23, 24),          # torso
    (11, 13), (13, 15), (12, 14), (14, 16),          # brazos
    (23, 25), (25, 27), (24, 26), (26, 28),          # piernas
    (27, 29), (29, 31), (27, 31), (28, 30), (30, 32), (28, 32),  # pies
    (0, 7), (0, 8),                                   # cabeza
]
# Articulaciones donde se rotula el angulo, con su clave en 'angulos'.
ARTICULACIONES = {
    13: "codo_izq", 14: "codo_der",
    25: "rodilla_izq", 26: "rodilla_der",
    11: "hombro_izq", 12: "hombro_der",
    23: "cadera_izq", 24: "cadera_der",
}

VERDE = (0, 220, 0)
ROJO = (0, 0, 255)
AMARILLO = (0, 220, 220)
VIS_MIN = 0.5


def _pt(lm, i, w, h):
    return int(lm[i]["x"] * w), int(lm[i]["y"] * h)


def dibujar(img, lm2d, angulos):
    """Dibuja esqueleto y angulos sobre la imagen (BGR, se modifica in situ)."""
    h, w = img.shape[:2]
    escala = max(w, h) / 1000.0
    r = max(2, int(4 * escala))
    grosor = max(1, int(2 * escala))

    for a, b in CONEXIONES:
        if a < len(lm2d) and b < len(lm2d):
            if lm2d[a].get("visibility", 0) >= VIS_MIN and lm2d[b].get("visibility", 0) >= VIS_MIN:
                cv2.line(img, _pt(lm2d, a, w, h), _pt(lm2d, b, w, h), VERDE, grosor)

    for i, p in enumerate(lm2d):
        vis = p.get("visibility", 0)
        color = VERDE if vis >= VIS_MIN else ROJO
        cv2.circle(img, _pt(lm2d, i, w, h), r, color, -1)

    if angulos:
        for i, clave in ARTICULACIONES.items():
            val = angulos.get(clave)
            if val is None or lm2d[i].get("visibility", 0) < VIS_MIN:
                continue
            x, y = _pt(lm2d, i, w, h)
            cv2.putText(img, f"{val:.0f}", (x + r + 2, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5 * escala, AMARILLO, grosor, cv2.LINE_AA)
    return img


def _lineas_panel(imagen, analisis, medidas) -> list[str]:
    lineas = [
        f"figs={analisis.num_figuras} principal={analisis.figura_principal}",
    ]
    if medidas is None:
        lineas.append("sin medidas")
        return lineas
    if medidas.es_primer_plano:
        mcr = (medidas.senales or {}).get("manos_cerca_rostro")
        lineas.append("PRIMER PLANO")
        lineas.append(f"manos_rostro={mcr}")
        return lineas
    sen = medidas.senales or {}
    esc = medidas.escorzo or {}
    lineas.append(f"ext={medidas.extension} comp={medidas.compacidad}")
    lineas.append(f"disp v={medidas.dispersion_vertical} h={medidas.dispersion_horizontal}")
    lineas.append(f"contra={sen.get('contraposto')} incl_torso={sen.get('inclinacion_torso')}")
    lineas.append(f"manos_arriba={sen.get('manos_sobre_cabeza')} cruzadas={sen.get('piernas_cruzadas')}")
    esc_txt = " ".join(f"{k[:2]}{k[-3:]}={v}" for k, v in esc.items())
    lineas.append(f"escorzo {esc_txt}")
    return lineas


def _panel(img, lineas):
    h, w = img.shape[:2]
    escala = max(w, h) / 1000.0
    fs = 0.5 * escala
    dy = int(22 * escala)
    alto_panel = dy * (len(lineas) + 1)
    ancho_panel = min(w, int(520 * escala))
    sub = img[0:alto_panel, 0:ancho_panel].copy()
    cv2.rectangle(sub, (0, 0), (ancho_panel, alto_panel), (0, 0, 0), -1)
    cv2.addWeighted(sub, 0.55, img[0:alto_panel, 0:ancho_panel], 0.45, 0,
                    img[0:alto_panel, 0:ancho_panel])
    y = dy
    for ln in lineas:
        cv2.putText(img, ln, (int(8 * escala), y), cv2.FONT_HERSHEY_SIMPLEX,
                    fs, (255, 255, 255), max(1, int(escala)), cv2.LINE_AA)
        y += dy


def ruta_imagen(sesion, imagen_id):
    fila = sesion.execute(
        select(Ubicacion, Raiz).join(Raiz, Raiz.id == Ubicacion.raiz_id)
        .where(Ubicacion.imagen_id == imagen_id, Ubicacion.estado == "disponible")
        .order_by(Ubicacion.id)
    ).first()
    if fila is None:
        return None, None
    ubic, raiz = fila
    return Path(raiz.ruta_montaje) / ubic.ruta_relativa, ubic.nombre_archivo


def generar(limite=None, solo_id=None, salida: Path = SALIDA_DEFECTO):
    salida.mkdir(parents=True, exist_ok=True)
    hechas = fallos = 0
    with SessionLocal() as s:
        consulta = select(AnalisisPose).order_by(AnalisisPose.imagen_id)
        if solo_id:
            consulta = consulta.where(AnalisisPose.imagen_id == solo_id)
        if limite:
            consulta = consulta.limit(limite)
        analisis = list(s.scalars(consulta))
        total = len(analisis)
        print(f"Imagenes a dibujar: {total}  ->  {salida}")

        for i, a in enumerate(analisis, 1):
            ruta, nombre = ruta_imagen(s, a.imagen_id)
            if ruta is None or not ruta.exists():
                fallos += 1
                continue
            img = cv2.imread(str(ruta))
            if img is None:
                fallos += 1
                continue
            medidas = s.scalar(select(MedidasPose).where(MedidasPose.imagen_id == a.imagen_id))
            imagen = s.get(Imagen, a.imagen_id)
            if a.landmarks_2d:
                dibujar(img, a.landmarks_2d, medidas.angulos if medidas else None)
            _panel(img, [f"[{a.imagen_id}] {nombre}"] + _lineas_panel(imagen, a, medidas))

            destino = salida / f"{a.imagen_id:04d}_{Path(nombre).stem}.jpg"
            cv2.imwrite(str(destino), img)
            hechas += 1
            if i % 20 == 0 or i == total:
                print(f"[{i}/{total}] dibujadas")

    print(f"\nHecho. Dibujadas: {hechas} | sin archivo: {fallos}\nCarpeta: {salida}")


def main():
    p = argparse.ArgumentParser(description="Overlay de depuracion de pose")
    p.add_argument("--limite", type=int)
    p.add_argument("--id", type=int, dest="solo_id")
    p.add_argument("--salida", type=Path, default=SALIDA_DEFECTO)
    args = p.parse_args()
    generar(limite=args.limite, solo_id=args.solo_id, salida=args.salida)


if __name__ == "__main__":
    main()
