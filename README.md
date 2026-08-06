# cron-desastres-naturales

Scraper programado de alertas de desastres naturales. Corre cada hora en GitHub
Actions, consulta fuentes públicas, normaliza todo a un modelo común y versiona
el resultado como JSON y CSV dentro del propio repo.

## Fuentes

| Fuente | Qué trae | Formato | API key |
|---|---|---|---|
| [USGS Earthquake Hazards Program](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php) | Sismos de las últimas 24 h, mundial | GeoJSON | No |
| [GDACS](https://www.gdacs.org/xml/rss.xml) | Sismos, ciclones, inundaciones, volcanes, sequías e incendios | RSS | No |

Las dos son complementarias y **no se deduplican entre sí**: un mismo sismo puede
aparecer como registro de USGS y como registro de GDACS, con magnitudes que no
coinciden exactamente porque cada organismo la calcula distinto. Se conservan
ambos a propósito; para correlacionarlos, cruzá por `fecha_evento` y coordenadas.

## Salida

Todo se escribe en `datos/`:

- **`recientes.json`** — **el que consume el front.** Últimos 7 días, sin el campo `extra` y sin micro-sismos. Es el único que conviene bajar desde una app móvil.
- **`eventos.json`** — histórico completo, más recientes primero. Pesado; para análisis, no para la app.
- **`eventos.csv`** — el mismo histórico plano, listo para abrir en una planilla.
- **`resumen.json`** — metadatos de la última corrida: qué fuente respondió, cuántos eventos nuevos/actualizados, conteos por tipo y por nivel de alerta.

Cada evento tiene esta forma:

```json
{
  "id": "usgs:us7000abcd",
  "id_agrupado": "usgs:us7000abcd",
  "fuente": "usgs",
  "tipo": "sismo",
  "titulo": "M 5.4 - 24 km SW of Coquimbo, Chile",
  "fecha_evento": "2026-08-06T01:33:20Z",
  "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000abcd",
  "lugar": "24 km SW of Coquimbo, Chile",
  "pais": "Chile",
  "magnitud": 5.4,
  "unidad_magnitud": "mww",
  "nivel_alerta": "verde",
  "latitud": -30.0512,
  "longitud": -71.4123,
  "profundidad_km": 42.6,
  "fecha_actualizacion": "2026-08-06T02:23:20Z",
  "visto_por_primera_vez": "2026-08-06T02:42:08Z",
  "cambiado_por_ultima_vez": "2026-08-06T02:42:08Z",
  "extra": { "tsunami": 0, "significancia": 449 }
}
```

Vocabulario normalizado, igual para todas las fuentes:

- `tipo`: `sismo`, `ciclon`, `inundacion`, `volcan`, `incendio`, `sequia`, `otro`
- `nivel_alerta`: `verde`, `amarilla`, `naranja`, `roja` (vacío si la fuente no lo informa)
- fechas: ISO 8601 en UTC, siempre con sufijo `Z`

**`id`** es único por registro. **`id_agrupado`** identifica el fenómeno del
mundo real: para USGS coinciden, pero GDACS republica un mismo evento por
episodios y `id` los distingue mientras `id_agrupado` los junta. Para colgar
comentarios de usuarios, **usá `id_agrupado`** — si no, un ciclón de cinco días
desparrama sus comentarios entre veinte "eventos" distintos.

`visto_por_primera_vez` y `cambiado_por_ultima_vez` son bookkeeping del scraper,
no de la fuente. La segunda es **la última vez que el registro cambió**, no la
última vez que se lo vio: si el feed lo republica idéntico, el valor no se toca.
Esa distinción no es cosmética — es lo que hace viable guardar el histórico en
git (ver más abajo).

## El cron

`.github/workflows/scraper.yml` corre `17 * * * *` (cada hora, minuto 17 — los
minutos redondos están congestionados en Actions y las corridas programadas se
demoran). También se puede disparar a mano desde la pestaña *Actions*, con
opción de elegir fuentes o hacer un `--dry-run`.

El workflow commitea `datos/` con el usuario `github-actions[bot]`. Como
`resumen.json` lleva la marca de tiempo de la corrida, **hay un commit por hora
aunque no haya novedades** — es el precio de que la app pueda detectar un
scraper caído en vez de mostrar datos viejos como si fueran actuales.

Lo que sí está garantizado es que los archivos pesados **no cambian si no hay
noticias**: `eventos.json` queda byte a byte idéntico entre dos corridas sin
novedades. Eso es lo que importa para el tamaño del repo, y depende de dos
propiedades que hay que cuidar al tocar el código:

- La salida es determinística: orden fijo y claves ordenadas.
- Un evento revisitado sin cambios se deja exactamente como estaba, sin tocarle
  ninguna marca de tiempo. Si `cambiado_por_ultima_vez` se actualizara en cada
  corrida, las decenas de miles de filas del histórico cambiarían cada hora y
  cada commit pesaría el archivo entero.

Ambas están cubiertas por tests (`test_guardar_es_deterministico` y
`test_una_corrida_sin_novedades_deja_eventos_json_byte_a_byte_igual`).

Códigos de salida, que el workflow distingue:

| Código | Significado | Qué hace el workflow |
|---|---|---|
| `0` | Todas las fuentes respondieron | Commitea si hay cambios |
| `2` | Alguna fuente falló, otra respondió | Commitea lo que hay + anota un warning |
| `1` | Ninguna fuente respondió | Falla el job y **no toca** el histórico |

Esa distinción importa: ante una caída total no se escribe nada, así que un
outage de USGS y GDACS no puede vaciar el archivo histórico.

## Uso local

Sin dependencias de runtime — solo stdlib de Python 3.10+.

```bash
python -m desastres --help

# Corrida completa
PYTHONPATH=src python -m desastres --salida datos

# Solo sismos, sin escribir nada
PYTHONPATH=src python -m desastres --fuentes usgs --dry-run
```

Opciones principales:

| Opción | Default | Qué hace |
|---|---|---|
| `--fuentes` | `usgs,gdacs` | Fuentes a consultar |
| `--retencion-dias` | `180` | Descarta del histórico lo más viejo que N días (`0` no poda) |
| `--dias-recientes` | `7` | Ventana de `recientes.json` |
| `--recientes-magnitud-minima` | `2.5` | Excluye de `recientes.json` los sismos por debajo de esta magnitud |
| `--dry-run` | — | Consulta y reporta sin escribir |

El umbral de magnitud **solo afecta a `recientes.json`, y solo a sismos con
magnitud conocida**: el histórico guarda todo, y un ciclón o una inundación
nunca se filtran (sus magnitudes no son comparables con la escala sísmica).
Existe porque USGS publica cientos de micro-sismos diarios de California que a
una app de público general no le aportan nada y le multiplican la descarga.
Poné `0` para no filtrar nada.

## Consumir los datos desde una app

**No pegues contra `raw.githubusercontent.com`**: no es un CDN, tiene rate
limits y te va a tirar `429`. Usá jsDelivr, que es gratis y sí lo es:

```
https://cdn.jsdelivr.net/gh/GustavoMix/cron-desastres-naturales@main/datos/recientes.json
```

Dos cosas que conviene hacer del lado del cliente:

- **Cachear con ETag.** Si el archivo no cambió, el servidor responde `304` y no
  bajás nada. En Android con OkHttp es configurar un `Cache` y listo.
- **Chequear `generado` antes de mostrar nada.** Si esa marca tiene muchas horas,
  el scraper está caído y los datos están viejos. En una app de desastres,
  mostrar información vieja como si fuera actual es peor que no mostrar nada:
  avisale al usuario.

## Desarrollo

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

Los tests no tocan la red: cada fuente separa `obtener()` (HTTP) de `parsear()`
(puro), y las pruebas ejercitan el parseo contra fixtures en `tests/fixtures/`
que incluyen los casos feos reales — campos nulos, coordenadas sin profundidad,
items sin identificador, fechas ausentes.

## Agregar una fuente

1. Creá `src/desastres/fuentes/<nombre>.py` con una clase que tenga `nombre`, `url`, `obtener()` y `parsear()` (ver `fuentes/base.py`).
2. En `parsear()`, traducí al modelo de `modelo.py` y prefijá los ids con el nombre de la fuente (`<nombre>:<id-interno>`) para que no colisionen con otras.
3. Registrala en `FUENTES_DISPONIBLES` dentro de `cli.py`.
4. Agregá un fixture y sus tests.

## Limitaciones conocidas

- **`pais` en eventos de USGS es aproximado.** El feed no trae país estructurado; se toma lo que sigue a la última coma de `place`, que para sismos en EE. UU. da un estado (`CA`) y no un país.
- **GDACS republica un mismo evento por episodios.** El `episodeid` forma parte del `id`, así que un ciclón de larga vida deja un registro por episodio en lugar de uno solo actualizándose. Es intencional: preserva la evolución del evento. Para agrupar, usá `id_agrupado`.
- **Ventana de USGS: 24 h.** Si el cron estuvo caído más de un día, esos sismos se pierden. Para recuperarlos habría que usar el feed de 7 días o la API de consulta por rango.
- **La poda puede dejar comentarios huérfanos.** Cuando se agreguen comentarios de usuarios, un evento podado del histórico dejará comentarios apuntando a un `id_agrupado` que ya no está en los feeds. Hay que decidirlo antes: o la app lo tolera, o no se poda lo que tiene comentarios.
- **El scraper es un espejo, no una autoridad.** Los datos son de USGS y GDACS, con sus propias latencias y revisiones: una magnitud puede cambiar horas después. No sirve para alertas de evacuación — para eso están los organismos oficiales de cada país.
