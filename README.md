# Proyecto ETL - Histórico Resultados ICFES Saber 11

## **Descripción**
El objetivo de este proyecto es caracterizar el perfil socioeconómico de los estudiantes de educación media del departamento del Valle del Cauca según su nivel de desempeño en las pruebas Saber 11 durante el año 2025. A través de un enfoque descriptivo y una arquitectura de datos escalable, la metodología contempla la extracción, limpieza, transformación y carga (ETL) de un volumen de **661.889 registros**. Con ello, se busca identificar las variables socioeconómicas y el equipamiento tecnológico del hogar predominantes en cada rango de resultados, así como analizar la distribución de estas características y brechas educativas en los distintos municipios de la región.

## **Justificación del Proyecto**
El análisis de datos en el sector educativo es fundamental para visibilizar disparidades socioeconómicas y respaldar decisiones de política pública alineadas con el **ODS 4 (Educación de Calidad, Meta 4.5)**. Sin embargo, los microdatos abiertos crudos del ICFES presentan problemas habituales de calidad: errores de codificación de texto (*mojibake*), inconsistencias en nombres de municipios, valores nulos e inscripciones duplicadas. Este proyecto surge de la necesidad de sanear, estandarizar y estructurar esta información bajo un modelo relacional en estrella (*Star Schema*) optimizado para la consulta rápida, la garantía de integridad referencial y la integración directa con herramientas de analítica y Business Intelligence (BI).

## **Tecnologías Utilizadas**
* **Python (v3.13+):** Lenguaje base del pipeline de procesamiento.
* **Polars:** Motor de procesamiento vectorial de alto rendimiento para manipulación de datos masivos con bajo consumo de memoria.
* **PyArrow:** Backend de almacenamiento y soporte columnar para Polars.
* **ftfy (Fixes text for you):** Reparación automática de caracteres corruptos (Mojibake) y codificación de texto en departamentos y municipios.
* **VS Code / Jupyter Notebooks:** VS Code / Jupyter Notebooks: Entorno interactivo seleccionado para construir, probar y documentar el flujo de transformación celda por celda, asi comoo para visualizar el EDA.
* **dbdiagram.io:** Diseño y documentación del modelo relacional.  
* **Docker:** Para la contenedorización del entorno de base de datos.
* **MySQL (v8.0):** El motor relacional que aloja el Data Warehouse (saber11_dw).
* **SQLAlchemy y PyMySQL:** Los conectores fundamentales que usamos para interactuar de forma segura entre Python y MySQL.

## **Arquitectura de Datos (Star Schema)**
El procesamiento transforma el dataset plano original en las siguientes estructuras relacionales:

* **Dim_Colegio:** Atributos de las instituciones (código ICFES, nombre, naturaleza, calendario, ubicación).
* **Dim_Ubicacion:** Limpieza de codificación (UTF-8/Mojibakes) y estandarización de departamento y municipio de residencia.
* **Dim_Socioeconomica:** Variables del entorno del estudiante (estrato, educación de padres, acceso a internet/computador).
* **Dim_Tiempo:** Periodo, año y semestre de presentación de la prueba.
* **Fact_ResultadosSaber11:** Tabla de hechos central con llaves foráneas numéricas y puntajes por área (Matemáticas, Lectura Crítica, Naturales, Sociales, Inglés, Global).

---
### **Esquema Estrella - Tabla de Hechos y Dimensiones**

![Esquema Estrella Mano](Esquema_project_ETL_1_ICFES_original.png)
![Esquema Estrella Digitalizada](Esquema_project_ETL_1_ICFES.png)

---

## **Flujo de Trabajo (Pipeline ETL)**

### 1. Extracción e Inspección Inicial
* Carga optimizada del conjunto de datos en formato CSV (`DB_ICFE2025.csv`).
* Evaluación dimensional del dataset de origen: **661,889 filas × 94 columnas**.
* Diagnóstico inicial de nulos y verificación de esquemas (*schema*) sobre el bloque de variables seleccionadas para el análisis socioeconómico y académico.

### 2. Transformación y Limpieza de Datos
* **Llaves de negocio y Centinelas:** Conversión a tipo texto (`String`), limpieza de espacios en blanco (`strip_chars`) en `estu_consecutivo` y `cole_codigo_icfes`. Asignación de valor centinela `-1` a estudiantes de inscripción individual (sin colegio) y a registros socioeconómicos faltantes para preservar la integridad referencial en la base de datos.
* **Gestión de Duplicados:** Identificación y resolución de inscripciones dobles sobre la clave de negocio `estu_consecutivo`, priorizando la retención del registro vinculado a una institución educativa sobre el registro de inscripción individual.
* **Tratamiento Geográfico (Mojibake & Nulos):** Integración de `ftfy` para corregir problemas de codificación de caracteres en `estu_depto_reside` y `estu_mcpio_reside`. Normalización a mayúsculas e imputación de valores faltantes.
* **Atributos del Colegio:** Homologación de texto a mayúsculas, unificación de valores categóricos (ej. cambio de `"URBANO"` a `"URBANA"`) e imputación de nulos en `cole_naturaleza`, `cole_calendario` y `cole_area_ubicacion`.
* **Dimensión Socioeconómica:** Estandarización de variables del entorno familiar (`fami_estratovivienda`, `fami_tieneinternet`, `fami_tienecomputador`, `fami_educacionpadre`, `fami_educacionmadre`) e imputación sistemática con `"SIN INFORMACION"`.
* **Casteo de Métricas y Tiempo:** Extracción vectorial de la columna `anio` (`Int32`), formateo numérico entero (`Int64`) para los puntajes por asignatura/global y casteo a flotante (`Float64`) para el Índice Socioeconómico Individual (`estu_inse_individual`).

### 3. Control e Inspección de Duplicados
* **Evaluación de Unicidad:** Escaneo estricto sobre la clave de negocio `estu_consecutivo` mediante expresiones vectoriales en Polars (`is_duplicated()`).
* **Criterio de Deduplicación:** Eliminación de inscripciones dobles en el mismo periodo para evitar el sesgo en el cálculo de métricas socioeconómicas (INSE, estrato) y la duplicación en el conteo de evaluaciones.
* **Garantía de Integridad:** Consolidación de **661.889 registros únicos**, garantizando 0 errores de clave foránea (*Foreign Keys*) al cargar la tabla de hechos `Fact_ResultadosSaber11`.

### 4. Carga e Integración en Data Warehouse
* **Verificación de Calidad:** Re-verificación del reporte de nulos (confirmando **0 nulos** en variables críticas) y validación de tipos de datos previo al cargue.
* **Carga Idempotente:** Inserción de datos hacia el Data Warehouse en MySQL 8.0 mediante sentencias `INSERT IGNORE`, garantizando la reejecución segura del script sin duplicación de registros.
* **Poblado del Modelo Estrella:** Carga relacional de las 4 tablas de dimensiones (`dim_colegio`, `dim_ubicacion`, `dim_socioeconomica`, `dim_tiempo`) y la tabla de hechos (`Fact_ResultadosSaber11`), garantizando integridad referencial perfecta (0 errores en *Foreign Keys*).

### 5. Instrucciones de Ejecución (Despliegue)

Para desplegar y reproducir el proyecto localmente desde cero, sigue estos pasos en estricto orden:

**1. Preparar el Entorno Virtual**
Clona el repositorio, crea el entorno virtual e instala las dependencias:
\`\`\`bash
python -m venv .venv
.venv\Scripts\activate  # En Windows
pip install -r requirements.txt
\`\`\`

**2. Configurar Archivos de Datos y Credenciales**
Descarga los archivos externos e insértalos en las rutas correspondientes del proyecto:
* **Archivo de variables de entorno (`.env`):** [Descargar aquí](https://drive.google.com/file/d/1wik8grKRmrZdb-UPixxdBOd_mEBAS2CL/view?usp=sharing) $\rightarrow$ Ubicar en la **raíz** del proyecto.
* **Dataset Histórico (CSV):** [Descargar aquí](https://drive.google.com/file/d/1PlBcRP9fjNIoU1gZ3i4sbc1OC1j7lixB/view?usp=sharing) $\rightarrow$ Guardar en la carpeta `data/` con el nombre `DB_ICFE2025.csv` (`data/DB_ICFE2025.csv`).

**3. Levantar la Infraestructura (Docker)**
Inicia el contenedor de la base de datos MySQL en segundo plano:
\`\`\`bash
docker compose up -d
\`\`\`

**4. Ejecutar el Pipeline ETL (Orden Secuencial)**

* **Paso A - Ingesta Raw:** Carga la base de datos cruda desde el CSV a la tabla staging de MySQL.
  \`\`\`bash
  python etl/ingesta_raw.py --csv data/DB_ICFE2025.csv
  \`\`\`

* **Paso B - Perfilamiento:** Revisa el estado, esquemas y métricas iniciales del dataset crudo.
  \`\`\`bash
  python etl/perfilamiento_raw.py
  \`\`\`

* **Paso C - Transformación y Carga (Star Schema):** Aplica limpieza de texto (`ftfy`), reglas de negocio y puebla las dimensiones y la tabla de hechos.
  \`\`\`bash
  python etl/transformacion.py
  \`\`\`

**5. Ejecutar el Análisis Exploratorio (EDA)**
Abre el cuaderno `EDA_Saber11_Valle2025.ipynb` en VS Code o Jupyter, asegúrate de tener seleccionado el kernel `.venv`, y presiona **"Run All"** para consultar el Data Warehouse y generar las visualizaciones.

### 6. EDA- Análisis Exploratorio de Dato
Definimos las 6 relaciones clave entre variables socioeconómicas, institucionales y los resultados académicos del departamento del Valle del Cauca (2025). Estas relaciones se encuentran estructuradas estratégicamente por su nivel de complejidad analítica, lo que facilitará su integración directa en el Dashboard interactivo y permitirá una rigurosa validación de las hipótesis planteadas en la investigación. De este modo, el sistema no solo describirá el panorama educativo, sino que servirá como una herramienta analítica avanzada para identificar los factores críticos que impactan el rendimiento escolar en la región.

1. Usamos la relación de **Estrato Socioeconómico vs. Puntaje Global**, cruzamos las variables FAMI_ESTRATOVIVIENDA y PUNT_GLOBAL para ayudarnos a entender ¿Cómo varía el promedio del puntaje global a medida que se incrementa el estrato de la vivienda del estudiante?: la inclusión de este análisis permite establecer la línea base fundamental para medir el impacto y la desigualdad económica directa sobre el rendimiento académico general en la región.

Gráfica: Gráfico de barras con promedio y desviación estándar por estrato.
![Grafica barras](media_puntajeGlobal_vs_estrato.png)

2. Usamos la relación de **Naturaleza del Colegio vs. Rendimiento Académico**, ruzamos las variables COLE_NATURALEZA y PUNT_GLOBAL para ayudarnos a entender ¿Cuál es la magnitud de la brecha de puntaje entre las instituciones públicas y privadas del departamento?: la inclusión de este análisis permite caracterizar la diferencia en el rendimiento del sistema educativo del Valle del Cauca según la administración del establecimiento.

Gráfica: Diagrama de caja y bigotes (Boxplot) comparativo entre sectores.

3. Usamos la relación de **Índice de Brecha Digital vs. Puntaje Global**, cruzamos las variables FAMI_TIENEINTERNET, FAMI_TIENECOMPUTADOR y PUNT_GLOBAL para ayudarnos a entender ¿Qué diferencia de puntaje existe entre estudiantes con acceso tecnológico completo frente a quienes enfrentan desconexión digital?: la inclusión de este análisis permite evaluar el impacto real de la conectividad y los equipos de cómputo en el hogar, diferenciando los perfiles de acceso tecnológico.

Gráfica: Diagrama de cajas agrupadas (Boxplot) por perfil de conectividad.

4. Usamos la relación de **Sensibilidad por Asignatura según el Índice Socioeconómico (INSE)**, cruzamos la variable ESTU_INSE_INDIVIDUAL con los puntajes por materia (PUNT_MATEMATICAS, PUNT_LECTURA_CRITICA, PUNT_NATURALES, PUNT_SOCIALES_CIUDADANAS, PUNT_INGLES) para ayudarnos a entender ¿Cuál asignatura presenta mayor vulnerabilidad o correlación respecto al índice socioeconómico del estudiante?: la inclusión de este análisis permite determinar si las competencias cuantitativas, científicas o de segunda lengua son más sensibles a las condiciones económicas que las del lenguaje o ciudadanas.

Gráfica: Matriz de correlación (Heatmap).

5. Usamos la relación de **Densidad del Hogar vs. Desempeño Académico**, cruzamos las variables FAMI_PERSONASHOGAR, FAMI_ESTRATOVIVIENDA y PUNT_GLOBAL para ayudarnos a entender ¿El tamaño de la familia incide de forma distinta en el puntaje global dependiendo del estrato socioeconómico?: la inclusión de este análisis permite identificar si el número de integrantes en el hogar afecta la concentración y los hábitos de estudio de forma diferenciada según el nivel socioeconómico.

Gráfica: Gráfico de líneas o puntos interconectados por estrato.

6. Usamos la relación de **Vulnerabilidad Digital Territorial por Municipio**, cruzamos las variables ESTU_MCPIO_RESIDE, FAMI_TIENEINTERNET y PUNT_GLOBAL para ayudarnos a entender ¿Cuáles municipios del Valle del Cauca presentan los rendimientos académicos más bajos según el acceso a internet y qué tanto incide la brecha de conectividad en el resultado de cada localidad?: la inclusión de este análisis permite diagnosticar territorialmente si la falta de internet actúa como un factor determinante de rezago educativo en zonas específicas del departamento, identificando las áreas con mayor necesidad de intervención.

Gráfica: Mapa de calor (Heatmap) matricial donde el eje vertical contiene los municipios del Valle del Cauca, el eje horizontal el acceso a internet (SI / NO) y el color/valor representa el PUNT_GLOBAL promedio.