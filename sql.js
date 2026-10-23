// Deliberately small SELECT editor: one fixed source, no subqueries or statements.
export function normalizeFragment(text) {
  let output = "",
    words = "",
    i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (["'", '"', "`"].includes(ch)) {
      const quote = ch;
      let value = "";
      let closed = false;
      i++;
      while (i < text.length) {
        if (text[i] === "\\")
          throw Error(
            "Usá comillas duplicadas para escapar texto, sin barras invertidas.",
          );
        if (text[i] === quote) {
          if (text[i + 1] === quote) {
            value += quote;
            i += 2;
            continue;
          }
          i++;
          closed = true;
          break;
        }
        value += text[i++];
      }
      if (!closed) throw Error("Hay comillas sin cerrar en la consulta.");
      output +=
        quote === "'"
          ? "'" + value.replaceAll("'", "''") + "'"
          : '"' + value.replaceAll('"', '""') + '"';
      words += " ";
      continue;
    }
    if (
      ch === ";" ||
      text.slice(i, i + 2) === "--" ||
      text.slice(i, i + 2) === "/*" ||
      ch === "$" ||
      ch === "\\"
    ) {
      throw Error(
        "Usá una sola consulta, sin punto y coma, comentarios ni escapes con barra invertida.",
      );
    }
    output += ch;
    words += ch;
    i++;
  }
  if (
    /\b(select|from|join|union|intersect|except|with|into|copy|insert|update|delete|drop|alter|create|attach|detach|install|load|pragma|set|call|export|import)\b/i.test(
      words,
    )
  ) {
    throw Error(
      "SELECT y FROM parquet ya están fijos. Escribí columnas y cláusulas; no se admiten subconsultas ni cambios de datos.",
    );
  }
  return output.trim();
}

export function buildQuery(projection = "*", clauses = "") {
  if (projection.length + clauses.length > 20000)
    throw Error("La consulta es demasiado larga (máximo 20.000 caracteres).");
  const columns = normalizeFragment(projection) || "*";
  const tail = normalizeFragment(clauses);
  if (
    tail &&
    !/^(where\b|group\s+by\b|having\b|order\s+by\b|limit\b|offset\b)/i.test(
      tail,
    )
  ) {
    throw Error(
      "Las cláusulas deben empezar con WHERE, GROUP BY, HAVING, ORDER BY, LIMIT u OFFSET.",
    );
  }
  return `SELECT ${columns} FROM parquet${tail ? "\n" + tail : ""}`;
}

// Kept independent of the browser so both the real WASM engine and tests use
// exactly the same projection, count, ordering and pagination behavior.
export async function executeSelect(connection, source, args) {
  const identifier = (value) => '"' + value.replaceAll('"', '""') + '"';
  const limit = Math.min(
    250,
    Math.max(1, Math.floor(Number(args.limit) || 100)),
  );
  const offset = Math.max(0, Math.floor(Number(args.offset) || 0));
  const sql = buildQuery(args.projection, args.clauses);
  const resultSource = `(WITH parquet AS (SELECT * FROM ${source}) ${sql}) AS sql_result`;
  const schema = await connection.query(
    `DESCRIBE SELECT * FROM ${resultSource}`,
  );
  const columns = schema
    .toArray()
    .map((row) => ({
      name: row.column_name,
      type: row.column_type,
      nullable: row.null,
    }));
  const count = await connection.query(
    `SELECT count(*) AS n FROM ${resultSource}`,
  );
  const order = columns.some((c) => c.name === args.sort)
    ? ` ORDER BY ${identifier(args.sort)} ${args.desc === "1" ? "DESC" : "ASC"} NULLS LAST`
    : "";
  const projection = columns
    .map(
      (c) => `CAST(${identifier(c.name)} AS VARCHAR) AS ${identifier(c.name)}`,
    )
    .join(",");
  const page = await connection.query(
    `SELECT ${projection} FROM (SELECT * FROM ${resultSource}${order} LIMIT ${limit} OFFSET ${offset})`,
  );
  return {
    columns,
    total: Number(count.get(0).n),
    rows: page.toArray().map((row) => columns.map((c) => row[c.name])),
  };
}
