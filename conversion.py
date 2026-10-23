"""CSV / Excel to ZSTD Parquet, with background jobs and real phase updates."""
import csv
from datetime import date, datetime, time
from pathlib import Path
import threading
import uuid
import duckdb

SOURCES = {}
JOBS = {}
LOCK = threading.Lock()
SLOTS = threading.BoundedSemaphore(2)


def inspect_source(path, name):
    suffix = Path(name).suffix.lower()
    sheets = []
    if suffix in ('.xlsx', '.xlsm'):
        import openpyxl
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            sheets = book.sheetnames
        finally:
            book.close()
    elif suffix == '.xls':
        import xlrd
        book = xlrd.open_workbook(path, on_demand=True)
        try:
            sheets = book.sheet_names()
        finally:
            book.release_resources()
    elif suffix not in ('.csv', '.tsv'):
        raise ValueError('Elegí un CSV, TSV o Excel (.xlsx, .xls, .xlsm).')
    token = uuid.uuid4().hex
    source = dict(path=Path(path), name=name, suffix=suffix, sheets=sheets, excel=bool(sheets))
    with LOCK:
        SOURCES[token] = source
    return dict(token=token, sheets=sheets, excel=bool(sheets))


def discard_source(token):
    with LOCK:
        source = SOURCES.get(token)
        if not source or source.get('busy'):
            return
        SOURCES.pop(token)
    source['path'].unlink(missing_ok=True)


def text(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (datetime, date, time)):
        return value.isoformat(sep=' ') if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def detect_delimiter(value):
    value = value.lstrip('\ufeff\r\n')
    counts = {',': 0, ';': 0, '\t': 0, '|': 0}
    quoted, i = False, 0
    while i < len(value):
        ch = value[i]
        if ch == '"':
            if quoted and value[i:i+2] == '""':
                i += 1
            else:
                quoted = not quoted
        elif not quoted:
            if ch in '\n\r' and i > 0:
                break
            if ch in counts:
                counts[ch] += 1
        i += 1
    return max(counts, key=counts.get)


def excel_rows(source, sheet):
    if sheet not in source['sheets']:
        raise ValueError('Elegí una hoja válida del Excel.')
    if source['suffix'] == '.xls':
        import xlrd
        book = xlrd.open_workbook(source['path'], on_demand=True)
        try:
            tab = book.sheet_by_name(sheet)
            for r in range(tab.nrows):
                values = []
                for c in range(tab.ncols):
                    cell = tab.cell(r, c)
                    if cell.ctype == xlrd.XL_CELL_ERROR:
                        raise ValueError('La hoja contiene una celda con error de Excel.')
                    value = xlrd.xldate_as_datetime(cell.value, book.datemode) if cell.ctype == xlrd.XL_CELL_DATE else bool(cell.value) if cell.ctype == xlrd.XL_CELL_BOOLEAN else cell.value
                    values.append(text(value))
                yield values
        finally:
            book.release_resources()
    else:
        import openpyxl
        cached = openpyxl.load_workbook(source['path'], read_only=True, data_only=True)
        formulas = None
        try:
            formulas = openpyxl.load_workbook(source['path'], read_only=True, data_only=False)
            for row, formula_row in zip(cached[sheet].iter_rows(), formulas[sheet].iter_rows()):
                values = []
                for cell, formula in zip(row, formula_row):
                    if cell.data_type == 'e':
                        raise ValueError('La hoja contiene una celda con error de Excel.')
                    if formula.data_type == 'f' and cell.value is None:
                        raise ValueError('Hay fórmulas sin resultado guardado. Abrí el Excel, recalculá y guardalo antes de convertir.')
                    values.append(text(cell.value))
                yield values
        finally:
            cached.close()
            if formulas:
                formulas.close()


def convert_file(source, options, output, progress):
    """No input files are changed. Temporary CSV is deleted on success or failure."""
    intermediate = output.with_suffix('.csv')
    try:
        input_path = source['path']
        progress(0, 'Leyendo los datos de origen…')
        if source['excel']:
            count = 0
            with intermediate.open('w', encoding='utf-8', newline='') as dest:
                writer = csv.writer(dest, quoting=csv.QUOTE_ALL)
                for row_number, row in enumerate(excel_rows(source, options.get('sheet', '')), 1):
                    if any(value != '' for value in row):
                        writer.writerow(row)
                        count += 1
                    if row_number % 1000 == 0:
                        progress(0, f'Leyendo hoja: fila {row_number}…')
            if not count:
                raise ValueError('La hoja seleccionada está vacía.')
            input_path = intermediate
        elif options.get('encoding') == 'windows-1252':
            with source['path'].open('r', encoding='cp1252', newline='') as src, intermediate.open('w', encoding='utf-8', newline='') as dest:
                while chunk := src.read(1024**2):
                    dest.write(chunk)
            input_path = intermediate
        progress(1, 'Comprimiendo datos como Parquet…')
        with input_path.open('r', encoding='utf-8-sig', newline='') as preview:
            delimiter = detect_delimiter(preview.read(262144))
        with duckdb.connect() as db:
            db.execute("SET memory_limit='512MB'")
            db.execute('SET threads=2')
            db.execute('COPY (SELECT * FROM read_csv($1, header=$2, all_varchar=$3, delim=$5, quote=\'"\', escape=\'"\', sample_size=-1, ignore_errors=false, strict_mode=true)) TO $4 (FORMAT PARQUET, COMPRESSION ZSTD)', [str(input_path), bool(options.get('header', True)), bool(options.get('allText', False)), str(output), delimiter])
        progress(2, 'Parquet generado. Comprobando la estructura…')
        return output
    except Exception:
        output.unlink(missing_ok=True)
        raise
    finally:
        intermediate.unlink(missing_ok=True)


def start_job(token, options, temp_directory, register):
    with LOCK:
        source = SOURCES.get(token)
        if not source:
            raise ValueError('El archivo de origen ya está cerrado. Volvé a seleccionarlo.')
        if source.get('busy'):
            raise ValueError('Este archivo ya se está convirtiendo.')
        if not SLOTS.acquire(blocking=False):
            raise ValueError('Ya hay dos conversiones en curso. Esperá a que terminen.')
        source['busy'] = True
        job_id = uuid.uuid4().hex
        JOBS[job_id] = dict(state='running', step=0, label='Preparando conversión…')

    def update(step, label):
        with LOCK:
            JOBS[job_id].update(step=step, label=label)

    def work():
        output = Path(temp_directory) / (job_id + '.parquet')
        try:
            convert_file(source, options, output, update)
            import re
            sheet = '_' + re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', options.get('sheet', '')) if source['excel'] else ''
            name = Path(source['name']).stem + sheet + '.parquet'
            info = register(output, name)
            result = dict(info=info, originalSize=source['path'].stat().st_size, outputSize=output.stat().st_size, name=name, downloadUrl='/api/download?id='+info['id'])
            with LOCK:
                JOBS[job_id].update(state='complete', step=3, label='Listo para descargar y abrir.', result=result)
        except Exception as error:
            output.unlink(missing_ok=True)
            with LOCK:
                JOBS[job_id].update(state='error', error=str(error))
        finally:
            with LOCK:
                source['busy'] = False
            SLOTS.release()

    threading.Thread(target=work, daemon=True).start()
    return dict(job=job_id)


def job_status(job_id):
    with LOCK:
        if job_id not in JOBS:
            raise ValueError('Conversión no encontrada.')
        return dict(JOBS[job_id])
