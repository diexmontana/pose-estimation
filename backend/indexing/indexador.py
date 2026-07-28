"""Fase 2: indexador.

Recorre una raiz de forma recursiva y registra carpetas, imagenes y
ubicaciones guardando SOLO rutas (relativas a la raiz). Detecta
duplicados por hash de contenido, reconecta archivos movidos, marca
faltantes y genera miniaturas.

Es idempotente: reindexar la misma raiz solo procesa lo nuevo o cambiado.
"""

import hashlib
from datetime import datetime
from pathlib import Path

import imagehash
from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Carpeta, Imagen, Miniatura, Raiz, Ubicacion

EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
MINIATURA_MAX = 512  # lado mayor en pixeles
LOTE_COMMIT = 50  # commit cada N imagenes para no acumular memoria

# data/ vive en la raiz del proyecto, fuera del repositorio
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
MINIATURAS_DIR = DATA_DIR / "miniaturas"


class ResumenIndexado:
    def __init__(self) -> None:
        self.vistas = 0
        self.nuevas = 0
        self.duplicadas = 0  # ubicacion nueva de una imagen ya conocida
        self.sin_cambios = 0
        self.movidas = 0
        self.faltantes = 0
        self.miniaturas = 0
        self.errores: list[str] = []

    def imprimir(self) -> None:
        print(f"Archivos de imagen vistos:   {self.vistas}")
        print(f"Imagenes nuevas:             {self.nuevas}")
        print(f"Ubicaciones duplicadas:      {self.duplicadas}")
        print(f"Sin cambios (saltadas):      {self.sin_cambios}")
        print(f"Movidas (reconectadas):      {self.movidas}")
        print(f"Faltantes:                   {self.faltantes}")
        print(f"Miniaturas generadas:        {self.miniaturas}")
        if self.errores:
            print(f"Errores ({len(self.errores)}):")
            for e in self.errores:
                print(f"  - {e}")


def hash_contenido(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def obtener_raiz(sesion: Session, ruta: Path, nombre: str, tipo: str) -> Raiz:
    """Busca la raiz por nombre; si existe con otra ruta la repunta
    (letra de unidad cambiada), si no existe la crea."""
    raiz = sesion.scalar(select(Raiz).where(Raiz.nombre == nombre))
    if raiz is None:
        raiz = Raiz(nombre=nombre, tipo=tipo, ruta_montaje=str(ruta))
        sesion.add(raiz)
        sesion.flush()
        print(f"Raiz nueva: '{nombre}' -> {ruta}")
    elif Path(raiz.ruta_montaje) != ruta:
        print(f"Raiz '{nombre}' repuntada: {raiz.ruta_montaje} -> {ruta}")
        raiz.ruta_montaje = str(ruta)
    raiz.ultima_verificacion = datetime.now()
    return raiz


def obtener_carpeta(
    sesion: Session, raiz: Raiz, rel: str, cache: dict[str, Carpeta]
) -> Carpeta:
    """Crea (si hace falta) la fila de carpeta y sus ancestros."""
    if rel in cache:
        return cache[rel]
    carpeta = sesion.scalar(
        select(Carpeta).where(Carpeta.raiz_id == raiz.id, Carpeta.ruta_relativa == rel)
    )
    if carpeta is None:
        padre = None
        if rel:  # "" es la carpeta raiz, sin padre
            rel_padre = str(Path(rel).parent.as_posix())
            rel_padre = "" if rel_padre == "." else rel_padre
            padre = obtener_carpeta(sesion, raiz, rel_padre, cache)
        carpeta = Carpeta(
            raiz_id=raiz.id,
            ruta_relativa=rel,
            carpeta_padre_id=padre.id if padre else None,
        )
        sesion.add(carpeta)
        sesion.flush()
    cache[rel] = carpeta
    return carpeta


def generar_miniatura(sesion: Session, imagen: Imagen, ruta_archivo: Path, resumen: ResumenIndexado) -> None:
    fila = sesion.scalar(select(Miniatura).where(Miniatura.imagen_id == imagen.id))
    rel = f"{imagen.hash_contenido[:2]}/{imagen.hash_contenido}.webp"
    destino = MINIATURAS_DIR / rel
    if fila is not None and destino.exists():
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(ruta_archivo) as img:
        img = ImageOps.exif_transpose(img)
        img.thumbnail((MINIATURA_MAX, MINIATURA_MAX))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        img.save(destino, "WEBP", quality=80)
    if fila is None:
        sesion.add(Miniatura(imagen_id=imagen.id, ruta=rel))
    resumen.miniaturas += 1


def indexar_raiz(
    sesion: Session, ruta_montaje: Path, nombre: str, tipo: str = "interno"
) -> ResumenIndexado:
    resumen = ResumenIndexado()
    ruta_montaje = ruta_montaje.resolve()
    raiz = obtener_raiz(sesion, ruta_montaje, nombre, tipo)
    cache_carpetas: dict[str, Carpeta] = {}

    # Ubicaciones ya registradas de esta raiz, por ruta relativa
    existentes: dict[str, Ubicacion] = {
        u.ruta_relativa: u
        for u in sesion.scalars(select(Ubicacion).where(Ubicacion.raiz_id == raiz.id))
    }
    vistas: set[str] = set()
    imagenes_con_ubicacion_nueva: set[int] = set()
    pendientes_commit = 0

    archivos = sorted(
        p for p in ruta_montaje.rglob("*")
        if p.is_file() and p.suffix.lower() in EXTENSIONES
    )

    for archivo in archivos:
        rel = archivo.relative_to(ruta_montaje).as_posix()
        resumen.vistas += 1
        vistas.add(rel)
        try:
            stat = archivo.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime)

            ubic = existentes.get(rel)
            if (
                ubic is not None
                and ubic.fecha_modificacion == mtime
                and ubic.estado == "disponible"
            ):
                resumen.sin_cambios += 1
                imagenes_con_ubicacion_nueva.add(ubic.imagen_id)
                continue

            h = hash_contenido(archivo)
            imagen = sesion.scalar(select(Imagen).where(Imagen.hash_contenido == h))
            if imagen is None:
                with Image.open(archivo) as img:
                    phash = str(imagehash.phash(img))
                    ancho, alto = img.size
                    formato = (img.format or archivo.suffix[1:]).lower()
                imagen = Imagen(
                    hash_contenido=h,
                    hash_perceptual=phash,
                    ancho=ancho,
                    alto=alto,
                    formato=formato,
                    tamano_bytes=stat.st_size,
                )
                sesion.add(imagen)
                sesion.flush()
                resumen.nuevas += 1
            else:
                resumen.duplicadas += 1

            carpeta_rel = str(Path(rel).parent.as_posix())
            carpeta_rel = "" if carpeta_rel == "." else carpeta_rel
            carpeta = obtener_carpeta(sesion, raiz, carpeta_rel, cache_carpetas)

            if ubic is None:
                ubic = Ubicacion(
                    imagen_id=imagen.id,
                    raiz_id=raiz.id,
                    carpeta_id=carpeta.id,
                    ruta_relativa=rel,
                    nombre_archivo=archivo.name,
                )
                sesion.add(ubic)
            else:
                ubic.imagen_id = imagen.id  # archivo reemplazado en la misma ruta
                ubic.carpeta_id = carpeta.id
            ubic.fecha_modificacion = mtime
            ubic.estado = "disponible"
            ubic.ultima_verificacion = datetime.now()
            imagenes_con_ubicacion_nueva.add(imagen.id)

            generar_miniatura(sesion, imagen, archivo, resumen)

            pendientes_commit += 1
            if pendientes_commit >= LOTE_COMMIT:
                sesion.commit()
                pendientes_commit = 0
        except Exception as e:  # un archivo corrupto no debe parar el proceso
            resumen.errores.append(f"{rel}: {e}")
            sesion.rollback()

    # Ubicaciones que ya no estan: movida si su imagen sigue viva en otra
    # ruta vista en esta pasada, faltante si no.
    for rel, ubic in existentes.items():
        if rel in vistas or ubic.estado != "disponible":
            continue
        if ubic.imagen_id in imagenes_con_ubicacion_nueva:
            ubic.estado = "movida"
            resumen.movidas += 1
        else:
            ubic.estado = "faltante"
            resumen.faltantes += 1
        ubic.ultima_verificacion = datetime.now()

    sesion.commit()
    return resumen
