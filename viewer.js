import { initConverter } from "./conversion-ui.js";
import { inspectSource, convertSource, discardSource } from "./convert-adapter.js";
import { buildQuery } from "./sql.js";
async function api(url, options) {
  const response = await fetch(url, options);
  const result = await response.json();
  if (!response.ok)
    throw Error(result.error || "No se pudo completar la consulta.");
  return result;
}
function openFile(file) {
  return api("/api/upload", {
    method: "POST",
    headers: { "X-Filename": encodeURIComponent(file.name) },
    body: file,
  });
}
function readRows(args) {
  return args.sqlMode === "1"
    ? api("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(args),
      })
    : api("/api/rows?" + new URLSearchParams(args));
}
function closeFile(id) {
  return api("/api/close", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
}

const $ = (id) => document.getElementById(id),
  fmt = (n) => n.toLocaleString("es-UY");
let current,
  opened = [],
  offset = 0,
  total = 0,
  sort = "",
  desc = false,
  view = "data",
  request = 0,
  busy = 0;
let appliedSql = { projection: "*", clauses: "" };
const el = (tag, text) => {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  return e;
};
function status(text, error = false) {
  $("status").textContent = text;
  $("status").style.color = error ? "#ff9e93" : "var(--accent)";
}
function size(n) {
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < 4) {
    n /= 1024;
    i++;
  }
  return n.toLocaleString("es-UY", { maximumFractionDigits: 1 }) + " " + u[i];
}
function activate(info) {
  clearTimeout(timer);
  view = "data";
  $("dataTab").classList.add("active");
  $("schemaTab").classList.remove("active");
  $("search").classList.remove("hidden");
  $("sqlTab").classList.remove("active");
  $("sqlPanel").classList.add("hidden");
  appliedSql = { projection: "*", clauses: "" };
  $("sqlColumns").value = "*";
  $("sqlClauses").value = "";
  $("sqlPreview").textContent = "SELECT * FROM parquet";
  current = info;
  offset = 0;
  sort = "";
  desc = false;
  $("search").value = "";
  $("drop").classList.add("hidden");
  $("content").classList.remove("hidden");
  $("filename").textContent = info.name;
  $("files").value = info.id;
  $("nrows").textContent = fmt(info.rows);
  $("ncols").textContent = fmt(info.columns.length);
  $("size").textContent = size(info.size);
  $("groups").textContent = fmt(info.rowGroups);
  return load();
}
function add(info) {
  opened.push(info);
  const o = el("option", info.name);
  o.value = info.id;
  $("files").append(o);
  return activate(info);
}
async function upload(files) {
  if (busy) return;
  files = Array.from(files);
  busy++;
  setOpening(true);
  const errors = [];
  try {
    for (const file of files) {
      status("Abriendo " + file.name + "…");
      try {
        await add(await openFile(file));
      } catch (e) {
        errors.push(e.message);
      }
    }
    if (errors.length) status(errors.join("\n"), true);
  } finally {
    busy--;
    setOpening(false);
  }
}
$("open").onclick = $("choose").onclick = () => $("file").click();
$("file").onchange = (e) => {
  upload(Array.from(e.target.files));
  e.target.value = "";
};
$("another").onclick = () => $("file").click();
for (const event of ["dragenter", "dragover"])
  $("drop").addEventListener(event, (e) => {
    e.preventDefault();
    $("drop").classList.add("over");
  });
$("drop").ondragleave = () => $("drop").classList.remove("over");
$("drop").ondrop = (e) => {
  e.preventDefault();
  $("drop").classList.remove("over");
  upload(Array.from(e.dataTransfer.files));
};
$("files").onchange = () =>
  activate(opened.find((f) => f.id === $("files").value));
function setView(v) {
  clearTimeout(timer);
  view = v;
  offset = 0;
  sort = "";
  desc = false;
  $("sqlPanel").classList.toggle("hidden", v !== "sql");
  $("sqlTab").classList.toggle("active", v === "sql");
  $("dataTab").classList.toggle("active", v === "data");
  $("schemaTab").classList.toggle("active", v === "schema");
  $("search").classList.toggle("hidden", v !== "data");
  load();
}
$("dataTab").onclick = () => setView("data");
$("schemaTab").onclick = () => setView("schema");
$("sqlTab").onclick = () => setView("sql");
function cellValue(v) {
  return v === null
    ? "NULL"
    : typeof v === "object"
      ? JSON.stringify(v)
      : String(v);
}
async function load() {
  if (!current) return;
  const token = ++request;
  $("prev").disabled = $("next").disabled = true;
  $("table").replaceChildren(el("div", "Cargando…"));
  let table = el("table"),
    head = el("thead"),
    hr = el("tr"),
    body = el("tbody");
  table.append(head, body);
  head.append(hr);
  if (view === "schema") {
    for (const n of ["#", "Columna", "Tipo de dato", "Admite NULL"])
      hr.append(el("th", n));
    current.columns.forEach((c, i) => {
      let r = el("tr");
      [i + 1, c.name, c.type, c.nullable === "YES" ? "Sí" : "No"].forEach((x) =>
        r.append(el("td", x)),
      );
      body.append(r);
    });
    $("table").replaceChildren(table);
    $("range").textContent =
      current.columns.length + " columnas · Esquema Parquet";
    $("page").textContent = "Esquema";
    $("prev").disabled = $("next").disabled = true;
    status("");
    return;
  }
  status("Consultando datos…");
  try {
    const q = new URLSearchParams({
      id: current.id,
      limit: $("limit").value,
      offset,
      search: view === "data" ? $("search").value : "",
      ...(view === "sql" ? { sqlMode: "1", ...appliedSql } : {}),
      sort,
      desc: desc ? "1" : "0",
    });
    const result = await readRows(Object.fromEntries(q));
    if (token !== request) return;
    total = result.total;
    hr.append(el("th", "#"));
    (result.columns || current.columns).forEach((c) => {
      let th = el("th"),
        b = el(
          "button",
          c.name + (sort === c.name ? (desc ? " ↓" : " ↑") : ""),
        );
      b.append(el("small", c.type));
      b.onclick = () => {
        desc = sort === c.name ? !desc : false;
        sort = c.name;
        offset = 0;
        load();
      };
      th.append(b);
      hr.append(th);
    });
    result.rows.forEach((row, i) => {
      let r = el("tr");
      r.append(el("td", fmt(offset + i + 1)));
      row.forEach((v) => {
        let td = el("td", cellValue(v));
        if (v === null) td.className = "null";
        td.classList.add("cell");
        td.tabIndex = 0;
        td.onkeydown = (e) => {
          if (e.key === "Enter") td.click();
        };
        td.title = "Clic para ver contenido completo";
        td.onclick = () => {
          $("detailText").textContent =
            typeof v === "object" && v !== null
              ? JSON.stringify(v, null, 2)
              : cellValue(v);
          $("detail").showModal();
        };
        r.append(td);
      });
      body.append(r);
    });
    $("table").replaceChildren(
      result.rows.length ? table : el("div", "No hay filas para mostrar."),
    );
    $("range").textContent = total
      ? `${fmt(offset + 1)}–${fmt(offset + result.rows.length)} de ${fmt(total)} filas`
      : "0 filas";
    const limit = +$("limit").value;
    $("page").textContent =
      `${Math.floor(offset / limit) + 1} / ${Math.max(1, Math.ceil(total / limit))}`;
    $("prev").disabled = offset === 0;
    $("next").disabled = offset + limit >= total;
    status("");
  } catch (e) {
    if (token !== request) return;
    $("table").replaceChildren(
      el(
        "div",
        view === "sql"
          ? "No se pudo ejecutar la consulta. Revisá las columnas y la sintaxis indicada en el mensaje."
          : "No se pudieron consultar los datos. Probá una búsqueda más acotada o un archivo más pequeño.",
      ),
    );
    status(e.message, true);
  }
}
$("closeDetail").onclick = () => $("detail").close();
let timer;
$("search").oninput = () => {
  clearTimeout(timer);
  request++;
  timer = setTimeout(() => {
    offset = 0;
    load();
  }, 350);
};
$("limit").onchange = () => {
  offset = 0;
  load();
};
$("prev").onclick = () => {
  offset = Math.max(0, offset - +$("limit").value);
  load();
};
$("next").onclick = () => {
  offset += +$("limit").value;
  load();
};

function setOpening(value) {
  for (const id of ["open", "choose", "another", "closeFile", "files", "generate"])
    $(id).disabled = value;
}
$("closeFile").onclick = async () => {
  if (!current || busy) return;
  const closing = current;
  request++;
  opened = opened.filter((f) => f.id !== closing.id);
  Array.from($("files").options)
    .find((o) => o.value === closing.id)
    ?.remove();
  if (opened.length) activate(opened.at(-1));
  else {
    current = null;
    $("content").classList.add("hidden");
    $("drop").classList.remove("hidden");
    $("table").replaceChildren();
    status("Archivo cerrado.");
  }
  try {
    await closeFile(closing.id);
  } catch (e) {
    status(e.message, true);
  }
};
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => {
  e.preventDefault();
  if (!e.target.closest("#drop")) upload(Array.from(e.dataTransfer.files));
});

async function runSql() {
  try {
    const next = {
      projection: $("sqlColumns").value,
      clauses: $("sqlClauses").value,
    };
    const query = buildQuery(next.projection, next.clauses);
    appliedSql = next;
    $("sqlPreview").textContent = query;
    offset = 0;
    sort = "";
    desc = false;
    await load();
  } catch (error) {
    status(error.message, true);
  }
}
$("runSql").onclick = runSql;
$("resetSql").onclick = () => {
  $("sqlColumns").value = "*";
  $("sqlClauses").value = "";
  runSql();
};
$("countSql").onclick = () => {
  $("sqlColumns").value = "COUNT(*) AS total";
  $("sqlClauses").value = "";
  runSql();
};
for (const id of ["sqlColumns", "sqlClauses"])
  $(id).onkeydown = (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      runSql();
    }
  };

$("openpath").onclick = async () => {
  if (busy) return;
  const path = $("path").value.trim().replace(/^"|"$/g, "");
  if (!path) return;
  busy++;
  setOpening(true);
  status("Leyendo archivo…");
  try {
    await add(
      await api("/api/open", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      }),
    );
  } catch (error) {
    status(error.message, true);
  } finally {
    busy--;
    setOpening(false);
  }
};
$("path").onkeydown = (event) => {
  if (event.key === "Enter") $("openpath").click();
};

initConverter({
 inspect: inspectSource, convert: convertSource, discard: discardSource,
 setBusy: value => { busy += value ? 1 : -1; setOpening(busy > 0); },
 onOpen: async result => { await add(result.info || await openFile(new File([result.blob], result.name, {type:'application/vnd.apache.parquet'}))); }
});
