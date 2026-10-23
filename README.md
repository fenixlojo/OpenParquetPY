# OpenParquets

Visor local de archivos Parquet. Requiere Python 3.10 o superior.

## Abrir

En Windows, doble clic en `start.bat`. La primera ejecución instala DuckDB y luego abre el navegador.

Alternativamente:

```powershell
python -m pip install -r requirements.txt
python app.py
```

Abrí http://127.0.0.1:8765. Cerrá el servidor con Ctrl+C.

Seleccioná o arrastrá archivos, o pegá su ruta local. Para archivos grandes conviene usar la ruta: las consultas leen el archivo directamente y devuelven páginas de hasta 500 filas. La búsqueda y el ordenamiento pueden demorar en archivos grandes. El límite de memoria de DuckDB es 512 MB; algunas operaciones pueden usar disco temporal o fallar si no hay recursos suficientes.

Incluye búsqueda literal en todas las columnas, orden ascendente/descendente, paginación, varias pestañas de archivo mediante selector, esquema con tipos y nulabilidad, tamaño y grupos de filas. Las celdas se pueden abrir para leer el valor completo. La nulabilidad refleja el esquema informado por DuckDB, no un conteo de valores nulos.

Los datos se procesan localmente. Los archivos seleccionados se copian a una carpeta temporal que se limpia al cerrar normalmente el servidor. Las rutas locales se leen directamente. No requiere servicios externos.

Puerto alternativo: `python app.py --port 8766`. Para iniciar sin navegador: `python app.py --no-browser`.

## Generar Parquet a partir de CSV o Excel

El botón **Generar Parquet**, junto a **Abrir archivo**, acepta CSV, TSV, XLSX, XLS y XLSM. Seleccioná el archivo y una hoja si es Excel. Podés indicar si la primera fila contiene encabezados y conservar todas las columnas como texto; si no, DuckDB infiere tipos a partir de todos los datos. Los CSV admiten separadores coma, punto y coma, tabulador o barra vertical y codificación UTF-8 o Windows-1252.

La barra muestra el avance por etapas reales: lectura, compresión, preparación y apertura. La conversión corre en segundo plano en el servidor local, con hasta dos conversiones simultáneas. Al terminar se solicita la descarga de un Parquet ZSTD y se abre automáticamente en el visor. Queda un resumen con tamaños de origen/destino, ahorro en bytes y porcentaje, o aumento cuando el resultado es mayor. Para Excel, la comparación usa el libro completo aunque el resultado solo contiene la hoja seleccionada.

Se exportan los valores de las celdas; no estilos, gráficos ni macros. Las filas completamente vacías de Excel se omiten. Las fórmulas no se recalculan: se usan resultados guardados y se rechazan los errores detectados y las fórmulas XLSX/XLSM sin resultado guardado. Los identificadores numéricos que necesitan ceros de formato deben convertirse a texto en Excel antes de importarlos. No se modifica el archivo original.

La conversión usa `openpyxl` para XLSX/XLSM y `xlrd` para XLS. `start.bat` instala las dependencias faltantes; para actualizar manualmente: `python -m pip install -r requirements.txt`. Los archivos de origen se copian al directorio temporal local y se eliminan al cerrar el conversor. Los Parquets generados y sus enlaces de descarga permanecen hasta cerrar el servidor. El navegador administra la carpeta de descarga según sus preferencias; si no guarda automáticamente, usá el enlace del resumen.

Límite de carga: 2 GB. El límite de memoria de DuckDB es 512 MB, pero la lectura de Excel también requiere memoria de Python y puede fallar antes. No hay un tamaño máximo de Excel garantizado para cualquier equipo.

Pruebas de conversión y SQL: `python -m unittest -v test_conversion test_sql`.

## Consultas SQL

Abrí un archivo y elegí la pestaña **SQL**. `SELECT` y `FROM parquet` están fijos. En **Columnas SQL** dejá `*` o escribí columnas y expresiones. En **Cláusulas SQL** podés escribir:

```sql
WHERE persona_id = 42325
ORDER BY persona_id DESC
```

El botón **Ejecutar consulta** o Ctrl / Cmd + Enter aplica la consulta. La columna usada debe existir en el archivo. El resultado tiene sus propias columnas y paginación; las modificaciones del editor no se aplican hasta ejecutar. **Ver todo** restaura la consulta completa; **Contar filas** ejecuta `COUNT(*) AS total`. La pestaña Datos permite volver al contenido original. Al cambiar de archivo se reinicia el editor.

También se admiten agregaciones: columnas `persona_id, COUNT(*) AS cantidad`; cláusulas `GROUP BY persona_id HAVING COUNT(*) > 1 ORDER BY cantidad DESC LIMIT 20`.

Es SQL de DuckDB, con la sintaxis común de filtros de MySQL e identificadores entre backticks. No emula todas las funciones y reglas de MySQL. Se permiten SELECT, expresiones, WHERE, GROUP BY, HAVING, ORDER BY y LIMIT/OFFSET; no subconsultas, JOIN, UNION, otras tablas, escrituras ni múltiples sentencias. No uses comentarios, punto y coma ni escapes con barra invertida. El texto se escribe entre comillas simples y los apóstrofos se duplican: `'O''Brien'`. Los identificadores especiales van entre comillas dobles o backticks.

El Parquet no se modifica. Las consultas locales restringen el acceso de archivos al Parquet seleccionado y tienen un tiempo máximo aproximado de 30 segundos y el límite de memoria del visor. Los módulos `viewer.js` y `sql.js` se sirven desde la app local; no requieren Node.js.

Pruebas de API, filtros, paginación, agrupaciones y restricciones: `python -m unittest -v test_sql`.
