/* Monitor de desastres naturales.
 *
 * Consume datos/recientes.json, que el cron regenera cada hora. Sin build, sin
 * framework: la lista y los filtros funcionan con JS a secas, y el mapa entra
 * solo si Leaflet cargó. Esa separación es deliberada — si el CDN se cae, la
 * página sigue sirviendo para lo que importa.
 */

const RUTA_DATOS = "datos/recientes.json";

/* Umbrales de frescura, atados a la cadencia del cron (semanal, lunes 06:17
 * UTC). Si se cambia el schedule en .github/workflows/scraper.yml, hay que
 * mover estos números o la página va a mentir: con umbrales de horas sobre un
 * cron semanal, el aviso estaría encendido siempre y la gente aprendería a
 * ignorarlo — que es peor que no tenerlo. Se deja un margen de un día sobre el
 * intervalo para no gritar por una corrida apenas demorada. */
const HORAS_VIEJO = 8 * 24;
const HORAS_CRITICO = 15 * 24;

// Ventana del tile de actividad reciente. También sigue a la cadencia: contar
// "últimas 24 h" sobre datos semanales daría 0 casi siempre.
const HORAS_VENTANA_ACTIVIDAD = 7 * 24;

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

/* Copia local de lo que el feed publica en `media`. Solo se usa si el feed no
 * lo trae —feeds de antes de la versión 2—, para que la página no se quede sin
 * fotos esperando la próxima corrida del cron. Cuando el feed lo trae, manda el
 * feed: así se puede cambiar de capa o de proveedor sin tocar esta página. */
const MEDIA_POR_DEFECTO = {
  satelite: {
    plantilla:
      "https://wvs.earthdata.nasa.gov/api/v1/snapshot?REQUEST=GetSnapshot&LAYERS={capa}" +
      "&CRS=EPSG:4326&TIME={fecha}&BBOX={sur},{oeste},{norte},{este}" +
      "&FORMAT=image/jpeg&WIDTH={ancho}&HEIGHT={alto}",
    capa: "MODIS_Terra_CorrectedReflectance_TrueColor",
    credito: "NASA Worldview (MODIS/Terra)",
    grados_por_tipo: {
      sismo: 6,
      volcan: 5,
      incendio: 4,
      inundacion: 8,
      ciclon: 16,
      sequia: 20,
      otro: 8,
    },
    grados_por_defecto: 8,
    dias_timelapse: 7,
  },
  videos: { plantilla_busqueda: "https://www.youtube.com/results?search_query={consulta}" },
};

const estado = {
  eventos: [],
  generado: null,
  media: MEDIA_POR_DEFECTO,
  tiposOcultos: new Set(),
  alertasOcultas: new Set(),
  texto: "",
  magnitudMinima: 0,
  seleccionado: null,
  detalle: null,
  fotograma: 0,
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

/* ------------------------------------------------------------------- fotos */

/* La foto de cada evento es el mosaico satelital de ese día recortado a su
 * área, servido por NASA Worldview. La URL se arma acá y no viene en el feed
 * porque es pura aritmética sobre datos que el evento ya tiene: mandarla mil
 * veces sería mandar mil veces la misma plantilla. */

function gradosDe(tipo) {
  const satelite = estado.media?.satelite ?? MEDIA_POR_DEFECTO.satelite;
  return satelite.grados_por_tipo?.[tipo] ?? satelite.grados_por_defecto ?? 8;
}

/* Cerca del polo o del antimeridiano el recuadro no entra centrado. Se lo corre
 * hacia adentro en vez de recortarlo: recortado saldría una imagen deformada, y
 * si el ancho diera cero, un error. */
function ventana(centro, mitad, minimo, maximo) {
  const ancho = Math.min(mitad * 2, maximo - minimo);
  let inicio = centro - ancho / 2;
  if (inicio < minimo) inicio = minimo;
  else if (inicio + ancho > maximo) inicio = maximo - ancho;
  return [inicio, inicio + ancho];
}

function recuadroDe(evento) {
  const grados = Math.max(gradosDe(evento.tipo), 0.01);
  const [sur, norte] = ventana(evento.latitud, grados / 2, -90, 90);
  const [oeste, este] = ventana(evento.longitud, grados / 2, -180, 180);
  return [sur, oeste, norte, este].map((valor) => Number(valor.toFixed(4)));
}

function tieneFoto(evento) {
  return (
    typeof evento.latitud === "number" &&
    typeof evento.longitud === "number" &&
    typeof evento.fecha_evento === "string" &&
    evento.fecha_evento.length >= 10
  );
}

function urlSatelite(evento, { fecha = null, ancho = 512, alto = 512 } = {}) {
  if (!tieneFoto(evento)) return null;
  const satelite = estado.media?.satelite ?? MEDIA_POR_DEFECTO.satelite;
  const [sur, oeste, norte, este] = recuadroDe(evento);
  return satelite.plantilla
    .replace("{capa}", satelite.capa)
    .replace("{fecha}", fecha ?? evento.fecha_evento.slice(0, 10))
    .replace("{sur}", sur)
    .replace("{oeste}", oeste)
    .replace("{norte}", norte)
    .replace("{este}", este)
    .replace("{ancho}", ancho)
    .replace("{alto}", alto);
}

/* Los días del timelapse: el del evento y los siguientes, que es cuando se ve
 * crecer el incendio o avanzar el ciclón. Nunca días futuros — el mosaico de
 * mañana no existe todavía y devolvería un rectángulo negro. */
function diasTimelapse(evento) {
  const satelite = estado.media?.satelite ?? MEDIA_POR_DEFECTO.satelite;
  const cuantos = satelite.dias_timelapse ?? 7;
  const inicio = new Date(`${evento.fecha_evento.slice(0, 10)}T00:00:00Z`);
  const hoy = new Date();
  const dias = [];
  for (let i = 0; i < cuantos; i += 1) {
    const dia = new Date(inicio.getTime() + i * 86400000);
    if (dia > hoy) break;
    dias.push(dia.toISOString().slice(0, 10));
  }
  return dias;
}

function urlVideos(evento) {
  const plantilla =
    estado.media?.videos?.plantilla_busqueda ?? MEDIA_POR_DEFECTO.videos.plantilla_busqueda;
  const consulta = [evento.titulo, evento.pais].filter(Boolean).join(" ").trim();
  if (!consulta) return null;
  return plantilla.replace("{consulta}", encodeURIComponent(consulta));
}

/* Las imágenes propias del evento (los mapas que adjunta GDACS) sí vienen en el
 * feed, porque no hay forma de derivarlas. */
function imagenesPropias(evento) {
  const media = evento.media ?? {};
  const recursos = Array.isArray(media.recursos) ? media.recursos : [];
  return [
    media.mapa ? { url: media.mapa, titulo: "Mapa de la fuente" } : null,
    ...recursos.map((r) => ({ url: r.url, titulo: r.titulo || "Mapa de la fuente" })),
  ].filter(Boolean);
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

  // La miniatura entra al final del DOM pero se ubica a la derecha por CSS: si
  // el satélite no responde, `onerror` la saca y la tarjeta queda como estaba.
  const miniatura = urlSatelite(evento, { ancho: 160, alto: 160 });
  if (miniatura) {
    const foto = document.createElement("img");
    foto.className = "evento__foto";
    foto.src = miniatura;
    foto.alt = "";
    foto.loading = "lazy";
    foto.decoding = "async";
    foto.addEventListener("error", () => foto.remove());
    boton.append(foto);
  }

  boton.addEventListener("click", () => {
    seleccionar(evento);
    abrirVisor(evento);
  });
  item.append(boton);
  return item;
}

/* ------------------------------------------------------------------- visor */

function abrirVisor(evento) {
  const visor = $("#visor");
  if (!visor) return;

  estado.detalle = evento;
  estado.fotograma = 0;

  const tipo = tipoDe(evento);
  const alerta = alertaDe(evento);
  $("#visor-titulo").textContent = `${tipo.icono} ${evento.titulo || tipo.etiqueta}`;
  $("#visor-meta").textContent = [
    alerta.etiqueta,
    fechaLegible(evento.fecha_evento),
    evento.pais,
    typeof evento.magnitud === "number"
      ? `${evento.magnitud} ${evento.unidad_magnitud || ""}`.trim()
      : null,
  ]
    .filter(Boolean)
    .join(" · ");

  pintarFotograma();
  pintarGaleria(evento);

  const dias = tieneFoto(evento) ? diasTimelapse(evento) : [];
  $("#visor-timelapse").hidden = dias.length < 2;
  $("#visor-dias").max = String(Math.max(dias.length - 1, 0));
  $("#visor-dias").value = "0";

  const videos = urlVideos(evento);
  $("#visor-videos").hidden = !videos;
  if (videos) $("#visor-videos").href = videos;

  $("#visor-fuente").hidden = !evento.url;
  if (evento.url) $("#visor-fuente").href = evento.url;

  visor.showModal();
}

function pintarFotograma() {
  const evento = estado.detalle;
  const foto = $("#visor-foto");
  const pie = $("#visor-pie");
  if (!evento || !foto) return;

  if (!tieneFoto(evento)) {
    foto.hidden = true;
    pie.textContent = "Este evento no informa posición, así que no hay foto satelital.";
    return;
  }

  const dias = diasTimelapse(evento);
  const dia = dias[Math.min(estado.fotograma, dias.length - 1)] ?? null;
  const satelite = estado.media?.satelite ?? MEDIA_POR_DEFECTO.satelite;

  foto.hidden = false;
  foto.src = urlSatelite(evento, { fecha: dia, ancho: 768, alto: 768 });
  foto.alt = `Vista satelital del área del evento el ${dia}`;
  pie.textContent = `${dia} · ${satelite.credito}`;
}

function pintarGaleria(evento) {
  const galeria = $("#visor-galeria");
  if (!galeria) return;

  const imagenes = imagenesPropias(evento);
  galeria.hidden = imagenes.length === 0;
  galeria.replaceChildren(
    ...imagenes.map(({ url, titulo }) => {
      const enlace = document.createElement("a");
      enlace.href = url;
      enlace.target = "_blank";
      enlace.rel = "noopener";
      const imagen = document.createElement("img");
      imagen.src = url;
      imagen.alt = titulo;
      imagen.loading = "lazy";
      imagen.addEventListener("error", () => enlace.remove());
      enlace.append(imagen);
      return enlace;
    })
  );
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
  $("#tile-24h").textContent = lista.filter(
    (e) => horasDesde(e.fecha_evento) <= HORAS_VENTANA_ACTIVIDAD
  ).length;
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
  // El feed manda sobre las plantillas de media: así se cambia de capa o de
  // proveedor de imágenes desde el cron, sin tocar esta página.
  estado.media = documento.media ?? MEDIA_POR_DEFECTO;
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

  $("#visor-dias").addEventListener("input", (evento) => {
    estado.fotograma = Number(evento.target.value);
    pintarFotograma();
  });

  $("#visor-cerrar").addEventListener("click", () => $("#visor").close());

  // Clic en el fondo del diálogo: el <dialog> recibe el evento solo cuando se
  // tocó fuera del contenido, porque el contenido lo tapa entero.
  $("#visor").addEventListener("click", (evento) => {
    if (evento.target.id === "visor") $("#visor").close();
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
