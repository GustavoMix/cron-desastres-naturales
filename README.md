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

- **`eventos.json`** — histórico completo, más recientes primero.
- **`eventos.csv`** — el mismo histórico plano, sin el campo `extra`, listo para abrir en una planilla.
- **`resumen.json`** — metadatos de la última corrida: qué fuente respondió, cuántos eventos nuevos/actualizados, conteos por tipo y por nivel de alerta.

Cada evento tiene esta forma:

```json
{
  "id": "usgs:us7000abcd",
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
  "visto_por_ultima_vez": "2026-08-06T03:17:04Z",
  "extra": { "tsunami": 0, "significancia": 449 }
}
```

Vocabulario normalizado, igual para todas las fuentes:

- `tipo`: `sismo`, `ciclon`, `inundacion`, `volcan`, `incendio`, `sequia`, `otro`
- `nivel_alerta`: `verde`, `amarilla`, `naranja`, `roja` (vacío si la fuente no lo informa)
- fechas: ISO 8601 en UTC, siempre con sufijo `Z`

`visto_por_primera_vez` y `visto_por_ultima_vez` son bookkeeping del scraper, no
de la fuente: sirven para saber cuándo apareció un evento en el feed y cuándo se
lo vio por última vez. Un evento que ya se conocía nunca pierde su
`visto_por_primera_vez` original.

## El cron

`.github/workflows/scraper.yml` corre `17 * * * *` (cada hora, minuto 17 — los
minutos redondos están congestionados en Actions y las corridas programadas se
demoran). También se puede disparar a mano desde la pestaña *Actions*, con
opción de elegir fuentes o hacer un `--dry-run`.

Si hay cambios, el workflow commitea `datos/` con el usuario `github-actions[bot]`.
Si los feeds no traen nada nuevo, no genera commit: la salida es determinística
(orden fijo, claves ordenadas), así que dos corridas idénticas producen bytes
idénticos.

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

Opciones: `--fuentes`, `--salida`, `--retencion-dias` (por defecto 400; `0`
desactiva la poda), `--timeout`, `--reintentos`, `--dry-run`, `-v`.

La poda existe para que el histórico no crezca sin techo: cada corrida reescribe
el archivo entero, así que un JSON de decenas de MB encarece cada commit.

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
- **GDACS republica un mismo evento por episodios.** El `episodeid` forma parte del id, así que un ciclón de larga vida deja un registro por episodio en lugar de uno solo actualizándose. Es intencional: preserva la evolución del evento.
- **Ventana de USGS: 24 h.** Si el cron estuvo caído más de un día, esos sismos se pierden. Para recuperarlos habría que usar el feed de 7 días o la API de consulta por rango.
