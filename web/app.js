/* Monitor de desastres naturales.
 *
 * Consume datos/recientes.json, que el cron regenera cada hora. Sin build, sin
 * framework: la lista y los filtros funcionan con JS a secas, y el mapa entra
 * solo si Leaflet cargó. Esa separación es deliberada — si el CDN se cae, la
 * página sigue sirviendo para lo que importa.
 */

const RUTA_DATOS = "datos/recientes.json";

// Umbrales de frescura. Si el cron corre cada hora, tres horas sin datos ya es
// señal de que algo se rompió, y hay que decírselo al usuario en vez de
// mostrarle información vieja como si fuera actual.
const HORAS_VIEJO = 3;
const HORAS_CRITICO = 12;

const TIPOS = [
  { clave: "sismo", etiqueta: "Sismo", icono: "〰️" },
  { clave: "ciclon", etiqueta: "Ciclón", icono: "🌀" },
  { clave: "inundacion", etiqueta: "Inundación", icono: "🌊" },
  { clave: "volcan", etiqueta: "Volcán", icono: "🌋" },
  { clave: "incendio", etiqueta: "Incendio", icono: "🔥" },
  { clave: "sequia", etiqueta: "Sequía", icono: "🏜️" },
  { clave: "otro", etiqueta: "Otro", icono: "◆" },
];

/* El nivel de alerta usa la paleta de estado, pero el color nunca viaja solo:
 * cada nivel lleva etiqueta de texto, y en el mapa además tamaño y anillo.
 * Amarilla y naranja son casi indistinguibles a simple vista, así que sin esa
 * redundancia el mapa mentiría. `peso` ordena el nivel y da el radio. */
const ALERTAS = [
  { clave: "roja", etiqueta: "Alerta roja", color: "#d03b3b", peso: 4 },
  { clave: "naranja", etiqueta: "Alerta naranja", color: "#ec835a", peso: 3 },
  { clave: "amarilla", etiqueta: "Alerta amarilla", color: "#fab219", peso: 2 },
  { clave: "verde", etiqueta: "Alerta verde", color: "#0ca30c", peso: 1 },
  { clave: "", etiqueta: "Sin nivel informado", color: "#898781", peso: 0 },
];

const TIPO_POR_CLAVE = new Map(TIPOS.map((t) => [t.clave, t]));
const ALERTA_POR_CLAVE = new Map(ALERTAS.map((a) => [a.clave, a]));

const estado = {
  eventos: [],
  generado: null,
  tiposOcultos: new Set(),
  alertasOcultas: new Set(),
  texto: "",
  magnitudMinima: 0,
  seleccionado: null,
};

let mapa = null;
let capaMarcadores = null;
const marcadoresPorId = new Map();

const $ = (sel) => document.querySelector(sel);

/* ---------------------------------------------------------------- utilidades */

function tipoDe(evento) {
  return TIPO_POR_CLAVE.get(evento.tipo) ?? TIPO_POR_CLAVE.get("otro");
}

function alertaDe(evento) {
  return ALERTA_POR_CLAVE.get(evento.nivel_alerta ?? "") ?? ALERTA_POR_CLAVE.get("");
}

function fechaLegible(iso) {
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return "fecha desconocida";
  return fecha.toLocaleString("es", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function horasDesde(iso) {
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return Infinity;
  return (Date.now() - fecha.getTime()) / 3_600_000;
}

function hace(horas) {
  if (!Number.isFinite(horas)) return "hace un tiempo indeterminado";
  if (horas < 1) return `hace ${Math.max(1, Math.round(horas * 60))} min`;
  if (horas < 48) return `hace ${Math.round(horas)} h`;
  return `hace ${Math.round(horas / 24)} días`;
}

/* ------------------------------------------------------------------ frescura */

function pintarFrescura() {
  const aviso = $("#frescura");
  if (!estado.generado) {
    aviso.hidden = false;
    aviso.dataset.nivel = "critico";
    aviso.innerHTML = "<strong>Sin datos.</strong> No se pudo leer la última actualización.";
    return;
  }

  const horas = horasDesde(estado.generado);
  if (horas < HORAS_VIEJO) {
    aviso.hidden = true;
    return;
  }

  aviso.hidden = false;
  aviso.dataset.nivel = horas >= HORAS_CRITICO ? "critico" : "viejo";
  aviso.innerHTML =
    `<strong>Datos desactualizados.</strong> La última actualización fue ${hace(horas)}. ` +
    "Puede haber eventos recientes que no aparezcan acá.";
}

/* -------------------------------------------------------------------- filtros */

function coincide(evento) {
  if (estado.tiposOcultos.has(tipoDe(evento).clave)) return false;
  if (estado.alertasOcultas.has(alertaDe(evento).clave)) return false;

  // El umbral aplica solo a sismos con magnitud conocida: los km/h de un ciclón
  // no son comparables con la escala sísmica.
  if (
    estado.magnitudMinima > 0 &&
    evento.tipo === "sismo" &&
    typeof evento.magnitud === "number" &&
    evento.magnitud < estado.magnitudMinima
  ) {
    return false;
  }

  if (estado.texto) {
    const heno = `${evento.titulo} ${evento.lugar} ${evento.pais}`.toLowerCase();
    if (!heno.includes(estado.texto)) return false;
  }
  return true;
}

function visibles() {
  return estado.eventos.filter(coincide);
}

/* ----------------------------------------------------------------------- UI */

function construirChips(contenedor, definiciones, ocultos, conteos) {
  contenedor.replaceChildren();

  for (const def of definiciones) {
    const conteo = conteos.get(def.clave) ?? 0;
    if (conteo === 0) continue;

    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.setAttribute("aria-pressed", String(!ocultos.has(def.clave)));

    if (def.color) {
      const punto = document.createElement("span");
      punto.className = "punto";
      punto.style.background = def.color;
      chip.append(punto);
    } else if (def.icono) {
      const icono = document.createElement("span");
      icono.setAttribute("aria-hidden", "true");
      icono.textContent = def.icono;
      chip.append(icono);
    }

    chip.append(document.createTextNode(def.etiqueta));

    const badge = document.createElement("span");
    badge.className = "chip__conteo";
    badge.textContent = String(conteo);
    chip.append(badge);

    chip.addEventListener("click", () => {
      if (ocultos.has(def.clave)) ocultos.delete(def.clave);
      else ocultos.add(def.clave);
      renderizar();
    });

    contenedor.append(chip);
  }
}

function contarPor(obtenerClave) {
  const conteos = new Map();
  for (const evento of estado.eventos) {
    const clave = obtenerClave(evento);
    conteos.set(clave, (conteos.get(clave) ?? 0) + 1);
  }
  return conteos;
}

function tarjeta(evento) {
  const tipo = tipoDe(evento);
  const alerta = alertaDe(evento);

  const item = document.createElement("li");
  const boton = document.createElement("button");
  boton.type = "button";
  boton.className = "evento";
  boton.style.setProperty("--color-alerta", alerta.color);
  boton.setAttribute("aria-current", String(estado.seleccionado === evento.id));

  const icono = document.createElement("span");
  icono.className = "evento__icono";
  icono.setAttribute("aria-hidden", "true");
  icono.textContent = tipo.icono;

  const titulo = document.createElement("span");
  titulo.className = "evento__titulo";
  titulo.textContent = evento.titulo || tipo.etiqueta;

  const meta = document.createElement("span");
  meta.className = "evento__meta";

  const cuando = document.createElement("span");
  cuando.textContent = fechaLegible(evento.fecha_evento);
  meta.append(cuando);

  if (typeof evento.magnitud === "number") {
    const mag = document.createElement("span");
    mag.className = "magnitud";
    mag.textContent = `${evento.magnitud} ${evento.unidad_magnitud || ""}`.trim();
    meta.append(mag);
  }

  if (evento.pais) {
    const donde = document.createElement("span");
    donde.textContent = evento.pais;
    meta.append(donde);
  }

  // La insignia lleva el nivel escrito. Sin esto el color sería el único
  // portador del dato más importante de la tarjeta.
  const insignia = document.createElement("span");
  insignia.className = "insignia";
  const punto = document.createElement("span");
  punto.className = "punto";
  punto.style.background = alerta.color;
  insignia.append(punto, document.createTextNode(alerta.etiqueta));
  meta.append(insignia);

  boton.append(icono, titulo, meta);
  boton.addEventListener("click", () => seleccionar(evento));
  item.append(boton);
  return item;
}

function seleccionar(evento) {
  estado.seleccionado = evento.id;
  const marcador = marcadoresPorId.get(evento.id);
  if (mapa && marcador) {
    mapa.setView(marcador.getLatLng(), Math.max(mapa.getZoom(), 5), { animate: true });
    marcador.openPopup();
  }
  renderizar();
}

function pintarTiles(lista) {
  $("#tile-total").textContent = lista.length;
  $("#tile-graves").textContent = lista.filter((e) =>
    ["roja", "naranja"].includes(e.nivel_alerta)
  ).length;
  $("#tile-24h").textContent = lista.filter((e) => horasDesde(e.fecha_evento) <= 24).length;
  $("#tile-actualizado").textContent = estado.generado ? hace(horasDesde(estado.generado)) : "–";
}

/* ---------------------------------------------------------------------- mapa */

function radioDe(evento) {
  const alerta = alertaDe(evento);
  // El nivel de alerta manda sobre el tamaño; la magnitud sísmica lo matiza.
  // Así el nivel se lee aunque el color no se distinga.
  const base = 5 + alerta.peso * 2.5;
  if (evento.tipo === "sismo" && typeof evento.magnitud === "number") {
    return base + Math.max(0, evento.magnitud - 3);
  }
  return base;
}

function iniciarMapa() {
  if (typeof window.L === "undefined") {
    $("#mapa").remove();
    $("#mapa-caido").hidden = false;
    return false;
  }

  mapa = window.L.map("mapa", { worldCopyJump: true }).setView([10, 0], 2);
  window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(mapa);
  capaMarcadores = window.L.layerGroup().addTo(mapa);
  return true;
}

function pintarMapa(lista) {
  if (!mapa || !capaMarcadores) return;

  capaMarcadores.clearLayers();
  marcadoresPorId.clear();

  for (const evento of lista) {
    if (typeof evento.latitud !== "number" || typeof evento.longitud !== "number") continue;

    const tipo = tipoDe(evento);
    const alerta = alertaDe(evento);
    const marcador = window.L.circleMarker([evento.latitud, evento.longitud], {
      radius: radioDe(evento),
      color: alerta.color,
      // Un anillo más grueso en los niveles altos: segunda señal, además del
      // color y del tamaño, para que naranja y roja no dependan del tono.
      weight: alerta.peso >= 3 ? 3 : 1.5,
      fillColor: alerta.color,
      fillOpacity: 0.55,
    });

    const enlace = evento.url
      ? `<br><a href="${evento.url}" rel="noopener" target="_blank">Ver en la fuente</a>`
      : "";
    marcador.bindPopup(
      `<strong>${tipo.icono} ${evento.titulo || tipo.etiqueta}</strong><br>` +
        `${alerta.etiqueta} · ${fechaLegible(evento.fecha_evento)}${enlace}`
    );
    marcador.on("click", () => {
      estado.seleccionado = evento.id;
      renderizar();
    });

    marcador.addTo(capaMarcadores);
    marcadoresPorId.set(evento.id, marcador);
  }
}

/* ------------------------------------------------------------------- render */

function renderizar() {
  const lista = visibles();

  construirChips($("#chips-tipo"), TIPOS, estado.tiposOcultos, contarPor((e) => tipoDe(e).clave));
  construirChips(
    $("#chips-alerta"),
    ALERTAS,
    estado.alertasOcultas,
    contarPor((e) => alertaDe(e).clave)
  );

  pintarTiles(lista);
  $("#lista-conteo").textContent = `(${lista.length})`;
  $("#lista").replaceChildren(...lista.map(tarjeta));
  $("#vacio").hidden = lista.length > 0;

  pintarMapa(lista);
}

/* -------------------------------------------------------------------- carga */

async function cargar() {
  const respuesta = await fetch(RUTA_DATOS, { cache: "no-cache" });
  if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status} al pedir ${RUTA_DATOS}`);

  const documento = await respuesta.json();
  estado.eventos = Array.isArray(documento.eventos) ? documento.eventos : [];
  estado.generado = documento.generado ?? null;
}

function conectarControles() {
  $("#busqueda").addEventListener("input", (evento) => {
    estado.texto = evento.target.value.trim().toLowerCase();
    renderizar();
  });

  $("#magnitud").addEventListener("input", (evento) => {
    estado.magnitudMinima = Number(evento.target.value);
    $("#mag-valor").textContent = estado.magnitudMinima.toFixed(1);
    renderizar();
  });

  const boton = $("#tema");
  boton.addEventListener("click", () => {
    const oscuroAhora = document.documentElement.dataset.theme === "dark";
    document.documentElement.dataset.theme = oscuroAhora ? "light" : "dark";
    boton.setAttribute("aria-pressed", String(!oscuroAhora));
  });
}

async function iniciar() {
  conectarControles();
  iniciarMapa();

  try {
    await cargar();
  } catch (error) {
    console.error(error);
    estado.generado = null;
    pintarFrescura();
    $("#vacio").hidden = false;
    $("#vacio").textContent =
      "No se pudieron cargar los datos. Probá recargar la página en unos minutos.";
    return;
  }

  pintarFrescura();
  renderizar();
}

document.addEventListener("DOMContentLoaded", iniciar);
