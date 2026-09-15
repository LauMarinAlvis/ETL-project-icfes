import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import polars as pl
from sqlalchemy import text
from sqlalchemy.dialects.mysql import insert as mysql_insert

from config import get_engine

Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler(f"logs/transformacion_{datetime.now():%Y%m%d_%H%M%S}.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("transformacion")

RAW_TABLE = "raw_saber11"

# Código centinela para estudiantes que se inscribieron de forma individual
# (no tienen colegio asociado). Así entran al modelo estrella igual que
# todos los demás, en vez de quedar fuera del estudio.
COD_ICFES_SIN_COLEGIO = -1

# Centinela para NSE faltante. Importante: NO se puede dejar como NULL,
# porque MySQL trata cada NULL como distinto dentro de una UNIQUE KEY
# compuesta, así que cada corrida generaría una fila nueva en
# dim_socioeconomica para los estudiantes sin NSE, en vez de reusar la
# existente. Eso duplica la dimensión y hace que el merge multiplique filas.
NSE_SIN_DATO = -1

COLUMNAS_CATEGORICAS_DIM = [
    "fami_estratovivienda", "fami_educacionpadre", "fami_educacionmadre",
    "fami_tieneinternet", "fami_tienecomputador", "fami_personashogar",
    "cole_naturaleza", "cole_calendario", "cole_area_ubicacion",
    "estu_depto_reside", "estu_mcpio_reside",
]

# Solo se traen de MySQL las columnas que realmente se usan en el análisis
# (socioeconómicas, puntajes, geografía/tiempo). La tabla raw tiene 97
# columnas de texto; traerlas todas gastaba mucha más RAM de la necesaria.
COLUMNAS_RAW_NECESARIAS = [
    "estu_consecutivo", "periodo",
    "estu_depto_reside", "estu_mcpio_reside",
    "cole_codigo_icfes", "cole_nombre_establecimiento",
    "cole_naturaleza", "cole_calendario", "cole_area_ubicacion",
    "fami_estratovivienda", "fami_educacionpadre", "fami_educacionmadre",
    "fami_tieneinternet", "fami_tienecomputador", "fami_personashogar",
    "estu_nse_individual", "estu_inse_individual",
    "punt_global", "punt_matematicas", "punt_lectura_critica",
    "punt_c_naturales", "punt_sociales_ciudadanas", "punt_ingles",
]

#Extracción
def cargar_raw(engine) -> pd.DataFrame:
    log.info("Extrayendo columnas necesarias desde '%s' usando Polars/connectorx...", RAW_TABLE)
    uri = engine.url.render_as_string(hide_password=False)
    uri = uri.replace("mysql+pymysql://", "mysql://")
    uri = uri.split("?")[0]  # connectorx no acepta parámetros extra (charset, etc.)
    columnas = ", ".join(COLUMNAS_RAW_NECESARIAS)
    query = f"SELECT {columnas} FROM {RAW_TABLE}"
    df = pl.read_database_uri(query=query, uri=uri).to_pandas()
    log.info("Filas extraídas: %s | Columnas: %d", f"{len(df):,}", df.shape[1])
    return df


#Limpieza y tipado
def a_numero(serie, tipo="float"):
    numerico = pd.to_numeric(serie, errors="coerce")
    return numerico.astype("Int64") if tipo == "int" else numerico


def limpiar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # cole_codigo_icfes se castea de una vez porque necesitamos saber,
    # antes de cualquier otra limpieza, quién se inscribió de forma
    # individual (sin colegio) para marcarlo en vez de perderlo.
    df["cole_codigo_icfes"] = a_numero(df["cole_codigo_icfes"], "int")
    mask_individual = df["cole_codigo_icfes"].isna()
    log.info("Estudiantes con inscripción individual (sin colegio): %d", int(mask_individual.sum()))

    # En vez de descartarlos, se les asigna un colegio centinela para que
    # entren al modelo estrella con una llave foránea válida y el estudio
    # siga reuniendo a todos los estudiantes, como debe ser.
    df.loc[mask_individual, "cole_nombre_establecimiento"] = "Sin colegio (inscripción individual)"
    df.loc[mask_individual, "cole_naturaleza"] = "No aplica"
    df.loc[mask_individual, "cole_calendario"] = "No aplica"
    df.loc[mask_individual, "cole_area_ubicacion"] = "No aplica"
    df["cole_codigo_icfes"] = df["cole_codigo_icfes"].fillna(COD_ICFES_SIN_COLEGIO).astype("Int64")

    # Texto: recortar espacios en columnas usadas como llaves de dimensión
    for col in COLUMNAS_CATEGORICAS_DIM:
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip()
            df[col] = df[col].fillna("No informa")
            df[col] = df[col].replace({"": "No informa"})

    # Numéricos de resultados (tabla de hechos)
    for col in ["punt_global", "punt_matematicas", "punt_lectura_critica",
                "punt_c_naturales", "punt_sociales_ciudadanas", "punt_ingles"]:
        df[col] = a_numero(df[col], "int")

    df["estu_inse_individual"] = a_numero(df["estu_inse_individual"], "float")
    df["estu_nse_individual"] = a_numero(df["estu_nse_individual"], "int")
    df["estu_nse_individual"] = df["estu_nse_individual"].fillna(NSE_SIN_DATO)

    df["periodo"] = df["periodo"].astype("string").str.strip()

    # Periodo ICFES en formato AAAAS (año + semestre), ej. 20251 -> 2025 / 1.
    # Solo se usa "anio" en el análisis; "semestre" se deja calculado por si
    # el esquema de dim_tiempo en MySQL ya la tiene como columna NOT NULL.
    df["anio"] = a_numero(df["periodo"].str[:4], "int")
    df["semestre"] = a_numero(df["periodo"].str[-1], "int")

    filas_antes = len(df)
    df = df.dropna(subset=["estu_consecutivo", "periodo"])
    log.info("Filas descartadas por llaves nulas (estudiante/periodo): %d",
              filas_antes - len(df))

    # Duplicados por doble inscripción (individual + institución en el
    # mismo periodo): se prioriza el registro institucional porque trae
    # más información real del colegio, y se descarta solo la fila
    # individual repetida de ESE estudiante. A los estudiantes que solo
    # tienen registro individual no los toca esta regla, porque no están
    # duplicados.
    es_individual = df["cole_codigo_icfes"] == COD_ICFES_SIN_COLEGIO
    df = df.assign(_es_individual=es_individual).sort_values("_es_individual")
    filas_antes = len(df)
    df = df.drop_duplicates(subset=["estu_consecutivo"], keep="first").drop(columns="_es_individual")
    log.info("Filas descartadas por doble inscripción (individual + institución): %d",
              filas_antes - len(df))

    duplicados_restantes = int(df["estu_consecutivo"].duplicated().sum())
    if duplicados_restantes:
        log.warning(
            "Quedan %d estu_consecutivo duplicados sin explicar. Revisar manualmente.",
            duplicados_restantes,
        )

    # Revisión: ¿algún colegio cambia de naturaleza/calendario/área entre
    # periodos? Si pasa, construir_dim_colegio se queda con el dato más
    # reciente en vez de uno al azar (ver más abajo).
    cambios_colegio = df.groupby("cole_codigo_icfes")[
        ["cole_naturaleza", "cole_calendario", "cole_area_ubicacion"]
    ].nunique()
    n_colegios_inconsistentes = (cambios_colegio > 1).any(axis=1).sum()
    log.info("Colegios con atributos distintos entre periodos: %d", n_colegios_inconsistentes)

    return df



#Construcción de dimensiones
def construir_dim_colegio(df: pd.DataFrame) -> pd.DataFrame:
    # Si un colegio tiene datos distintos entre periodos (cambió de
    # naturaleza/calendario), nos quedamos con el del periodo más
    # reciente en vez de con el primero que aparezca en la tabla raw.
    dim = (
        df[[
            "cole_codigo_icfes", "cole_nombre_establecimiento",
            "cole_naturaleza", "cole_calendario", "cole_area_ubicacion", "periodo",
        ]]
        .sort_values("periodo")
        .drop_duplicates(subset=["cole_codigo_icfes"], keep="last")
        .drop(columns="periodo")
    )
    return dim.rename(columns={"cole_codigo_icfes": "cole_cod_icfes"})


def construir_dim_ubicacion(df: pd.DataFrame) -> pd.DataFrame:
    return df[["estu_depto_reside", "estu_mcpio_reside"]].drop_duplicates()


def construir_dim_socioeconomica(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "fami_estratovivienda", "fami_educacionpadre", "fami_educacionmadre",
        "fami_tieneinternet", "fami_tienecomputador", "fami_personashogar",
        "estu_nse_individual",
    ]
    return df[cols].drop_duplicates()


def construir_dim_tiempo(df: pd.DataFrame) -> pd.DataFrame:
    return df[["periodo", "anio", "semestre"]].drop_duplicates(subset=["periodo"])


#carga idempotente de dimensiones
def insert_ignore(pd_table, conn, keys, data_iter):
    data = [dict(zip(keys, row)) for row in data_iter]
    stmt = mysql_insert(pd_table.table).values(data).prefix_with("IGNORE")
    conn.execute(stmt)


def cargar_dimension(engine, df_dim: pd.DataFrame, tabla: str) -> pd.DataFrame:
    df_dim = df_dim.where(pd.notnull(df_dim), None)
    if len(df_dim):
        df_dim.to_sql(
            tabla, con=engine, if_exists="append", index=False, method=insert_ignore
        )
    log.info("Dimensión '%s' actualizada (%d combinaciones evaluadas).", tabla, len(df_dim))
    return pd.read_sql(text(f"SELECT * FROM {tabla}"), con=engine)

#Construcción y carga de la tabla de hechos
def construir_fact(df, dim_colegio, dim_ubicacion, dim_socioeco, dim_tiempo) -> pd.DataFrame:
    colegio_keys = dim_colegio[["cole_cod_icfes", "id_colegio"]]
    ubicacion_keys = dim_ubicacion[["estu_depto_reside", "estu_mcpio_reside", "id_ubicacion"]]
    socioeco_keys = dim_socioeco[[
        "fami_estratovivienda", "fami_educacionpadre", "fami_educacionmadre",
        "fami_tieneinternet", "fami_tienecomputador", "fami_personashogar",
        "estu_nse_individual", "id_socioeconomico",
    ]]
    tiempo_keys = dim_tiempo[["periodo", "id_tiempo"]]

    fact = (
        df.merge(colegio_keys, left_on="cole_codigo_icfes", right_on="cole_cod_icfes", how="left")
          .merge(ubicacion_keys, on=["estu_depto_reside", "estu_mcpio_reside"], how="left")
          .merge(socioeco_keys, on=[
              "fami_estratovivienda", "fami_educacionpadre", "fami_educacionmadre",
              "fami_tieneinternet", "fami_tienecomputador", "fami_personashogar",
              "estu_nse_individual",
          ], how="left")
          .merge(tiempo_keys, on="periodo", how="left")
    )

    fact = fact.rename(columns={
        "punt_c_naturales": "punt_naturales",
        "estu_consecutivo": "bk_estu_consecutivo",
    })

    columnas_fact = [
        "punt_global", "punt_matematicas", "punt_lectura_critica", "punt_naturales",
        "punt_sociales_ciudadanas", "punt_ingles", "estu_inse_individual",
        "id_colegio", "id_socioeconomico", "id_tiempo", "id_ubicacion",
        "bk_estu_consecutivo",
    ]

    llaves_fk = ["id_colegio", "id_socioeconomico", "id_tiempo", "id_ubicacion"]
    sin_fk = fact[llaves_fk].isna().any(axis=1).sum()
    if sin_fk:
        log.warning(
            "%d filas quedaron sin alguna llave foránea (no calzaron con una "
            "dimensión) y serán descartadas.", sin_fk
        )

    return fact[columnas_fact].dropna(subset=llaves_fk)


def cargar_fact(engine, fact: pd.DataFrame):
    fact = fact.where(pd.notnull(fact), None)
    if len(fact):
        fact.to_sql(
            "fact_resultadossaber11", con=engine, if_exists="append",
            index=False, method=insert_ignore, chunksize=5000,
        )
    log.info("Tabla de hechos cargada: %d filas procesadas.", len(fact))


def main():
    engine = get_engine()

    df_raw = cargar_raw(engine)
    df = limpiar(df_raw)

    dim_colegio = cargar_dimension(engine, construir_dim_colegio(df), "dim_colegio")
    dim_ubicacion = cargar_dimension(engine, construir_dim_ubicacion(df), "dim_ubicacion")
    dim_socioeco = cargar_dimension(engine, construir_dim_socioeconomica(df), "dim_socioeconomica")
    dim_tiempo = cargar_dimension(engine, construir_dim_tiempo(df), "dim_tiempo")

    fact = construir_fact(df, dim_colegio, dim_ubicacion, dim_socioeco, dim_tiempo)
    cargar_fact(engine, fact)

    with engine.connect() as conn:
        total_fact = conn.execute(text("SELECT COUNT(*) FROM fact_resultadossaber11")).scalar()
    log.info("Transformación y carga finalizadas. Total filas en fact: %s", f"{total_fact:,}")


if __name__ == "__main__":
    main()