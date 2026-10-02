# Pose Estimation · Organizador de referencias de dibujo por pose

Aplicación local que organiza una colección personal de imágenes de referencia de
figura humana a partir de la **pose** que contienen. Detecta la pose con
**MediaPipe** y clasifica cada imagen mediante **reglas geométricas** (postura,
orientación corporal, encuadre, escorzo y ángulo de cámara), para poder filtrar,
agrupar en colecciones y practicar dibujo con las referencias ordenadas. Todo el
procesamiento ocurre en el equipo del usuario, sin subir nada a la nube.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![MediaPipe](https://img.shields.io/badge/MediaPipe-Pose-0097A7)

---

## Capturas

<!--
  Para agregar imágenes desde la web de GitHub: edita este README, y en el editor
  arrastra y suelta tus capturas aquí. GitHub las sube solo y reemplaza estas
  líneas por la imagen. Sugerencia: una de la galería con filtros, una del detalle
  con el esqueleto detectado y una de la sesión de práctica.
-->

| Galería con filtros | Detalle con pose detectada | Práctica cronometrada |
|---|---|---|
| _<img width="1309" height="631" alt="Screenshot_1" src="https://github.com/user-attachments/assets/c85d1a57-d4d0-4edd-b2d8-66809d2523f8" />_ | _<img width="1010" height="782" alt="Screenshot_3" src="https://github.com/user-attachments/assets/b94d6343-2650-46de-ba34-1f32440da569" />_ | _<img width="888" height="714" alt="Screenshot_2" src="https://github.com/user-attachments/assets/6c3459d9-eafb-4886-ab40-a8400305f085" />_ |




---

## Características

- **Indexado no destructivo:** guarda solo las rutas de las imágenes, nunca copias.
  Las identifica por el **hash de su contenido**, así puedes reorganizar tus
  carpetas sin perder las etiquetas.
- **Detección de pose** con MediaPipe (33 puntos, 2D y 3D).
- **Clasificación por reglas geométricas** interpretables: postura, orientación
  corporal, encuadre, escorzo y ángulo de cámara, con una cola de revisión para
  los casos dudosos.
- **Galería filtrable** por la taxonomía de pose.
- **Colecciones** al estilo de un tablero visual.
- **Modo de práctica** de dibujo cronometrada.
- **100% local:** el procesamiento nunca sale del equipo del usuario.

## Stack tecnológico

Python · FastAPI · SQLAlchemy 2.0 · Alembic · PostgreSQL con pgvector · Docker ·
MediaPipe · OpenCV · NumPy · Jinja2 · HTMX · Alpine.js. Arquitectura por capas
(Clean Architecture).

## Requisitos

- **Python 3.10** o superior
- **Docker** (para PostgreSQL con la extensión pgvector)
- **Git**
- Windows 10/11 (también funciona en Linux o macOS con ajustes menores)

## Instalación y puesta en marcha

1. **Clonar el repositorio**

   ```
   git clone https://github.com/diexmontana/pose-estimation.git
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
colecciones y lanzar sesiones de práctica cronometrada.

## Estructura del proyecto

- `backend/` — lógica de la aplicación: `pose/` (detección con MediaPipe),
  `tagging/` (medidas y reglas de clasificación), `db/` (modelos y migraciones),
  `services/` (galería, detalle, práctica, exportar), `ui/` (aplicación FastAPI).
- `frontend/templates/` — plantillas de la interfaz (Jinja2 + HTMX + Alpine.js).
- `docker/` — `docker-compose.yml` de PostgreSQL con pgvector.
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

## Autor

**Diego Montaña** · Estudiante de Ingeniería de Sistemas (UNSA) y artista plástico.
[GitHub](https://github.com/diexmontana) · [Instagram](https://www.instagram.com/diexmontana/)
