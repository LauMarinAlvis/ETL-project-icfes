import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.types import Text

from config import get_engine

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler(f"logs/ingesta_{datetime.now():%Y%m%d_%H%M%S}.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("ingesta")

RAW_TABLE = "raw_saber11"
CHUNKSIZE = 20_000


def normalizar_columnas(columnas):
    """snake_case en minúscula, sin espacios, para nombres válidos en MySQL."""
    return [c.strip().lower() for c in columnas]


def crear_tabla_raw(engine, columnas):
   
    columnas_sql = ",\n    ".join(f"`{c}` TEXT NULL" for c in columnas)
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {RAW_TABLE} (
        id_raw BIGINT AUTO_INCREMENT PRIMARY KEY,
        {columnas_sql},
        archivo_origen VARCHAR(255) NULL,
        fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))
    log.info("Tabla raw '%s' verificada/creada (%d columnas fuente).", RAW_TABLE, len(columnas))


def contar_filas_csv(csv_path: Path) -> int:
    """Cuenta filas del CSV sin cargarlo completo en memoria (para validar luego)."""
    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f) - 1  # -1 por el encabezado


def cargar_csv_a_raw(engine, csv_path: Path, archivo_origen: str):
    total_filas_csv = contar_filas_csv(csv_path)
    log.info("El CSV fuente tiene %s filas (sin encabezado).", f"{total_filas_csv:,}")

    filas_cargadas = 0
    dtype_map = None

    lector = pd.read_csv(
        csv_path,
        chunksize=CHUNKSIZE,
        dtype=str,  # todo se lee como texto: la capa raw preserva fidelidad con la fuente
        encoding="utf-8",
        keep_default_na=True,
        na_values=["", "NA", "N/A", "null", "NULL"],
    )

    for i, chunk in enumerate(lector, start=1):
        chunk.columns = normalizar_columnas(chunk.columns)

        if dtype_map is None:
            crear_tabla_raw(engine, list(chunk.columns))
            dtype_map = {c: Text for c in chunk.columns}

        chunk["archivo_origen"] = archivo_origen

        chunk.to_sql(
            RAW_TABLE,
            con=engine,
            if_exists="append",
            index=False,
            dtype=dtype_map,
            method="multi",
            chunksize=2000,
        )
        filas_cargadas += len(chunk)
        log.info("Chunk %d cargado (%s filas acumuladas).", i, f"{filas_cargadas:,}")

    return total_filas_csv, filas_cargadas


def validar_carga(engine, total_filas_csv: int):
    with engine.connect() as conn:
        total_bd = conn.execute(text(f"SELECT COUNT(*) FROM {RAW_TABLE}")).scalar()

    log.info("Filas en CSV: %s | Filas en tabla raw: %s", f"{total_filas_csv:,}", f"{total_bd:,}")
    if total_bd < total_filas_csv:
        log.warning(
            "El conteo en la tabla raw es menor al del CSV. Revise si ya existían "
            "cargas previas (ejecución repetida) o errores en algún chunk en el log."
        )
    else:
        log.info("Validación OK: la carga preservó la cantidad de filas de la fuente.")


def main():
    parser = argparse.ArgumentParser(description="Ingesta CSV crudo -> tabla RAW en MySQL")
    parser.add_argument("--csv", required=True, help="Ruta al archivo CSV de origen")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        log.error("No se encontró el archivo: %s", csv_path)
        sys.exit(1)

    engine = get_engine()
    log.info("Iniciando ingesta desde: %s", csv_path)

    total_csv, total_cargado = cargar_csv_a_raw(engine, csv_path, archivo_origen=csv_path.name)
    validar_carga(engine, total_csv)

    log.info("Ingesta finalizada. %s filas procesadas.", f"{total_cargado:,}")


if __name__ == "__main__":
    main()
