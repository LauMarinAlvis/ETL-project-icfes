import polars as pl
from sqlalchemy import create_engine
import ftfy

engine = create_engine("mysql+pymysql://root:root@localhost:3306/icfes_db")

def limpiar_socioeconomicas_polars(df: pl.DataFrame) -> pl.DataFrame:
    columnas_texto_bloque = [
        "fami_estratovivienda", "fami_educacionpadre", "fami_educacionmadre",
        "fami_tieneinternet", "fami_tienecomputador", "fami_personashogar"
    ]
    for c in columnas_texto_bloque:
        if c not in df.columns:
            continue
        valores_unicos = df.get_column(c).drop_nulls().unique().to_list()
        mapeo_encoding = {v: ftfy.fix_text(v) for v in valores_unicos if ftfy.fix_text(v) != v}
        if mapeo_encoding:
            df = df.with_columns(pl.col(c).replace(mapeo_encoding))

    return df.with_columns([
        pl.col("fami_estratovivienda").cast(pl.Utf8).str.strip_chars()
          .replace({"": None, "nan": None, "None": None, "Ubicar en otro estrato": None})
          .fill_null("Sin Estrato"),

        pl.col("fami_educacionpadre").cast(pl.Utf8).str.strip_chars().str.to_titlecase()
          .replace({"": None, "Nan": None, "None": None, "No Sabe": None})
          .fill_null("No Informa"),

        pl.col("fami_educacionmadre").cast(pl.Utf8).str.strip_chars().str.to_titlecase()
          .replace({"": None, "Nan": None, "None": None, "No Sabe": None})
          .fill_null("No Informa"),

        pl.col("fami_tieneinternet").cast(pl.Utf8).str.strip_chars()
          .replace({"Sí": "Si", "": None, "nan": None, "None": None})
          .fill_null("No"),

        pl.col("fami_tienecomputador").cast(pl.Utf8).str.strip_chars()
          .replace({"Sí": "Si", "": None, "nan": None, "None": None})
          .fill_null("No"),

        pl.col("fami_personashogar").cast(pl.Utf8).str.strip_chars()
          .replace({"": None, "nan": None, "None": None})
          .fill_null("No Informa"),

        pl.col("estu_nse_individual").cast(pl.Int64, strict=False)
    ])

def ejecutar_etl_completo():
    print("1. Extrayendo datos crudos desde MySQL...")
    df_raw = pl.read_database("SELECT * FROM raw_icfes_historico", connection=engine)
    
    # Normalizar a minúsculas
    df = df_raw.rename({c: c.lower() for c in df_raw.columns})
    if "cole_cod_icfes" in df.columns and "cole_codigo_icfes" not in df.columns:
        df = df.rename({"cole_cod_icfes": "cole_codigo_icfes"})

    print("2. Limpiando variables socioeconómicas...")
    df = limpiar_socioeconomicas_polars(df)

    print("3. Limpiando métricas y filtrando puntaje global...")
    cols_metricas = [
        "punt_global", "punt_matematicas", "punt_lectura_critica",
        "punt_naturales", "punt_sociales_ciudadanas", "punt_ingles", "estu_inse_individual"
    ]
    df = df.with_columns([pl.col(c).cast(pl.Float64, strict=False) for c in cols_metricas if c in df.columns])
    df = df.filter(pl.col("punt_global").is_not_null() & (pl.col("punt_global") >= 0) & (pl.col("punt_global") <= 500))

    print("4. Estandarizando llaves, tiempo, ubicación y colegio...")
    df = df.with_columns(
        estu_consecutivo = pl.col("estu_consecutivo").cast(pl.Utf8).str.strip_chars(),
        cole_codigo_icfes = pl.col("cole_codigo_icfes").cast(pl.Utf8).str.strip_chars().str.replace(r"\.0$", "").fill_null("SIN INFORMACION"),
        periodo = pl.col("periodo").cast(pl.Utf8).str.strip_chars(),
        anio = pl.col("periodo").cast(pl.Utf8).str.strip_chars().str.slice(0, 4).cast(pl.Int32),
        semestre = pl.col("periodo").cast(pl.Utf8).str.strip_chars().str.slice(4, 1).cast(pl.Int32),
        estu_depto_reside = pl.col("estu_depto_reside").cast(pl.Utf8).str.strip_chars().str.to_uppercase()
            .str.replace_all("Ã\x81", "Á").str.replace_all("Ã\x89", "É").str.replace_all("Ã\x8d", "Í")
            .str.replace_all("Ã\x93", "Ó").str.replace_all("Ã\x9a", "Ú").str.replace_all("Ã\x91", "Ñ")
            .fill_null("SIN INFORMACION").replace("", "SIN INFORMACION"),
        estu_mcpio_reside = pl.col("estu_mcpio_reside").cast(pl.Utf8).str.strip_chars().str.to_uppercase()
            .str.replace_all("Ã\x81", "Á").str.replace_all("Ã\x89", "É").str.replace_all("Ã\x8d", "Í")
            .str.replace_all("Ã\x93", "Ó").str.replace_all("Ã\x9a", "Ú").str.replace_all("Ã\x91", "Ñ")
            .fill_null("SIN INFORMACION").replace("", "SIN INFORMACION"),
        cole_nombre_establecimiento = pl.col("cole_nombre_establecimiento").cast(pl.Utf8).str.strip_chars().str.to_uppercase().fill_null("SIN INFORMACION"),
        cole_naturaleza = pl.col("cole_naturaleza").cast(pl.Utf8).str.strip_chars().str.to_uppercase().fill_null("SIN INFORMACION"),
        cole_calendario = pl.col("cole_calendario").cast(pl.Utf8).str.strip_chars().str.to_uppercase().fill_null("SIN INFORMACION"),
        cole_area_ubicacion = pl.col("cole_area_ubicacion").cast(pl.Utf8).str.strip_chars().str.to_uppercase().replace({"URBANO": "URBANA"}).fill_null("SIN INFORMACION")
    )

    # -------------------------------------------------------------
    # 5. CARGA DE TABLAS DIMENSIONALES
    # -------------------------------------------------------------
    print("5. Poblando Dimensiones en MySQL...")

    # Dim_Colegio
    dim_colegio = df.select([
        "cole_codigo_icfes", "cole_nombre_establecimiento", "cole_naturaleza", "cole_calendario", "cole_area_ubicacion"
    ]).unique()
    dim_colegio.rename({
        "cole_codigo_icfes": "COLE_COD_ICFES",
        "cole_nombre_establecimiento": "COLE_NOMBRE_ESTABLECIMIENTO",
        "cole_naturaleza": "COLE_NATURALEZA",
        "cole_calendario": "COLE_CALENDARIO",
        "cole_area_ubicacion": "COLE_AREA_UBICACION"
    }).to_pandas().to_sql("Dim_Colegio", engine, if_exists="append", index=False)

    # Dim_Socioeconomica
    dim_socio = df.select([
        "fami_estratovivienda", "fami_educacionpadre", "fami_educacionmadre",
        "fami_tieneinternet", "fami_tienecomputador", "fami_personashogar", "estu_nse_individual"
    ]).unique()
    dim_socio.rename({
        "fami_estratovivienda": "FAMI_ESTRATOVIVIENDA",
        "fami_educacionpadre": "FAMI_EDUCACIONPADRE",
        "fami_educacionmadre": "FAMI_EDUCACIONMADRE",
        "fami_tieneinternet": "FAMI_TIENEINTERNET",
        "fami_tienecomputador": "FAMI_TIENECOMPUTADOR",
        "fami_personashogar": "FAMI_PERSONASHOGAR",
        "estu_nse_individual": "ESTU_NSE_INDIVIDUAL"
    }).to_pandas().to_sql("Dim_Socioeconomica", engine, if_exists="append", index=False)

    # Dim_Tiempo
    dim_tiempo = df.select(["periodo", "anio", "semestre"]).unique()
    dim_tiempo.rename({
        "periodo": "PERIODO", "anio": "ANIO", "semestre": "SEMESTRE"
    }).to_pandas().to_sql("Dim_Tiempo", engine, if_exists="append", index=False)

    # Dim_Ubicacion
    dim_ubicacion = df.select(["estu_depto_reside", "estu_mcpio_reside"]).unique()
    dim_ubicacion.rename({
        "estu_depto_reside": "ESTU_DEPTO_RESIDE", "estu_mcpio_reside": "ESTU_MCPIO_RESIDE"
    }).to_pandas().to_sql("Dim_Ubicacion", engine, if_exists="append", index=False)

    # -------------------------------------------------------------
    # 6. CARGA DE TABLA DE HECHOS (Fact_ResultadosSaber11)
    # -------------------------------------------------------------
    print("6. Cruzando llaves foráneas y poblando Fact_ResultadosSaber11...")
    
    # Re-leer dimensiones con IDs auto-incrementales generados
    db_colegio = pl.read_database("SELECT id_colegio, COLE_COD_ICFES, COLE_NOMBRE_ESTABLECIMIENTO FROM Dim_Colegio", engine)
    db_socio = pl.read_database("SELECT id_socioeconomico, FAMI_ESTRATOVIVIENDA, FAMI_EDUCACIONPADRE, FAMI_EDUCACIONMADRE, FAMI_TIENEINTERNET, FAMI_TIENECOMPUTADOR, FAMI_PERSONASHOGAR FROM Dim_Socioeconomica", engine)
    db_tiempo = pl.read_database("SELECT id_tiempo, PERIODO FROM Dim_Tiempo", engine)
    db_ubicacion = pl.read_database("SELECT id_ubicacion, ESTU_DEPTO_RESIDE, ESTU_MCPIO_RESIDE FROM Dim_Ubicacion", engine)

    # Unir para obtener llaves foráneas
    df_fact = df.join(db_colegio, left_on=["cole_codigo_icfes", "cole_nombre_establecimiento"], right_on=["COLE_COD_ICFES", "COLE_NOMBRE_ESTABLECIMIENTO"], how="inner")
    df_fact = df_fact.join(db_socio, left_on=["fami_estratovivienda", "fami_educacionpadre", "fami_educacionmadre", "fami_tieneinternet", "fami_tienecomputador", "fami_personashogar"], right_on=["FAMI_ESTRATOVIVIENDA", "FAMI_EDUCACIONPADRE", "FAMI_EDUCACIONMADRE", "FAMI_TIENEINTERNET", "FAMI_TIENECOMPUTADOR", "FAMI_PERSONASHOGAR"], how="inner")
    df_fact = df_fact.join(db_tiempo, left_on="periodo", right_on="PERIODO", how="inner")
    df_fact = df_fact.join(db_ubicacion, left_on=["estu_depto_reside", "estu_mcpio_reside"], right_on=["ESTU_DEPTO_RESIDE", "ESTU_MCPIO_RESIDE"], how="inner")

    df_fact_final = df_fact.select([
        pl.col("punt_global").cast(pl.Int64).alias("PUNT_GLOBAL"),
        pl.col("punt_matematicas").cast(pl.Int64).alias("PUNT_MATEMATICAS"),
        pl.col("punt_lectura_critica").cast(pl.Int64).alias("PUNT_LECTURA_CRITICA"),
        pl.col("punt_naturales").cast(pl.Int64).alias("PUNT_NATURALES"),
        pl.col("punt_sociales_ciudadanas").cast(pl.Int64).alias("PUNT_SOCIALES_CIUDADANAS"),
        pl.col("punt_ingles").cast(pl.Int64).alias("PUNT_INGLES"),
        pl.col("estu_inse_individual").alias("ESTU_INSE_INDIVIDUAL"),
        pl.col("id_colegio"),
        pl.col("id_socioeconomico"),
        pl.col("id_tiempo"),
        pl.col("id_ubicacion"),
        pl.col("estu_consecutivo").alias("BK_ESTU_CONSECUTIVO")
    ])

    df_fact_final.to_pandas().to_sql(
        name="Fact_ResultadosSaber11",
        con=engine,
        if_exists="append",
        index=False,
        chunksize=10000
    )
    print("¡Proceso ETL completo finalizado exitosamente!")

if __name__ == "__main__":
    ejecutar_etl_completo()