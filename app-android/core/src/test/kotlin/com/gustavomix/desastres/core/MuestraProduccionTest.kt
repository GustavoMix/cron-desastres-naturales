package com.gustavomix.desastres.core

import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Regresión contra datos de producción.
 *
 * `muestra_produccion.json` es una muestra estratificada de un feed real
 * (768 eventos, generado el 2026-08-06): incluye todos los casos raros que
 * aparecieron —multipaís, sin país, GDACS con episodio, magnitud en hectáreas,
 * alertas naranja y roja, eventos sin magnitud— más un relleno aleatorio.
 *
 * Estos tests afirman **invariantes**, no valores puntuales: sirven para
 * detectar que el feed cambió de forma, que es la manera realista en que esto
 * se va a romper. Cuando el scraper cambie el contrato, regenerá la muestra.
 */
class MuestraProduccionTest {

    private val feed: Feed = FeedParser.parsear(recursoDePrueba("/muestra_produccion.json"))

    @Test
    fun `parsea la muestra completa`() {
        assertEquals(feed.total, feed.eventos.size)
        assertTrue(feed.eventos.size >= 50)
    }

    @Test
    fun `ningun evento real cae en tipo desconocido`() {
        // Si esto falla, el scraper agregó un tipo y hay que sumarlo a
        // TipoEvento — la app no se rompe, pero ese tipo se muestra como "◆".
        val desconocidos = feed.eventos.filter { it.tipoEvento == TipoEvento.DESCONOCIDO }
        assertTrue(desconocidos.isEmpty(), "tipos sin mapear: ${desconocidos.map { it.tipo }.distinct()}")
    }

    @Test
    fun `todas las fechas del feed real son parseables`() {
        val ilegibles = feed.eventos.filter { it.instante == null }
        assertTrue(ilegibles.isEmpty(), "fechas ilegibles: ${ilegibles.map { it.fechaEvento }}")
    }

    @Test
    fun `todo codigo de pais tiene forma iso alfa-2`() {
        val invalidos = feed.eventos
            .flatMap { it.paises }
            .filterNot { it.length == 2 && it.all(Char::isUpperCase) }
        assertTrue(invalidos.isEmpty(), "códigos con forma rara: ${invalidos.distinct()}")
    }

    @Test
    fun `los eventos sin pais son los que no se pueden ubicar`() {
        // Regiones oceánicas: el scraper no les resuelve país a propósito.
        // Que existan está bien; que sean la mayoría, no.
        val sinPais = feed.eventos.count { it.paises.isEmpty() }
        assertTrue(sinPais < feed.eventos.size / 2, "demasiados eventos sin país: $sinPais")
    }

    @Test
    fun `el id agrupado de gdacs nunca conserva el episodio`() {
        feed.eventos.filter { it.fuente == "gdacs" }.forEach { evento ->
            assertTrue(
                evento.id.startsWith(evento.idAgrupado),
                "${evento.id} no deriva de ${evento.idAgrupado}",
            )
        }
    }

    @Test
    fun `filtrar por pais devuelve solo eventos de ese pais`() {
        feed.eventos.paisesDisponibles().take(5).forEach { codigo ->
            val filtrados = feed.eventos.filtrar(Filtro(paises = setOf(codigo)))
            assertTrue(filtrados.isNotEmpty(), "$codigo está en el selector pero no filtra nada")
            assertTrue(filtrados.all { codigo in it.paises })
        }
    }

    @Test
    fun `el umbral sismico no descarta incendios medidos en hectareas`() {
        // Caso real: un incendio con magnitud 6568 ha. Si el umbral se aplicara
        // a todo, un filtro de "magnitud mínima 5" dejaría pasar incendios por
        // hectáreas y descartaría sismos de M4 — sin sentido en ambos lados.
        val incendios = feed.eventos.filter { it.tipoEvento == TipoEvento.INCENDIO }
        val filtrados = feed.eventos.filtrar(Filtro(magnitudMinimaSismo = 9.0))

        assertTrue(incendios.isNotEmpty(), "la muestra debe traer incendios")
        assertTrue(incendios.all { it.id in filtrados.map { f -> f.id } })
    }

    @Test
    fun `un feed recien generado se considera fresco`() {
        val generado = requireNotNull(feed.generadoEn)
        assertTrue(EvaluadorDeFrescura().evaluar(generado, generado) is Frescura.Fresca)
    }

    @Test
    fun `la magnitud siempre se muestra con su unidad`() {
        feed.eventos.filter { it.magnitud != null && it.unidadMagnitud.isNotBlank() }.forEach {
            assertTrue(
                it.magnitudLegible!!.endsWith(it.unidadMagnitud),
                "${it.id} muestra '${it.magnitudLegible}' sin la unidad ${it.unidadMagnitud}",
            )
        }
    }
}
