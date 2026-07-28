# Clasificador y buscador de referencias de pose

Aplicación local que organiza una colección personal de imágenes de referencia de
figura humana a partir de la **pose** que contienen. Indexa las carpetas del
usuario (guardando solo las rutas, nunca copias), detecta la pose con **MediaPipe**
y deriva etiquetas interpretables mediante **reglas geométricas** (postura,
orientación corporal, encuadre, escorzo y ángulo de cámara), con una cola de
revisión para los casos dudosos. Ofrece una galería filtrable, colecciones al
estilo de un tablero visual y un modo de práctica de dibujo cronometrada. Todo el
procesamiento se ejecuta en el dispositivo del usuario, sin subir nada a la nube.

## Requisitos

- **Python 3.10** o superior
- **Docker** (para PostgreSQL con la extensión pgvector)
- **Git**
- Windows 10/11 (también funciona en Linux o macOS con ajustes menores)

## Instalación y puesta en marcha

1. **Clonar el repositorio**

   ```
   git clone https://github.com/TU_USUARIO/pose-estimation.git
   cd pose-estimation
   ```

2. **Crear y activar el entorno virtual**

   ```
   python -m venv .venv
   # PowerShell (Windows):
   .venv\Scripts\Activate.ps1
   # cmd (Windows):
   .venv\Scripts\activate.bat
   # Linux / macOS:
   source .venv/bin/activate
   ```

3. **Instalar las dependencias**

   ```
   pip install -r requirements.txt
   ```

4. **Descargar el modelo de MediaPipe**

   El modelo no se incluye en el repositorio. Crea la carpeta `data/models/` y
   coloca dentro el archivo `pose_landmarker_heavy.task`, descargado desde:

   ```
   https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task
   ```

   Debe quedar en `data/models/pose_landmarker_heavy.task`.

5. **Configurar las variables de entorno**

   Copia `.env.example` a `.env` (ajusta `DB_PORT` si el puerto 5432 está ocupado):

   ```
   copy .env.example .env      # Windows
   cp .env.example .env        # Linux / macOS
   ```

6. **Levantar la base de datos** (PostgreSQL + pgvector) con Docker:

   ```
   docker compose -f docker/docker-compose.yml up -d
   ```

7. **Aplicar las migraciones** de la base de datos:

   ```
   alembic upgrade head
   ```

8. **Arrancar la aplicación**:

   ```
   uvicorn backend.ui.app:app --reload
   ```

   Luego abre `http://127.0.0.1:8000` en el navegador.

## Uso

Desde la interfaz puedes indexar una carpeta de imágenes, explorar la galería y
filtrarla por la taxonomía (postura, orientación, encuadre, etc.), abrir el detalle
de cada imagen para ver el esqueleto y editar sus etiquetas, organizar imágenes en
colecciones y lanzar sesiones de práctica cronometrada. El detalle de cada función
está en el **manual de usuario**.

## Estructura del proyecto

- `backend/` — lógica de la aplicación: `pose/` (detección con MediaPipe),
  `tagging/` (medidas y reglas de clasificación), `db/` (modelos y migraciones),
  `services/` (galería, detalle, práctica, exportar), `ui/` (aplicación FastAPI).
- `frontend/templates/` — plantillas de la interfaz (Jinja2 + HTMX + Alpine.js).
- `docker/` — `docker-compose.yml` de PostgreSQL con pgvector.
- `docs/reglas-clasificacion.md` — guía de calibración de las reglas y sus umbrales.
- `data/` — (no versionado) modelo de MediaPipe, miniaturas y caché.

## Comandos útiles

- Borrar lo indexado, conservando la taxonomía:
  `python -m backend.db.borrar_indexado --si`
- Detener la base de datos: `docker compose -f docker/docker-compose.yml down`

## Notas

- Todo el procesamiento es local. Las imágenes originales nunca se copian ni se
  mueven: la aplicación solo guarda sus rutas y las identifica por el hash de su
  contenido, de modo que el usuario puede reorganizar sus carpetas libremente.
- El modelo de MediaPipe y la carpeta `data/` no forman parte del repositorio.
