package com.gustavomix.desastres.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class FeedParserTest {

    private val feed: Feed = FeedParser.parsear(recursoDePrueba("/recientes_real.json"))

    @Test
    fun `parsea el feed real del scraper`() {
        assertEquals(1, feed.version)
        assertEquals(7, feed.eventos.size)
        assertEquals(feed.total, feed.eventos.size)
        assertNotNull(feed.generadoEn)
    }

    @Test
    fun `ignora las claves que no conoce`() {
        // El scraper agrega campos sin coordinarse con la app, y una app ya
        // publicada no se actualiza al mismo tiempo que el feed. Si esto
        // fallara, un campo nuevo tumbaría a todos los usuarios viejos.
        val conCampoNuevo = """
            {"version":1,"generado":"2026-08-06T15:00:00Z","total":1,
             "campo_del_futuro":{"a":1},
             "eventos":[{"id":"usgs:x","fuente":"usgs","tipo":"sismo","titulo":"M 5",
                         "fecha_evento":"2026-08-06T00:00:00Z","algo_nuevo":42}]}
        """.trimIndent()

        val resultado = FeedParser.parsear(conCampoNuevo)

        assertEquals(1, resultado.eventos.size)
        assertEquals("usgs:x", resultado.eventos.first().id)
    }

    @Test
    fun `un tipo desconocido no rompe el parseo`() {
        // Si `tipo` fuera un enum, un valor nuevo reventaría el feed entero.
        val json = """
            {"eventos":[{"id":"x","fuente":"gdacs","tipo":"tsunami","titulo":"t",
                         "fecha_evento":"2026-08-06T00:00:00Z"}]}
        """.trimIndent()

        val evento = FeedParser.parsear(json).eventos.single()

        assertEquals(TipoEvento.DESCONOCIDO, evento.tipoEvento)
        assertEquals("tsunami", evento.tipo)
    }

    @Test
    fun `un nivel de alerta desconocido cae en sin dato`() {
        val json = """
            {"eventos":[{"id":"x","fuente":"gdacs","tipo":"sismo","titulo":"t",
                         "fecha_evento":"2026-08-06T00:00:00Z","nivel_alerta":"morada"}]}
        """.trimIndent()

        assertEquals(NivelAlerta.SIN_DATO, FeedParser.parsear(json).eventos.single().alerta)
    }

    @Test
    fun `feed vacio se parsea sin romper`() {
        val vacio = FeedParser.parsear("""{"version":1,"generado":"","total":0,"eventos":[]}""")
        assertTrue(vacio.eventos.isEmpty())
        assertNull(vacio.generadoEn)
    }

    @Test
    fun `una fecha ilegible no revienta el evento`() {
        val json = """
            {"eventos":[{"id":"x","fuente":"usgs","tipo":"sismo","titulo":"t",
                         "fecha_evento":"ayer a la tarde"}]}
        """.trimIndent()

        assertNull(FeedParser.parsear(json).eventos.single().instante)
    }

    @Test
    fun `mapea los campos con guion bajo`() {
        val sismo = feed.eventos.first { it.id == "usgs:us6000tibh" || it.fuente == "usgs" }
        assertTrue(sismo.fechaEvento.isNotBlank())
        assertTrue(sismo.idAgrupado.isNotBlank())
    }

    @Test
    fun `conserva el id agrupado sin episodio en eventos de gdacs`() {
        // Es la clave a la que se van a colgar los comentarios: si llevara el
        // episodio, un ciclón de días fragmentaría sus comentarios.
        val conEpisodio = feed.eventos.filter { it.fuente == "gdacs" && it.id != it.idAgrupado }
        assertTrue(conEpisodio.isNotEmpty(), "el fixture debe traer al menos un evento con episodio")
        conEpisodio.forEach { evento ->
            assertTrue(evento.id.startsWith(evento.idAgrupado))
            assertTrue(evento.idAgrupado.count { it == ':' } < evento.id.count { it == ':' })
        }
    }
}
