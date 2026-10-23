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
