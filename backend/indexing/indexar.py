"""CLI del indexador.

Uso:
  python -m backend.indexing.indexar "C:\\ruta\\a\\la\\carpeta" [--nombre N] [--tipo interno|externo]

Reindexar es el mismo comando: solo procesa lo nuevo o cambiado.
"""

import argparse
from pathlib import Path

from backend.db.session import SessionLocal
from backend.indexing.indexador import indexar_raiz


def main() -> None:
    parser = argparse.ArgumentParser(description="Indexa una carpeta raiz de imagenes")
    parser.add_argument("ruta", help="Ruta de la carpeta raiz a indexar")
    parser.add_argument("--nombre", help="Nombre de la raiz (por defecto, el de la carpeta)")
    parser.add_argument("--tipo", choices=["interno", "externo"], default="interno")
    args = parser.parse_args()

    ruta = Path(args.ruta)
    if not ruta.is_dir():
        raise SystemExit(f"No existe o no es carpeta: {ruta}")
    nombre = args.nombre or ruta.name

    with SessionLocal() as sesion:
        resumen = indexar_raiz(sesion, ruta, nombre, args.tipo)
    resumen.imprimir()


if __name__ == "__main__":
    main()
