"""Conexion a la base de datos. Lee DATABASE_URL de .env."""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

# Nombre propio del proyecto para no chocar con variables DATABASE_URL
# globales de otros proyectos.
DATABASE_URL = os.getenv(
    "POSE_DB_URL",
    "postgresql+psycopg://pose:pose@localhost:5432/pose_estimation",
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
