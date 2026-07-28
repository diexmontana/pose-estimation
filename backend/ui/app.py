"""Fachada HTML de la aplicacion (fase 8). Rutas delgadas que llaman a los
servicios y devuelven fragmentos HTML (HTMX). No hay fachada JSON por ahora
(ver 6.10 del diseño).

Arrancar:  uvicorn backend.ui.app:app --reload
Luego abrir http://localhost:8000
"""

from pathlib import Path

from sqlalchemy import select

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.db.session import SessionLocal
from backend.services import detalle, galeria, practica
from backend.ui import indexado

RAIZ = Path(__file__).resolve().parents[2]
PLANTILLAS = RAIZ / "frontend" / "templates"
MINIATURAS = RAIZ / "data" / "miniaturas"

app = FastAPI(title="Referencias de pose")
templates = Jinja2Templates(directory=str(PLANTILLAS))

MINIATURAS.mkdir(parents=True, exist_ok=True)
app.mount("/miniaturas", StaticFiles(directory=str(MINIATURAS)), name="miniaturas")


import random as _random


def _seed(seed: str, mezclar: int) -> int:
    """Nueva baraja si se pide mezclar o si no hay seed; si no, se conserva."""
    s = _int_o_none(seed)
    return _random.randint(1, 10_000_000) if (mezclar or s is None) else s


def _int_o_none(valor):
    """Convierte '' o None a None; un numero a int. Los desplegables mandan ''
    cuando se elige 'Todas/Todos'."""
    if valor is None or valor == "":
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request, op: list[int] = Query(default=[]),
           coleccion: str = "", modelo: str = "", seed: str = "", mezclar: int = 0):
    with SessionLocal() as s:
        datos = galeria.listar(s, pagina=1, opcion_ids=op,
                               coleccion_id=_int_o_none(coleccion),
                               modelo_id=_int_o_none(modelo), seed=_seed(seed, mezclar))
        datos["grupos"] = galeria.arbol_agrupado(s)
        datos["seleccion"] = set(op)
        datos["colecciones"] = galeria.listar_colecciones(s)
        datos["modelos"] = galeria.listar_modelos(s)
        datos["activo"] = "inicio"
    return templates.TemplateResponse(request, "galeria.html", datos)


@app.get("/galeria", response_class=HTMLResponse)
def mas_galeria(request: Request, pagina: int = 1, op: list[int] = Query(default=[]),
                coleccion: str = "", modelo: str = "", seed: str = "", mezclar: int = 0):
    """Fragmento con una pagina de tarjetas (para 'cargar mas', filtros y mezclar)."""
    with SessionLocal() as s:
        datos = galeria.listar(s, pagina=pagina, opcion_ids=op,
                               coleccion_id=_int_o_none(coleccion),
                               modelo_id=_int_o_none(modelo), seed=_seed(seed, mezclar))
    return templates.TemplateResponse(request, "_grid.html", datos)


@app.get("/colecciones", response_class=HTMLResponse)
def colecciones_pagina(request: Request):
    with SessionLocal() as s:
        cols = galeria.colecciones_con_portada(s)
    return templates.TemplateResponse(
        request, "colecciones.html", {"colecciones": cols, "activo": "colecciones"})


@app.get("/coleccion/{coleccion_id}", response_class=HTMLResponse)
def coleccion_ver(request: Request, coleccion_id: int):
    from backend.db.models import Coleccion
    with SessionLocal() as s:
        col = s.get(Coleccion, coleccion_id)
        if col is None:
            return HTMLResponse("Colección no encontrada", status_code=404)
        datos = galeria.listar(s, coleccion_id=coleccion_id, por_pagina=300)
        datos["coleccion"] = {"id": col.id, "nombre": col.nombre}
        datos["coleccion_ver"] = coleccion_id
        datos["activo"] = "colecciones"
    return templates.TemplateResponse(request, "coleccion.html", datos)


@app.post("/coleccion/{coleccion_id}/borrar")
def coleccion_borrar(coleccion_id: int):
    with SessionLocal() as s:
        galeria.borrar_coleccion(s, coleccion_id)
    return HTMLResponse("", headers={"HX-Redirect": "/colecciones"})


@app.post("/coleccion/{coleccion_id}/quitar/{imagen_id}", response_class=HTMLResponse)
def coleccion_quitar(coleccion_id: int, imagen_id: int):
    with SessionLocal() as s:
        galeria.quitar_de_coleccion(s, coleccion_id, imagen_id)
    return HTMLResponse("")  # la tarjeta se elimina del DOM


@app.post("/coleccion/{coleccion_id}/exportar", response_class=HTMLResponse)
def coleccion_exportar(coleccion_id: int):
    from backend.services import exportar
    destino = indexado.elegir_carpeta()
    if not destino:
        return HTMLResponse("")  # cancelado
    with SessionLocal() as s:
        r = exportar.exportar_coleccion(s, coleccion_id, destino)
    falt = f" · {r['faltantes']} no disponibles" if r["faltantes"] else ""
    return HTMLResponse(
        f'<div class="modal-bg" onclick="this.remove()"><div class="toast">'
        f'Exportadas {r["copiadas"]}/{r["total"]} imágenes a «{r["destino"]}»{falt} ✓</div></div>')


@app.post("/imagen/{imagen_id}/excluir", response_class=HTMLResponse)
def imagen_excluir(imagen_id: int):
    with SessionLocal() as s:
        galeria.excluir(s, imagen_id, True)
    return HTMLResponse("")  # la tarjeta se elimina del DOM


@app.post("/imagen/{imagen_id}/restaurar", response_class=HTMLResponse)
def imagen_restaurar(imagen_id: int):
    with SessionLocal() as s:
        galeria.excluir(s, imagen_id, False)
    return HTMLResponse("")


@app.get("/papelera", response_class=HTMLResponse)
def papelera_pagina(request: Request):
    with SessionLocal() as s:
        items = galeria.papelera(s)
    return templates.TemplateResponse(
        request, "papelera.html", {"items": items, "activo": "papelera"})


@app.get("/practica", response_class=HTMLResponse)
def practica_config(request: Request, op: list[int] = Query(default=[]),
                    coleccion: list[int] = Query(default=[]),
                    modelo: list[int] = Query(default=[])):
    with SessionLocal() as s:
        prev = practica.muestra(s, practica.pool(s, coleccion, modelo, op))
        ctx = {
            "grupos": galeria.arbol_agrupado(s),
            "seleccion": set(op),
            "colecciones": galeria.colecciones_con_portada(s),
            "modelos": galeria.listar_modelos(s),
            "coleccion_ids": coleccion, "modelo_ids": modelo,
            "clases": practica.clases_descritas(),
            "intervalos": practica.INTERVALOS,
            "preview": prev,
            "activo": "practica",
        }
    return templates.TemplateResponse(request, "practica.html", ctx)


@app.get("/practica/preview", response_class=HTMLResponse)
def practica_preview(request: Request, op: list[int] = Query(default=[]),
                     coleccion: list[int] = Query(default=[]),
                     modelo: list[int] = Query(default=[])):
    with SessionLocal() as s:
        prev = practica.muestra(s, practica.pool(s, coleccion, modelo, op))
    return templates.TemplateResponse(request, "_practica_preview.html", {"preview": prev})


@app.get("/practica/iniciar", response_class=HTMLResponse)
def practica_iniciar(request: Request, op: list[int] = Query(default=[]),
                     coleccion: list[int] = Query(default=[]),
                     modelo: list[int] = Query(default=[]), orden: str = "aleatorio",
                     modo: str = "intervalo", seg: str = "30", custom: str = "60",
                     numero: str = "", clase: str = "30 min"):
    with SessionLocal() as s:
        ids = practica.pool(s, coleccion, modelo, op, orden)
    if not ids:
        return HTMLResponse(
            '<div style="padding:2rem;color:#ccc">No hay imágenes que cumplan esos '
            'criterios. <a href="/practica" style="color:#5b8cff">Volver a configurar</a></div>')

    if modo == "clase":
        plan = practica.plan_clase(clase)
    else:
        segundos = _int_o_none(custom) or 60 if seg == "custom" else int(seg)
        plan = practica.plan_intervalo(segundos, _int_o_none(numero))

    return templates.TemplateResponse(
        request, "practica_sesion.html", {"pool": ids, "plan": plan})


def _picker(request: Request, imagen_id: int):
    with SessionLocal() as s:
        cols = galeria.colecciones_estado(s, imagen_id)
    return templates.TemplateResponse(
        request, "_guardar.html", {"imagen_id": imagen_id, "colecciones": cols})


@app.get("/coleccion/picker/{imagen_id}", response_class=HTMLResponse)
def coleccion_picker(request: Request, imagen_id: int):
    return _picker(request, imagen_id)


@app.post("/coleccion/guardar", response_class=HTMLResponse)
def coleccion_guardar(request: Request, imagen_id: int = Form(...),
                      coleccion_id: str = Form(""), nuevo: str = Form("")):
    with SessionLocal() as s:
        galeria.guardar_en_coleccion(
            s, imagen_id, int(coleccion_id) if coleccion_id else None, nuevo or None)
    return _picker(request, imagen_id)  # re-renderiza el selector con el nuevo estado


@app.post("/coleccion/quitar-img", response_class=HTMLResponse)
def coleccion_quitar_img(request: Request, imagen_id: int = Form(...),
                         coleccion_id: int = Form(...)):
    with SessionLocal() as s:
        galeria.quitar_de_coleccion(s, coleccion_id, imagen_id)
    return _picker(request, imagen_id)


def _ctx_estado(request, job_id):
    j = indexado.JOBS.get(job_id)
    if j is None:
        return HTMLResponse("")
    ctx = {"job": job_id, "fase": j["fase"], "fase_msg": indexado.FASES.get(j["fase"], j["fase"]),
           "terminado": j["terminado"], "error": j["error"], "resumen": j["resumen"],
           "raiz_id": j["raiz_id"], "dudosas": j["dudosas"], "con_revision": j["con_revision"]}
    if j["terminado"] and not j["error"]:
        with SessionLocal() as s:
            ctx["modelos"] = [m["nombre"] for m in galeria.listar_modelos(s)]
            ctx["colecciones"] = [c["nombre"] for c in galeria.listar_colecciones(s)]
    return templates.TemplateResponse(request, "_indexar.html", ctx)


@app.post("/indexar/elegir", response_class=HTMLResponse)
def indexar_elegir(request: Request, con_revision: int = 0):
    ruta = indexado.elegir_carpeta()
    if not ruta:
        return HTMLResponse("")  # cancelado -> cierra el popover
    job_id = indexado.iniciar(ruta, bool(con_revision))
    return _ctx_estado(request, job_id)


@app.get("/indexar/estado/{job_id}", response_class=HTMLResponse)
def indexar_estado(request: Request, job_id: str):
    return _ctx_estado(request, job_id)


@app.post("/indexar/asignar", response_class=HTMLResponse)
def indexar_asignar(request: Request, raiz_id: int = Form(...),
                    modelo: str = Form(""), coleccion: str = Form("")):
    with SessionLocal() as s:
        hecho = indexado.asignar_carpeta(s, raiz_id, modelo, coleccion)
    partes = []
    if hecho["modelo"]:
        partes.append(f"modelo «{hecho['modelo']}»")
    if hecho["coleccion"]:
        partes.append(f"colección «{hecho['coleccion']}»")
    msg = ("Asignado: " + ", ".join(partes)) if partes else "Sin cambios"
    return HTMLResponse(
        f'<div class="modal-bg" onclick="this.remove()"><div class="toast">{msg} ✓ '
        f'<a href="/" style="color:#fff;text-decoration:underline">ver galería</a></div></div>')


@app.get("/revision")
def revision_inicio():
    """Entra en la revision guiada por la primera imagen (dudosas primero)."""
    with SessionLocal() as s:
        orden, _ = detalle.review_lista(s)
    if not orden:
        return RedirectResponse("/", status_code=303)
    return RedirectResponse(f"/imagen/{orden[0]}?revision=1", status_code=303)


@app.get("/imagen/{imagen_id}", response_class=HTMLResponse)
def detalle_imagen(request: Request, imagen_id: int, revision: int = 0):
    with SessionLocal() as s:
        d = detalle.datos(s, imagen_id)
        if d is None:
            return HTMLResponse("Imagen no encontrada", status_code=404)
        d["revision"] = bool(revision)
        d["rev"] = detalle.review_contexto(s, imagen_id) if revision else None
    return templates.TemplateResponse(request, "detalle.html", d)


@app.get("/imagen/{imagen_id}/original")
def imagen_original(imagen_id: int):
    """Sirve la imagen original a resolucion completa; si el archivo no esta
    disponible, cae a la miniatura."""
    from backend.db.models import Miniatura
    from backend.tagging import overlay as ov
    with SessionLocal() as s:
        ruta, _ = ov.ruta_imagen(s, imagen_id)
        if ruta and ruta.exists():
            return FileResponse(str(ruta))
        ruta_min = s.scalar(select(Miniatura.ruta).where(Miniatura.imagen_id == imagen_id))
    if ruta_min and (MINIATURAS / ruta_min).exists():
        return FileResponse(str(MINIATURAS / ruta_min))
    return Response(status_code=404)


@app.get("/imagen/{imagen_id}/overlay")
def overlay_imagen(imagen_id: int):
    with SessionLocal() as s:
        data = detalle.overlay_bytes(s, imagen_id)
    if data is None:
        return Response(status_code=404)
    return Response(content=data, media_type="image/jpeg")


@app.post("/imagen/{imagen_id}/modelo", response_class=HTMLResponse)
def imagen_modelo(request: Request, imagen_id: int,
                  nombre: str = Form(""), carpeta: int = Form(0)):
    with SessionLocal() as s:
        nom = detalle.set_modelo(s, imagen_id, nombre, a_carpeta=bool(carpeta))
    if not nom:
        return HTMLResponse('<span style="color:var(--muted)">modelo quitado</span>')
    alcance = "toda la carpeta" if carpeta else "esta imagen"
    return HTMLResponse(f'<span style="color:#7fbf7f">✓ «{nom}» en {alcance}</span>')


@app.post("/imagen/{imagen_id}/etiqueta", response_class=HTMLResponse)
def editar_etiqueta(request: Request, imagen_id: int,
                    categoria: str = Form(...), opcion_id: str = Form("")):
    with SessionLocal() as s:
        if opcion_id:
            detalle.set_manual(s, imagen_id, int(opcion_id))
        else:
            detalle.quitar_manual(s, imagen_id, categoria_codigo=categoria)
        d = detalle.datos(s, imagen_id)
    return templates.TemplateResponse(request, "_panel.html", d)


@app.post("/imagen/{imagen_id}/quitar", response_class=HTMLResponse)
def quitar_etiqueta(request: Request, imagen_id: int, opcion_id: int = Form(...)):
    with SessionLocal() as s:
        detalle.quitar_manual(s, imagen_id, opcion_id=opcion_id)
        d = detalle.datos(s, imagen_id)
    return templates.TemplateResponse(request, "_panel.html", d)
