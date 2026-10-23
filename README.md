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
