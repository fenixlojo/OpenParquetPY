export function initConverter({ inspect, convert, discard, onOpen, setBusy }) {
  const $ = (id) => document.getElementById(id);
  let source,
    working = false,
    inspecting = false,
    downloadUrl;
  const size = (n) => {
    const units = ["B", "KB", "MB", "GB"];
    let i = 0;
    while (n >= 1024 && i < 3) {
      n /= 1024;
      i++;
    }
    return (
      n.toLocaleString("es-UY", { maximumFractionDigits: 2 }) + " " + units[i]
    );
  };
  function progress({ step, label }) {
    if (step === 0) $("convertProgress").removeAttribute("value");
    else $("convertProgress").value = step;
    $("convertStatus").textContent = label;
    $("convertProgress").classList.toggle("working", step < 4);
  }
  function controls(busy) {
    working = busy;
    for (const id of [
      "convertFile",
      "convertSheet",
      "convertHeader",
      "convertText",
      "convertEncoding",
      "convertRun",
      "convertClose",
    ])
      $(id).disabled = busy;
    setBusy(busy);
  }
  async function clearSource() {
    const previous = source;
    source = undefined;
    if (previous) await discard(previous);
  }
  $("generate").onclick = () => {
    $("convertProgress").value = 0;
    $("convertProgress").classList.remove("working");
    $("convertStatus").textContent = "Elegí un archivo para empezar.";
    $("convertSummary").textContent = "";
    $("convertDownload").classList.add("hidden");
    $("sheetLabel").classList.add("hidden");
    $("encodingLabel").classList.remove("hidden");
    $("convertDialog").showModal();
  };
  $("convertClose").onclick = () => {
    $("convertDialog").close();
  };
  $("convertDialog").oncancel = (event) => {
    if (working || inspecting) event.preventDefault();
  };
  $("convertDialog").onclose = () => {
    clearSource().catch(() => {});
    $("convertFile").value = "";
    $("convertRun").disabled = true;
  };
  $("convertFile").onchange = async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    inspecting = true;
    controls(true);
    $("convertSummary").textContent = "";
    $("convertDownload").classList.add("hidden");
    progress({ step: 0, label: "Leyendo el archivo y sus hojas…" });
    try {
      await clearSource();
      source = await inspect(file);
      $("convertSheet").replaceChildren(
        ...source.sheets.map((name) => {
          const option = document.createElement("option");
          option.value = name;
          option.textContent = name;
          return option;
        }),
      );
      $("sheetLabel").classList.toggle("hidden", !source.excel);
      $("encodingLabel").classList.toggle("hidden", source.excel);
      $("convertStatus").textContent =
        `${file.name} · ${size(file.size)}. Listo para convertir.`;
    } catch (error) {
      $("convertStatus").textContent = error.message;
    } finally {
      inspecting = false;
      controls(false);
      $("convertRun").disabled = !source;
      $("convertProgress").value = 0;
      $("convertProgress").classList.remove("working");
    }
  };
  $("convertRun").onclick = async () => {
    if (!source || working) return;
    controls(true);
    $("convertDownload").classList.add("hidden");
    $("convertSummary").textContent = "";
    progress({ step: 0, label: "Preparando conversión…" });
    try {
      const result = await convert(
        source,
        {
          sheet: $("convertSheet").value,
          header: $("convertHeader").checked,
          allText: $("convertText").checked,
          encoding: $("convertEncoding").value,
        },
        progress,
      );
      const delta = result.originalSize - result.outputSize,
        percent = (Math.abs(delta) / result.originalSize) * 100;
      $("convertSummary").textContent =
        `Origen: ${size(result.originalSize)} → Parquet: ${size(result.outputSize)}. ${delta >= 0 ? "Ahorro" : "Aumento"}: ${size(Math.abs(delta))} (${percent.toLocaleString("es-UY", { maximumFractionDigits: 1 })} %).`;
      if (source.excel)
        $("convertSummary").textContent +=
          " Comparación con el Excel completo; el Parquet contiene solo la hoja elegida.";
      if (downloadUrl) URL.revokeObjectURL(downloadUrl);
      downloadUrl = result.blob ? URL.createObjectURL(result.blob) : undefined;
      const link = $("convertDownload");
      link.href = downloadUrl || result.downloadUrl;
      link.download = result.name;
      link.textContent = "Descargar de nuevo: " + result.name;
      link.classList.remove("hidden");
      link.click();
      progress({
        step: 3,
        label: "Descarga solicitada. Abriendo el Parquet en el visor…",
      });
      await onOpen(result);
      progress({
        step: 4,
        label:
          "Parquet generado y abierto. Se solicitó la descarga; si no aparece, usá el enlace de abajo.",
      });
      $("conversionResultText").textContent =
        $("convertSummary").textContent +
        " Se solicitó la descarga y el archivo se abrió en el visor.";
      const savedLink = $("conversionResultDownload");
      savedLink.href = link.href;
      savedLink.download = result.name;
      $("conversionResult").classList.remove("hidden");
      $("convertDialog").close();
    } catch (error) {
      progress({ step: 0, label: error.message || String(error) });
      $("convertProgress").classList.remove("working");
      $("convertProgress").value = 0;
    } finally {
      controls(false);
      $("convertRun").disabled = !source;
    }
  };
}
