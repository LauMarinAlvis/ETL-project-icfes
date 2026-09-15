import logging
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd # Lo mantenemos solo para exportar el reporte final
import polars as pl

from config import get_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("perfilamiento")

RAW_TABLE = "raw_saber11"
REPORTS_DIR = Path("reports")

COLUMNAS_NUMERICAS = [
    "periodo", "cole_cod_dane_establecimiento", "cole_cod_dane_sede",
    "cole_cod_depto_ubicacion", "cole_cod_mcpio_ubicacion", "cole_codigo_icfes",
    "desemp_c_naturales", "desemp_lectura_critica", "desemp_matematicas",
    "desemp_sociales_ciudadanas", "estu_cod_depto_presentacion",
    "estu_cod_mcpio_presentacion", "estu_cod_reside_depto", "estu_cod_reside_mcpio",
    "estu_grado", "estu_inse_individual", "estu_nse_establecimiento",
    "estu_nse_individual", "estu_repite", "percentil_c_naturales",
    "percentil_global", "percentil_ingles", "percentil_lectura_critica",
    "percentil_matematicas", "percentil_sociales_ciudadanas", "punt_c_naturales",
    "punt_global", "punt_ingles", "punt_lectura_critica", "punt_matematicas",
    "punt_sociales_ciudadanas", "periodo_historico",
]

def cargar_raw(engine) -> pl.DataFrame:
    log.info("Leyendo tabla '%s' usando Polars...", RAW_TABLE)
    uri = engine.url.render_as_string(hide_password=False)
    uri = uri.replace("mysql+pymysql://", "mysql://")
    uri = uri.split("?")[0]  # <-- quita cualquier parámetro extra (charset, etc.)
    query = f"SELECT * FROM {RAW_TABLE}"
    df = pl.read_database_uri(query=query, uri=uri)
    log.info("Filas: %s | Columnas: %s", f"{df.height:,}", df.width)
    return df

def perfilar(df: pl.DataFrame) -> pd.DataFrame:
    filas = df.height
    registros = []

    for col in df.columns:
        serie = df.get_column(col)
        n_nulos = serie.null_count()
        n_unicos = serie.n_unique()

        fila = {
            "columna": col,
            "tipo_polars": str(serie.dtype),
            "n_nulos": n_nulos,
            "pct_nulos": round(100 * n_nulos / filas, 2) if filas else 0,
            "n_unicos": n_unicos,
            "pct_unicos": round(100 * n_unicos / filas, 2) if filas else 0,
        }

        if col in COLUMNAS_NUMERICAS:
            # Cast a float, invalid values become null (strict=False)
            numerico = serie.cast(pl.Float64, strict=False)
            nuevos_nulos = numerico.null_count()

            fila.update({
                "min": numerico.min(),
                "max": numerico.max(),
                "media": round(numerico.mean(), 2) if nuevos_nulos < filas else None,
                "n_no_convertibles_a_numero": nuevos_nulos - n_nulos,
            })
        else:
            # Polars value_counts devuelve un DataFrame, lo ordenamos y tomamos top 3
            top = serie.value_counts().sort("count", descending=True).head(3)
            valores = [f"{row[col]} ({row['count']})" for row in top.iter_rows(named=True)]
            fila["valores_mas_frecuentes"] = "; ".join(valores)

        registros.append(fila)

    # Convertimos la lista de resultados a Pandas solo para facilitar la exportación final
    return pd.DataFrame(registros)

def detectar_duplicados(df: pl.DataFrame) -> dict:
    # is_duplicated devuelve booleanos, sumamos los True
    duplicados_totales = df.is_duplicated().sum()
    duplicados_por_estudiante = (
        df.get_column("estu_consecutivo").is_duplicated().sum()
        if "estu_consecutivo" in df.columns else "N/A"
    )
    return {
        "filas_duplicadas_exactas": duplicados_totales,
        "estu_consecutivo_duplicados": duplicados_por_estudiante,
    }

def revisar_duplicados_estudiante(df: pl.DataFrame) -> pl.DataFrame:
    duplicados = (
        df.filter(pl.col("estu_consecutivo").is_duplicated())
        .sort("estu_consecutivo")
    )
    log.info("Registros con estu_consecutivo duplicado: %s", duplicados.height)

    out_path = REPORTS_DIR / "duplicados_estu_consecutivo.csv"
    duplicados.write_csv(out_path)
    log.info("Casos guardados en: %s", out_path)

    return duplicados

def guardar_reporte(perfil: pd.DataFrame, resumen: dict, total_filas: int, total_cols: int):
    REPORTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    csv_path = REPORTS_DIR / f"perfilamiento_raw_{timestamp}.csv"
    perfil.to_csv(csv_path, index=False, encoding="utf-8-sig")
    log.info("Reporte CSV guardado en: %s", csv_path)

    md_path = REPORTS_DIR / f"perfilamiento_raw_{timestamp}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Perfilamiento de datos - Tabla RAW Saber 11\n\n")
        f.write(f"- Fecha de ejecución: {timestamp}\n")
        f.write(f"- Filas totales: {total_filas:,}\n")
        f.write(f"- Columnas totales: {total_cols}\n")
        f.write(f"- Filas duplicadas exactas: {resumen['filas_duplicadas_exactas']}\n")
        f.write(f"- Duplicados por estu_consecutivo: {resumen['estu_consecutivo_duplicados']}\n\n")
        f.write("## Detalle por columna\n\n")
        f.write(perfil.to_markdown(index=False))
    log.info("Reporte Markdown guardado en: %s", md_path)

def main():
    engine = get_engine()
    df = cargar_raw(engine)

    perfil = perfilar(df)
    resumen = detectar_duplicados(df)

    duplicados_df = revisar_duplicados_estudiante(df)
    print(duplicados_df.select(["estu_consecutivo", "periodo", "cole_cod_dane_establecimiento"]))

    log.info("Resumen de calidad de datos: %s", resumen)
    guardar_reporte(perfil, resumen, df.height, df.width)

    log.info("Perfilamiento finalizado.")

if __name__ == "__main__":
    main()