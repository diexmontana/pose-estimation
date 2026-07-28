"""Indexado desde la interfaz (trozo 2).

- Abre un dialogo nativo del sistema para elegir carpeta (funciona porque el
  servidor corre en la misma maquina que el navegador).
- Encadena el pipeline automatico (indexar -> pose -> medidas -> etiquetas ->
  vector) en un hilo de fondo, con seguimiento de progreso por fases.
- Paso rapido: asignar un modelo y/o una coleccion a toda la carpeta.
"""

import subprocess
import sys
import threading
import uuid
from pathlib import Path

from sqlalchemy import func, select

from backend.db.models import (
    Coleccion, ColaRevision, Imagen, ImagenColeccion, ImagenModelo, Modelo,
    Raiz, Ubicacion,
)
from backend.db.session import SessionLocal

# Estado de los trabajos de indexado en memoria (id -> dict).
JOBS: dict[str, dict] = {}

FASES = {
    "indexando": "Indexando carpeta (rutas, hashes, miniaturas)…",
    "pose": "Analizando la pose con MediaPipe… (puede tardar)",
    "midiendo": "Calculando medidas geométricas…",
    "etiquetando": "Aplicando reglas y etiquetas…",
    "vector": "Construyendo vectores de similitud…",
    "listo": "Listo",
    "error": "Error",
}


def elegir_carpeta() -> str | None:
    """Abre el dialogo nativo de seleccion de carpeta y devuelve la ruta
    elegida, o None si se canceló. Se ejecuta en un subproceso para no chocar
    con el hilo del servidor."""
    script = (
        "import tkinter as tk\n"
        "from tkinter import filedialog\n"
        "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
        "print(filedialog.askdirectory() or '')\n"
    )
    try:
        res = subprocess.run([sys.executable, "-c", script],
                             capture_output=True, text=True, timeout=300)
        ruta = res.stdout.strip()
        return ruta or None
    except Exception:
        return None


def iniciar(ruta: str, con_revision: bool) -> str:
    """Crea un trabajo y lanza el pipeline en segundo plano. Devuelve el id."""
    job_id = uuid.uuid4().hex[:8]
    nombre = Path(ruta).name or "raiz"
    JOBS[job_id] = {"fase": "indexando", "terminado": False, "error": None,
                    "ruta": ruta, "nombre": nombre, "con_revision": con_revision,
                    "raiz_id": None, "dudosas": 0, "resumen": None}
    t = threading.Thread(target=_ejecutar, args=(job_id,), daemon=True)
    t.start()
    return job_id


def _ejecutar(job_id: str):
    # imports aqui para no cargar MediaPipe salvo que se use
    from backend.indexing.indexador import indexar_raiz
    from backend.pose.procesar import procesar
    from backend.pose.vectorizar import vectorizar
    from backend.tagging.derivar import derivar
    from backend.tagging.etiquetar import etiquetar

    J = JOBS[job_id]
    try:
        J["fase"] = "indexando"
        with SessionLocal() as s:
            resumen = indexar_raiz(s, Path(J["ruta"]), J["nombre"], "interno")
        J["resumen"] = {"nuevas": resumen.nuevas, "vistas": resumen.vistas,
                        "duplicadas": resumen.duplicadas}

        J["fase"] = "pose"
        procesar()
        J["fase"] = "midiendo"
        derivar()
        J["fase"] = "etiquetando"
        etiquetar()
        J["fase"] = "vector"
        vectorizar()

        with SessionLocal() as s:
            raiz = s.scalar(select(Raiz).where(Raiz.nombre == J["nombre"]))
            J["raiz_id"] = raiz.id if raiz else None
            J["dudosas"] = s.scalar(select(func.count(ColaRevision.id))
                                    .where(ColaRevision.estado == "pendiente")) or 0
        J["fase"] = "listo"
        J["terminado"] = True
    except Exception as e:  # noqa: BLE001
        J["fase"] = "error"
        J["error"] = str(e)
        J["terminado"] = True


def _imagenes_de_raiz(s, raiz_id: int) -> list[int]:
    return list(s.scalars(select(Ubicacion.imagen_id).where(Ubicacion.raiz_id == raiz_id).distinct()))


def sugerir_modelos(s, texto: str) -> list[str]:
    texto = (texto or "").strip()
    consulta = select(Modelo.nombre).order_by(Modelo.nombre).limit(8)
    if texto:
        consulta = consulta.where(Modelo.nombre.ilike(f"%{texto}%"))
    return list(s.scalars(consulta))


def asignar_carpeta(s, raiz_id: int, modelo_nombre: str = "", coleccion_nombre: str = "") -> dict:
    """Asigna un modelo y/o añade a una colección todas las imágenes de una
    raíz (carpeta indexada). Crea modelo/colección si no existen."""
    img_ids = _imagenes_de_raiz(s, raiz_id)
    hecho = {"modelo": None, "coleccion": None, "imagenes": len(img_ids)}

    if modelo_nombre.strip():
        nombre = modelo_nombre.strip()
        modelo = s.scalar(select(Modelo).where(Modelo.nombre == nombre))
        if modelo is None:
            modelo = Modelo(nombre=nombre)
            s.add(modelo)
            s.flush()
        for iid in img_ids:
            if not s.get(ImagenModelo, {"imagen_id": iid, "modelo_id": modelo.id}):
                s.add(ImagenModelo(imagen_id=iid, modelo_id=modelo.id))
        hecho["modelo"] = nombre

    if coleccion_nombre.strip():
        nombre = coleccion_nombre.strip()
        col = s.scalar(select(Coleccion).where(Coleccion.nombre == nombre))
        if col is None:
            col = Coleccion(nombre=nombre, tipo="estatica")
            s.add(col)
            s.flush()
        maxo = s.scalar(select(func.max(ImagenColeccion.orden))
                        .where(ImagenColeccion.coleccion_id == col.id)) or 0
        for iid in img_ids:
            if not s.get(ImagenColeccion, {"imagen_id": iid, "coleccion_id": col.id}):
                maxo += 1
                s.add(ImagenColeccion(imagen_id=iid, coleccion_id=col.id, orden=maxo))
        hecho["coleccion"] = nombre

    s.commit()
    return hecho
