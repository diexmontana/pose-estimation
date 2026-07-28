"""Esquema minimo de la fase 1.

Tablas de archivos y ubicaciones (seccion 10 de notas-diseno.md) mas
colecciones, que se modelan desde el principio. Las tablas de pose,
taxonomia, etc. se agregan en sus fases; hasta la fase 5 el esquema se
recrea desde cero con reset_db.py.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from backend.db.tipos import Vector


class Base(DeclarativeBase):
    pass


class Raiz(Base):
    """Carpeta raiz registrada. Las rutas se guardan relativas a ella,
    de modo que si cambia la letra de unidad basta con repuntarla."""

    __tablename__ = "raiz"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True)
    tipo: Mapped[str] = mapped_column(String(10))  # interno | externo
    ruta_montaje: Mapped[str] = mapped_column(String(500))
    ultima_verificacion: Mapped[Optional[datetime]] = mapped_column(DateTime)


class Carpeta(Base):
    """Carpeta dentro de una raiz. Soporta la herencia de atributos
    (fase 6); el arbol se forma con carpeta_padre_id."""

    __tablename__ = "carpeta"
    __table_args__ = (UniqueConstraint("raiz_id", "ruta_relativa"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    raiz_id: Mapped[int] = mapped_column(ForeignKey("raiz.id"))
    ruta_relativa: Mapped[str] = mapped_column(String(500))
    carpeta_padre_id: Mapped[Optional[int]] = mapped_column(ForeignKey("carpeta.id"))


class Imagen(Base):
    """Entidad logica, identificada por hash de contenido. Puede vivir
    en varias ubicaciones fisicas."""

    __tablename__ = "imagen"

    id: Mapped[int] = mapped_column(primary_key=True)
    hash_contenido: Mapped[str] = mapped_column(String(64), unique=True)
    hash_perceptual: Mapped[Optional[str]] = mapped_column(String(32))
    ancho: Mapped[Optional[int]] = mapped_column(Integer)
    alto: Mapped[Optional[int]] = mapped_column(Integer)
    formato: Mapped[Optional[str]] = mapped_column(String(10))
    tamano_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    fecha_indexado: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # Ciclo de vida: registrada | analizada | medida | etiquetada | error
    estado_analisis: Mapped[str] = mapped_column(String(15), default="registrada")
    # Excluida (papelera reversible por hash): no se muestra ni entra en sesiones,
    # y al reindexar se mantiene fuera. No borra el archivo.
    excluida: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))

    ubicaciones: Mapped[list["Ubicacion"]] = relationship(back_populates="imagen")


class Ubicacion(Base):
    """Sitio fisico donde vive una imagen."""

    __tablename__ = "ubicacion"
    __table_args__ = (UniqueConstraint("raiz_id", "ruta_relativa"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    imagen_id: Mapped[int] = mapped_column(ForeignKey("imagen.id"))
    raiz_id: Mapped[int] = mapped_column(ForeignKey("raiz.id"))
    carpeta_id: Mapped[Optional[int]] = mapped_column(ForeignKey("carpeta.id"))
    ruta_relativa: Mapped[str] = mapped_column(String(500))
    nombre_archivo: Mapped[str] = mapped_column(String(255))
    fecha_modificacion: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # disponible | faltante | movida
    estado: Mapped[str] = mapped_column(String(10), default="disponible")
    ultima_verificacion: Mapped[Optional[datetime]] = mapped_column(DateTime)

    imagen: Mapped["Imagen"] = relationship(back_populates="ubicaciones")


class Miniatura(Base):
    __tablename__ = "miniatura"

    id: Mapped[int] = mapped_column(primary_key=True)
    imagen_id: Mapped[int] = mapped_column(ForeignKey("imagen.id"), unique=True)
    ruta: Mapped[str] = mapped_column(String(500))


class Coleccion(Base):
    __tablename__ = "coleccion"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), unique=True)
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(10), default="estatica")  # estatica | dinamica
    imagen_portada_id: Mapped[Optional[int]] = mapped_column(ForeignKey("imagen.id"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ImagenColeccion(Base):
    __tablename__ = "imagen_coleccion"

    imagen_id: Mapped[int] = mapped_column(ForeignKey("imagen.id"), primary_key=True)
    coleccion_id: Mapped[int] = mapped_column(ForeignKey("coleccion.id"), primary_key=True)
    orden: Mapped[Optional[int]] = mapped_column(Integer)
    fecha_agregado: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AnalisisPose(Base):
    """Salida cruda de MediaPipe (fase 3). Se escribe una vez por imagen.
    Todo lo derivado (medidas, etiquetas) sale de aqui en fases posteriores,
    sin volver a pasar el modelo. Guarda los landmarks tal cual, sin
    interpretar.
    """

    __tablename__ = "analisis_pose"

    id: Mapped[int] = mapped_column(primary_key=True)
    imagen_id: Mapped[int] = mapped_column(ForeignKey("imagen.id"), unique=True)
    version_modelo: Mapped[str] = mapped_column(String(50))
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    num_figuras: Mapped[int] = mapped_column(Integer, default=0)
    # Indice (dentro de la deteccion) de la figura elegida como principal.
    figura_principal: Mapped[Optional[int]] = mapped_column(Integer)
    # False cuando no se detecto ninguna figura; el triaje de torso es fase 4.
    pose_detectada: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo: Mapped[Optional[str]] = mapped_column(String(50))

    # Crudo: lista de 33 landmarks {x,y,z,visibility,presence} de la figura
    # principal. Normalizados 0-1 (imagen) y en metros (world).
    landmarks_2d: Mapped[Optional[list]] = mapped_column(JSON)
    world_landmarks_3d: Mapped[Optional[list]] = mapped_column(JSON)
    # Visibilidad media por zona: cabeza, torso, brazos, manos, piernas, pies.
    visibilidad_zonas: Mapped[Optional[dict]] = mapped_column(JSON)


class MedidasPose(Base):
    """Medidas geometricas derivadas de analisis_pose (fase 4).

    Regenerable: no vuelve a pasar MediaPipe, solo recalcula desde lo crudo.
    Lleva version_reglas para poder rematerializar al mejorar una regla.
    Las medidas que no se pueden calcular con fiabilidad quedan en None,
    nunca inventadas (seccion 7.1).
    """

    __tablename__ = "medidas_pose"

    id: Mapped[int] = mapped_column(primary_key=True)
    imagen_id: Mapped[int] = mapped_column(ForeignKey("imagen.id"), unique=True)
    version_reglas: Mapped[str] = mapped_column(String(20))
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Triaje (7.1): con torso -> via geometrica completa; sin torso -> primer plano.
    torso_fiable: Mapped[bool] = mapped_column(Boolean, default=False)
    es_primer_plano: Mapped[bool] = mapped_column(Boolean, default=False)

    # Angulos articulares 3D en grados (7.3). Dict {codo_izq, rodilla_der, ...}.
    angulos: Mapped[Optional[dict]] = mapped_column(JSON)
    # Señales ordinales (7.3): inclinaciones con signo, contraposto, manos, piernas.
    senales: Mapped[Optional[dict]] = mapped_column(JSON)
    # Escorzo por miembro (7.3): ratio proyectado/real, <1 = escorzado.
    escorzo: Mapped[Optional[dict]] = mapped_column(JSON)
    # Señales de orientacion corporal (7.4), sin interpretar todavia.
    orientacion: Mapped[Optional[dict]] = mapped_column(JSON)

    # Base para dinamismo (7.3) y deteccion de acostado.
    extension: Mapped[Optional[float]] = mapped_column(Float)
    compacidad: Mapped[Optional[float]] = mapped_column(Float)
    dispersion_vertical: Mapped[Optional[float]] = mapped_column(Float)
    dispersion_horizontal: Mapped[Optional[float]] = mapped_column(Float)


class VectorPose(Base):
    """Vector de similitud de pose (fase 7, seccion 8). Sustituye a los
    embeddings para 'buscar imagenes parecidas': mas preciso para pose e
    interpretable.

    - `vector`: seno y coseno de cada angulo curado (no el grado crudo, para
      que 359 y 1 no parezcan lejanos). Longitud fija.
    - `vector_reflejado`: la version espejo (izq<->der). Una pose y su espejo
      son la misma referencia para un artista.
    - `mascara`: 1/0 por angulo, para comparar solo sobre articulaciones
      fiables en ambas imagenes.
    """

    __tablename__ = "vector_pose"

    id: Mapped[int] = mapped_column(primary_key=True)
    imagen_id: Mapped[int] = mapped_column(ForeignKey("imagen.id"), unique=True)
    vector: Mapped[list] = mapped_column(Vector(16))
    vector_reflejado: Mapped[list] = mapped_column(Vector(16))
    mascara: Mapped[list] = mapped_column(JSON)  # lista de 8 enteros 0/1
    version: Mapped[str] = mapped_column(String(20))


class Categoria(Base):
    """Categoria de la taxonomia (fase 5: solo las automaticas de 9.1;
    el arbol manual rico llega en la fase 6)."""

    __tablename__ = "categoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))
    es_multivalor: Mapped[bool] = mapped_column(Boolean, default=False)
    detectable_automaticamente: Mapped[bool] = mapped_column(Boolean, default=True)
    nivel_sugerido: Mapped[str] = mapped_column(String(10), default="imagen")  # modelo|carpeta|imagen
    orden: Mapped[int] = mapped_column(Integer, default=0)

    opciones: Mapped[list["Opcion"]] = relationship(back_populates="categoria")


class Opcion(Base):
    """Valor posible de una categoria. id_padre soporta el arbol (fase 6);
    en la fase 5 las opciones automaticas son planas."""

    __tablename__ = "opcion"
    __table_args__ = (UniqueConstraint("categoria_id", "codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria.id"))
    id_padre: Mapped[Optional[int]] = mapped_column(ForeignKey("opcion.id"))
    codigo: Mapped[str] = mapped_column(String(40))
    nombre: Mapped[str] = mapped_column(String(80))
    orden: Mapped[int] = mapped_column(Integer, default=0)

    categoria: Mapped["Categoria"] = relationship(back_populates="opciones")


class ImagenOpcion(Base):
    """Asignacion de una opcion a una imagen, con procedencia (6.2).
    En la fase 5 el origen es siempre 'geometrico'. categoria_id se
    denormaliza para simplificar consultas y garantizar unicidad de las
    categorias de valor unico por (imagen, categoria, origen) desde la app."""

    __tablename__ = "imagen_opcion"

    id: Mapped[int] = mapped_column(primary_key=True)
    imagen_id: Mapped[int] = mapped_column(ForeignKey("imagen.id"))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria.id"))
    opcion_id: Mapped[int] = mapped_column(ForeignKey("opcion.id"))
    origen: Mapped[str] = mapped_column(String(12))  # geometrico|manual|carpeta|modelo
    confianza: Mapped[Optional[float]] = mapped_column(Float)
    version_reglas: Mapped[Optional[str]] = mapped_column(String(20))
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ColaRevision(Base):
    """Casos que las reglas no resuelven con confianza (6.8, 7.6). El
    etiquetado manual de esta cola es como el sistema aprende donde falla."""

    __tablename__ = "cola_revision"

    id: Mapped[int] = mapped_column(primary_key=True)
    imagen_id: Mapped[int] = mapped_column(ForeignKey("imagen.id"))
    categoria_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categoria.id"))
    motivo: Mapped[str] = mapped_column(String(20))  # ambiguo|baja_confianza|sin_deteccion
    estado: Mapped[str] = mapped_column(String(12), default="pendiente")  # pendiente|resuelto
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Modelo(Base):
    """Persona fotografiada. Fuente de verdad del nivel modelo (6.3)."""

    __tablename__ = "modelo"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    notas: Mapped[Optional[str]] = mapped_column(Text)
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AliasModelo(Base):
    __tablename__ = "alias_modelo"

    id: Mapped[int] = mapped_column(primary_key=True)
    modelo_id: Mapped[int] = mapped_column(ForeignKey("modelo.id"))
    alias: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[Optional[str]] = mapped_column(String(20))  # real|arroba|personaje


class ImagenModelo(Base):
    __tablename__ = "imagen_modelo"

    imagen_id: Mapped[int] = mapped_column(ForeignKey("imagen.id"), primary_key=True)
    modelo_id: Mapped[int] = mapped_column(ForeignKey("modelo.id"), primary_key=True)


class ModeloOpcion(Base):
    """Atributo asignado a una modelo. Se materializa hacia imagen_opcion
    con origen='modelo' en todas sus fotos (6.3)."""

    __tablename__ = "modelo_opcion"
    __table_args__ = (UniqueConstraint("modelo_id", "opcion_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    modelo_id: Mapped[int] = mapped_column(ForeignKey("modelo.id"))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria.id"))
    opcion_id: Mapped[int] = mapped_column(ForeignKey("opcion.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CarpetaOpcion(Base):
    """Atributo asignado a una carpeta. Se materializa hacia imagen_opcion
    con origen='carpeta', bajando a las subcarpetas; una subcarpeta puede
    contradecir a su padre (6.3)."""

    __tablename__ = "carpeta_opcion"
    __table_args__ = (UniqueConstraint("carpeta_id", "opcion_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    carpeta_id: Mapped[int] = mapped_column(ForeignKey("carpeta.id"))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria.id"))
    opcion_id: Mapped[int] = mapped_column(ForeignKey("opcion.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
