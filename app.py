"""OpenParquets: a loopback-only, paginated Parquet viewer."""
import argparse
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import duckdb

ROOT = Path(__file__).resolve().parent
FILES = {}
LOCK = threading.Lock()
TEMP = tempfile.TemporaryDirectory(prefix="openparquets-")


def connect(path):
    db = duckdb.connect()
    db.execute("SET threads=2")
    db.execute("SET memory_limit='512MB'")
    db.read_parquet(str(path)).create_view("data")
    return db


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def clean(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    return value


def register(path, name=None):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError("La ruta debe ser un archivo.")
    with connect(path) as db:
        columns = [{"name": r[0], "type": r[1], "nullable": r[2]} for r in db.execute("DESCRIBE data").fetchall()]
        count = db.execute("SELECT count(*) FROM data").fetchone()[0]
        metadata = db.execute("SELECT num_row_groups, format_version FROM parquet_file_metadata(?)", [str(path)]).fetchone()
    import uuid
    key = uuid.uuid4().hex
    info = dict(id=key, name=name or path.name, size=path.stat().st_size, rows=count, columns=columns, rowGroups=metadata[0], version=metadata[1])
    with LOCK:
        FILES[key] = (path, info)
    return info


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, value, status=200):
        body = json.dumps(clean(value), default=str, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def trusted(self):
        expected = f"127.0.0.1:{self.server.server_port}"
        return self.headers.get("Host") == expected and self.headers.get("Origin", f"http://{expected}") == f"http://{expected}"

    def do_GET(self):
        if not self.trusted():
            return self.send({"error": "Origen no permitido"}, 403)
        url = urlparse(self.path)
        static = {"/": ("index.html", "text/html"), "/viewer.js": ("viewer.js", "text/javascript"), "/sql.js": ("sql.js", "text/javascript")}
        if url.path in static:
            filename, mime = static[url.path]
            body = (ROOT / filename).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if url.path != "/api/rows":
            return self.send({"error": "No encontrado"}, 404)
        try:
            args = {k: v[0] for k, v in parse_qs(url.query).items()}
            path, info = FILES[args["id"]]
            limit = min(500, max(10, int(args.get("limit", 100))))
            offset = max(0, int(args.get("offset", 0)))
            search = args.get("search", "")[:500]
            names = [c["name"] for c in info["columns"]]
            params = []
            where = ""
            if search:
                where = " WHERE " + " OR ".join(f"contains(lower(CAST({quote(n)} AS VARCHAR)), lower(?))" for n in names)
                params = [search] * len(names)
            sort = args.get("sort")
            order = f" ORDER BY {quote(sort)} {'DESC' if args.get('desc') == '1' else 'ASC'} NULLS LAST" if sort in names else ""
            with connect(path) as db:
                total = db.execute("SELECT count(*) FROM data" + where, params).fetchone()[0] if search else info["rows"]
                rows = db.execute("SELECT * FROM data" + where + order + " LIMIT ? OFFSET ?", params + [limit, offset]).fetchall()
            self.send(dict(rows=rows, total=total))
        except Exception as exc:
            self.send({"error": str(exc)}, 400)

    def do_POST(self):
        if not self.trusted():
            return self.send({"error": "Origen no permitido"}, 403)
        upload_path = None
        try:
            length = int(self.headers.get("Content-Length", 0))
            if self.path in ("/api/query", "/api/close"):
                if length <= 0 or length > 100000:
                    raise ValueError("Solicitud demasiado grande o vacía")
                args = json.loads(self.rfile.read(length))
                if self.path == "/api/close":
                    with LOCK:
                        FILES.pop(args["id"], None)
                    result = {"closed": True}
                else:
                    from sql_query import run_query
                    path, info = FILES[args["id"]]
                    with connect(path) as db:
                        result = run_query(db, path, args)
            elif self.path == "/api/open":
                if length > 16384:
                    raise ValueError("Ruta demasiado larga")
                result = register(json.loads(self.rfile.read(length))["path"])
            elif self.path == "/api/upload":
                if length <= 0 or length > 2 * 1024**3:
                    raise ValueError("Usá una ruta local para archivos de más de 2 GB.")
                import uuid
                upload_path = Path(TEMP.name) / (uuid.uuid4().hex + ".parquet")
                with upload_path.open("wb") as dest:
                    remaining = length
                    while remaining:
                        chunk = self.rfile.read(min(1024**2, remaining))
                        if not chunk:
                            raise ValueError("Transferencia incompleta")
                        dest.write(chunk)
                        remaining -= len(chunk)
                from urllib.parse import unquote
                result = register(upload_path, unquote(self.headers.get("X-Filename", "archivo.parquet")))
            else:
                return self.send({"error": "No encontrado"}, 404)
            self.send(result)
        except Exception as exc:
            if upload_path:
                upload_path.unlink(missing_ok=True)
            self.send({"error": str(exc)}, 400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"OpenParquets listo en {url} · Ctrl+C para cerrar", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        TEMP.cleanup()


if __name__ == "__main__":
    main()
