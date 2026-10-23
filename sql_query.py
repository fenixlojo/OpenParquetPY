"""A constrained, read-only SELECT editor over the selected Parquet file."""
import re
import threading

FORBIDDEN = re.compile(r'\b(select|from|join|union|intersect|except|with|into|copy|insert|update|delete|drop|alter|create|attach|detach|install|load|pragma|set|call|export|import)\b', re.I)


def normalize_fragment(text):
    output, words = [], []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "'\"`":
            delimiter, value, closed = ch, [], False
            i += 1
            while i < len(text):
                if text[i] == '\\':
                    raise ValueError('Usá comillas duplicadas para escapar texto, sin barras invertidas.')
                if text[i] == delimiter:
                    if i + 1 < len(text) and text[i + 1] == delimiter:
                        value.append(delimiter)
                        i += 2
                        continue
                    i += 1
                    closed = True
                    break
                value.append(text[i])
                i += 1
            if not closed:
                raise ValueError('Hay comillas sin cerrar en la consulta.')
            quote = "'" if delimiter == "'" else '"'
            output.append(quote + ''.join(value).replace(quote, quote * 2) + quote)
            words.append(' ')
            continue
        if ch in ';$\\' or text[i:i + 2] in ('--', '/*'):
            raise ValueError('Usá una sola consulta, sin punto y coma, comentarios ni escapes con barra invertida.')
        output.append(ch)
        words.append(ch)
        i += 1
    if FORBIDDEN.search(''.join(words)):
        raise ValueError('SELECT y FROM parquet ya están fijos. Escribí columnas y cláusulas; no se admiten subconsultas ni cambios de datos.')
    return ''.join(output).strip()


def build_query(projection='*', clauses=''):
    if not isinstance(projection, str) or not isinstance(clauses, str):
        raise ValueError('Las columnas y cláusulas deben ser texto.')
    if len(projection) + len(clauses) > 20000:
        raise ValueError('La consulta es demasiado larga (máximo 20.000 caracteres).')
    columns = normalize_fragment(projection) or '*'
    tail = normalize_fragment(clauses)
    if tail and not re.match(r'^(where\b|group\s+by\b|having\b|order\s+by\b|limit\b|offset\b)', tail, re.I):
        raise ValueError('Las cláusulas deben empezar con WHERE, GROUP BY, HAVING, ORDER BY, LIMIT u OFFSET.')
    return f'SELECT {columns} FROM parquet' + ('\n' + tail if tail else '')


def run_query(db, path, args):
    query = build_query(args.get('projection', '*'), args.get('clauses', ''))
    statements = db.extract_statements(query)
    if len(statements) != 1 or str(statements[0].type) != 'StatementType.SELECT':
        raise ValueError('Solo se admiten consultas SELECT de lectura.')
    db.execute('CREATE VIEW parquet AS SELECT * FROM data')
    # Restrict SQL file access to the explicitly opened file.
    db.execute('SET allowed_paths = ?', [[str(path)]])
    db.execute('SET enable_external_access = false')
    db.execute('SET autoinstall_known_extensions = false')
    db.execute('SET autoload_known_extensions = false')
    db.execute('SET lock_configuration = true')
    limit = min(500, max(10, int(args.get('limit', 100))))
    offset = max(0, int(args.get('offset', 0)))
    source = f'({query}) AS sql_result'
    def quote(name):
        return '"' + name.replace('"', '""') + '"'
    timer = threading.Timer(30, db.interrupt)
    timer.daemon = True
    timer.start()
    try:
        columns = [dict(name=r[0], type=r[1], nullable=r[2]) for r in db.execute(f'DESCRIBE SELECT * FROM {source}').fetchall()]
        total = db.execute(f'SELECT count(*) FROM {source}').fetchone()[0]
        sort = args.get('sort')
        order = f" ORDER BY {quote(sort)} {'DESC' if args.get('desc') == '1' else 'ASC'} NULLS LAST" if sort in [c['name'] for c in columns] else ''
        projection = ','.join(f'CAST({quote(c["name"])} AS VARCHAR) AS {quote(c["name"])}' for c in columns)
        rows = db.execute(f'SELECT {projection} FROM (SELECT * FROM {source}{order} LIMIT ? OFFSET ?)', [limit, offset]).fetchall()
        return dict(columns=columns, rows=rows, total=total)
    finally:
        timer.cancel()
