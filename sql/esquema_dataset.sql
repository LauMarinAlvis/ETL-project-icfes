USE saber11_dw;

-- ----------------------------------------------------------------------------
-- Dim_Colegio
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_colegio (
    id_colegio INT AUTO_INCREMENT PRIMARY KEY,
    cole_cod_icfes INT NOT NULL,
    cole_nombre_establecimiento VARCHAR(255),
    cole_naturaleza VARCHAR(50),
    cole_calendario VARCHAR(20),
    cole_area_ubicacion VARCHAR(50),
    UNIQUE KEY uq_colegio (cole_cod_icfes)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------------------------------------------------------
-- Dim_Ubicacion
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_ubicacion (
    id_ubicacion INT AUTO_INCREMENT PRIMARY KEY,
    estu_depto_reside VARCHAR(100),
    estu_mcpio_reside VARCHAR(100),
    UNIQUE KEY uq_ubicacion (estu_depto_reside, estu_mcpio_reside)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------------------------------------------------------
-- Dim_Socioeconomica
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_socioeconomica (
    id_socioeconomico INT AUTO_INCREMENT PRIMARY KEY,
    fami_estratovivienda VARCHAR(50),
    fami_educacionpadre VARCHAR(100),
    fami_educacionmadre VARCHAR(100),
    fami_tieneinternet VARCHAR(10),
    fami_tienecomputador VARCHAR(10),
    fami_personashogar VARCHAR(20),
    estu_nse_individual INT,
    UNIQUE KEY uq_socioeco (
        fami_estratovivienda, fami_educacionpadre, fami_educacionmadre,
        fami_tieneinternet, fami_tienecomputador, fami_personashogar,
        estu_nse_individual
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------------------------------------------------------
-- Dim_Tiempo
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_tiempo (
    id_tiempo INT AUTO_INCREMENT PRIMARY KEY,
    periodo VARCHAR(10) NOT NULL,
    anio INT,
    semestre INT,
    UNIQUE KEY uq_tiempo (periodo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------------------------------------------------------
-- Fact_ResultadosSaber11
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_resultadossaber11 (
    id_resultado BIGINT AUTO_INCREMENT PRIMARY KEY,
    punt_global INT,
    punt_matematicas INT,
    punt_lectura_critica INT,
    punt_naturales INT,
    punt_sociales_ciudadanas INT,
    punt_ingles INT,
    estu_inse_individual FLOAT,
    id_colegio INT NOT NULL,
    id_socioeconomico INT NOT NULL,
    id_tiempo INT NOT NULL,
    id_ubicacion INT NOT NULL,
    bk_estu_consecutivo VARCHAR(50) NOT NULL,
    UNIQUE KEY uq_estu_consecutivo (bk_estu_consecutivo),
    CONSTRAINT fk_fact_colegio FOREIGN KEY (id_colegio) REFERENCES dim_colegio (id_colegio),
    CONSTRAINT fk_fact_socioeco FOREIGN KEY (id_socioeconomico) REFERENCES dim_socioeconomica (id_socioeconomico),
    CONSTRAINT fk_fact_tiempo FOREIGN KEY (id_tiempo) REFERENCES dim_tiempo (id_tiempo),
    CONSTRAINT fk_fact_ubicacion FOREIGN KEY (id_ubicacion) REFERENCES dim_ubicacion (id_ubicacion)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
