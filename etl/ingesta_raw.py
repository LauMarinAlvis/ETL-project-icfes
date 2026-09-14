from pathlib import Path
import polars as pl
from sqlalchemy import create_engine, text

BASE_DIR = Path(__file__).resolve().parent.parent
RUTA_CSV = BASE_DIR / "data" / "df_icfes_historico(full).csv"

engine = create_engine("mysql+pymysql://root:root@localhost:3306/icfes_db")

def cargar_raw():
    if not RUTA_CSV.exists():
        print(f"❌ ARCHIVO NO ENCONTRADO EN: {RUTA_CSV}")
        return

    print("Vaciando tabla 'raw_icfes_historico' antes de la ingesta...")
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE raw_icfes_historico;"))

    mapeo_columnas = {
        "estu_consecutivo": "ESTU_CONSECUTIVO",
        "periodo": "PERIODO",
        "estu_depto_reside": "ESTU_DEPTO_RESIDE",
        "estu_mcpio_reside": "ESTU_MCPIO_RESIDE",
        "cole_cod_icfes": "COLE_COD_ICFES",
        "cole_codigo_icfes": "COLE_COD_ICFES",
        "cole_nombre_establecimiento": "COLE_NOMBRE_ESTABLECIMIENTO",
        "cole_naturaleza": "COLE_NATURALEZA",
        "cole_calendario": "COLE_CALENDARIO",
        "cole_area_ubicacion": "COLE_AREA_UBICACION",
        "fami_estratovivienda": "FAMI_ESTRATOVIVIENDA",
        "fami_educacionpadre": "FAMI_EDUCACIONPADRE",
        "fami_educacionmadre": "FAMI_EDUCACIONMADRE",
        "fami_tieneinternet": "FAMI_TIENEINTERNET",
        "fami_tienecomputador": "FAMI_TIENECOMPUTADOR",
        "fami_personashogar": "FAMI_PERSONASHOGAR",
        "estu_nse_individual": "ESTU_NSE_INDIVIDUAL",
        "estu_inse_individual": "ESTU_INSE_INDIVIDUAL",
        "punt_global": "PUNT_GLOBAL",
        "punt_matematicas": "PUNT_MATEMATICAS",
        "punt_lectura_critica": "PUNT_LECTURA_CRITICA",
        "punt_naturales": "PUNT_NATURALES",
        "punt_sociales_ciudadanas": "PUNT_SOCIALES_CIUDADANAS",
        "punt_ingles": "PUNT_INGLES"
    }

    print("🚀 Iniciando ingesta por lotes a MySQL desde CSV...")
    lazy_reader = pl.scan_csv(
        str(RUTA_CSV), 
        ignore_errors=True, 
        low_memory=True,
        truncate_ragged_lines=True
    )
    
    total_filas = 0
    for batch in lazy_reader.collect_batches(chunk_size=100_000):
        cols_lower = {c: c.lower() for c in batch.columns}
        df_lote = batch.rename(cols_lower)
        
        cols_presentes = {c: mapeo_columnas[c] for c in df_lote.columns if c in mapeo_columnas}
        df_lote = df_lote.select(list(cols_presentes.keys())).rename(cols_presentes)
        df_lote = df_lote.select([pl.col(c).cast(pl.Utf8) for c in df_lote.columns])
        
        df_lote.to_pandas().to_sql(
            name="raw_icfes_historico",
            con=engine, 
            if_exists="append", 
            index=False,
            method="multi",
            chunksize=10_000
        )
        total_filas += len(df_lote)
        print(f"Lote insertado. Total acumulado: {total_filas:,} filas.")

    print(f"\n✅ ¡Ingesta masiva finalizada exitosamente! Total exacto: {total_filas:,} filas.")

if __name__ == "__main__":
    cargar_raw()