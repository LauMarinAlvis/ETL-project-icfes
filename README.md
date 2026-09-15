# Proyecto ETL - Histórico Resultados ICFES Saber 11

## **Descripción**
El objetivo de este proyecto es caracterizar el perfil socioeconómico de los estudiantes colombianos de educación media según su nivel de desempeño en las pruebas Saber 11 entre 2019 y 2025. A través de un enfoque descriptivo, la metodología contempla la exploración, limpieza y visualización de una base de datos histórica masiva que supera los 4.6 millones de registros. Con ello, se busca identificar las variables socioeconómicas predominantes en cada rango de resultados, así como analizar su evolución temporal a lo me largo del periodo establecido.

## **Justificación del Proyecto**
El análisis de datos en el sector educativo permite identificar brechas socioeconómicas y evaluar el rendimiento académico en diferentes regiones del país. Sin embargo, los datos abiertos crudos presentan problemas habituales de calidad: errores de codificación de texto (mojibake), inconsistencias en nombres de municipios, valores nulos y registros duplicados. Este proyecto surge de la necesidad de limpiar, estandarizar y modelar esta información bajo un esquema en estrella (Star Schema) optimizado para la consulta rápida y la integración con herramientas de analítica y Business Intelligence (BI).

## **Tecnologías Utilizadas**
* **Python (v3.13+):** Lenguaje base del pipeline de procesamiento.
* **Polars:** Motor de procesamiento vectorial de alto rendimiento para manipulación de datos masivos con bajo consumo de memoria.
* **PyArrow:** Backend de almacenamiento y soporte columnar para Polars.
* **ftfy (Fixes text for you):** Reparación automática de caracteres corruptos (Mojibake) y codificación de texto en departamentos y municipios.
* **VS Code / Jupyter Notebooks:** Entorno de desarrollo interactivo.
* **dbdiagram.io:** Diseño y documentación del modelo relacional.
Python (v3.13+): Lenguaje principal por su flexibilidad y amplio ecosistema para la manipulación de datos.  VS Code / Jupyter Notebooks: Entorno interactivo seleccionado para construir, probar y documentar el flujo de transformación celda por celda.  

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
* Carga optimizada del conjunto de datos histórico en formato CSV (`df_icfes_historico.csv`).
* Evaluación dimensional del dataset original: **4,629,768 filas × 94 columnas**.
* Diagnóstico inicial de nulos y verificación de esquemas (`schema`) sobre el bloque de variables asignadas.

### 2. Transformación y Limpieza de Datos
* **Llaves de negocio:** Conversión a tipo texto (`String`), limpieza de espacios en blanco (`strip_chars`) en `estu_consecutivo` y `cole_codigo_icfes`. Eliminación de sufijos flotantes (`.0`) e imputación de nulos/vacíos por `"SIN INFORMACION"`.
* **Dimensión Temporal:** Conversión de `periodo` a texto y extracción vectorial de la columna `anio` como entero de 32 bits (`Int32`).
* **Tratamiento Geográfico (Mojibake & Nulos):** Integración de `ftfy` mediante diccionarios en memoria para corregir problemas de codificación de caracteres en `estu_depto_reside` y `estu_mcpio_reside`. Normalización a mayúsculas e imputación de nulos.
* **Atributos del Colegio:** Homologación de texto a mayúsculas, unificación de valores categóricos (ej. cambio de `"URBANO"` a `"URBANA"`) e imputación de faltantes en `cole_naturaleza`, `cole_calendario` y `cole_area_ubicacion`.

### 3. Control e Inspección de Duplicados
* Evaluación de unicidad sobre la llave primaria `estu_consecutivo`.
* Inspección y filtrado de registros duplicados en pantalla mediante `is_duplicated()`.
* Deduplicación conservando la primera aparición válida (`keep="first"`), reduciendo el conjunto de datos de **4,629,768 a 4,629,766 registros únicos**.

### 4. Validación Final y Carga
* Re-verificación del reporte de nulos (confirmando **0 nulos** en las columnas procesadas).
* Preparación de las tablas de dimensiones y hechos para su posterior exportación a la base de datos relacional y herramientas de Business Intelligence (BI).