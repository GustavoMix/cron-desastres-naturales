package com.gustavomix.desastres.core

import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class FiltroTest {

    private val reales: List<Evento> =
        FeedParser.parsear(recursoDePrueba("/recientes_real.json")).eventos

    private fun evento(
        id: String = "x",
        tipo: String = "sismo",
        paises: List<String> = emptyList(),
        magnitud: Double? = null,
        alerta: String = "",
        titulo: String = "Un evento",
        lugar: String = "",
        pais: String = "",
        fecha: String = "2026-08-06T00:00:00Z",
    ) = Evento(
        id = id,
        fuente = "usgs",
        tipo = tipo,
        titulo = titulo,
        fechaEvento = fecha,
        paises = paises,
        magnitud = magnitud,
        nivelAlerta = alerta,
        lugar = lugar,
        pais = pais,
    )

    @Test
    fun `el filtro por defecto no saca nada`() {
        assertEquals(reales.size, reales.filtrar(Filtro()).size)
    }

    @Test
    fun `filtra por pais con codigo iso`() {
        val filipinas = reales.filtrar(Filtro(paises = setOf("PH")))
        assertTrue(filipinas.isNotEmpty())
        assertTrue(filipinas.all { "PH" in it.paises })
    }

    @Test
    fun `un evento multipais aparece bajo cada uno de sus paises`() {
        // Caso real del fixture: un incendio en Angola y RD del Congo.
        val angola = reales.filtrar(Filtro(paises = setOf("AO")))
        val congo = reales.filtrar(Filtro(paises = setOf("CD")))

        assertTrue(angola.isNotEmpty())
        assertContentEquals(angola.map { it.id }, congo.map { it.id })
    }

    @Test
    fun `los sismos de eeuu caen bajo US y no bajo el estado`() {
        // El scraper ya tradujo "Oregon" a US; sin eso este filtro estaría roto.
        val eeuu = reales.filtrar(Filtro(paises = setOf("US")))
        assertTrue(eeuu.isNotEmpty())
        assertTrue(eeuu.any { it.pais == "Oregon" })
    }

    @Test
    fun `un evento sin pais resuelto no matchea ningun filtro de pais`() {
        // Regiones oceánicas ("south of the Kermadec Islands"): no sabemos
        // dónde ubicarlas, así que no aparecen bajo ningún país concreto.
        val sinPais = reales.single { it.paises.isEmpty() }
        val todos = reales.filtrar(Filtro(paises = setOf("NZ", "US", "PH")))

        assertTrue(sinPais.id !in todos.map { it.id })
    }

    @Test
    fun `el codigo de pais no distingue mayusculas`() {
        assertEquals(
            reales.filtrar(Filtro(paises = setOf("PH"))).size,
            reales.filtrar(Filtro(paises = setOf("ph"))).size,
        )
    }

    @Test
    fun `filtra por tipo`() {
        val incendios = reales.filtrar(Filtro(tipos = setOf(TipoEvento.INCENDIO)))
        assertTrue(incendios.isNotEmpty())
        assertTrue(incendios.all { it.tipoEvento == TipoEvento.INCENDIO })
    }

    @Test
    fun `el nivel minimo deja pasar de ahi para arriba`() {
        val graves = reales.filtrar(Filtro(alertaMinima = NivelAlerta.NARANJA))
        assertTrue(graves.isNotEmpty())
        assertTrue(graves.all { it.alerta.peso >= NivelAlerta.NARANJA.peso })
    }

    @Test
    fun `el umbral de magnitud solo aplica a sismos`() {
        // La "magnitud" de un incendio son hectáreas quemadas y la de un ciclón
        // km/h: compararlas contra una escala sísmica no significa nada.
        val eventos = listOf(
            evento(id = "sismo-chico", tipo = "sismo", magnitud = 2.0),
            evento(id = "sismo-grande", tipo = "sismo", magnitud = 6.0),
            evento(id = "incendio", tipo = "incendio", magnitud = 1.0),
            evento(id = "ciclon", tipo = "ciclon", magnitud = 3.0),
        )

        val resultado = eventos.filtrar(Filtro(magnitudMinimaSismo = 4.0)).map { it.id }

        assertEquals(setOf("sismo-grande", "incendio", "ciclon"), resultado.toSet())
    }

    @Test
    fun `un sismo sin magnitud conocida no se descarta por el umbral`() {
        val eventos = listOf(evento(id = "sin-mag", tipo = "sismo", magnitud = null))
        assertEquals(1, eventos.filtrar(Filtro(magnitudMinimaSismo = 5.0)).size)
    }

    @Test
    fun `la busqueda por texto mira titulo lugar y pais`() {
        val eventos = listOf(
            evento(id = "por-titulo", titulo = "Sismo en Sucre"),
            evento(id = "por-lugar", lugar = "12 km al norte de Sucre"),
            evento(id = "por-pais", pais = "Sucrelandia"),
            evento(id = "sin-relacion", titulo = "Otra cosa"),
        )

        val resultado = eventos.filtrar(Filtro(texto = "sucre")).map { it.id }

        assertEquals(setOf("por-titulo", "por-lugar", "por-pais"), resultado.toSet())
    }

    @Test
    fun `la busqueda no distingue mayusculas ni espacios al borde`() {
        val eventos = listOf(evento(titulo = "Sismo en Bolivia"))
        assertEquals(1, eventos.filtrar(Filtro(texto = "  BOLIVIA ")).size)
    }

    @Test
    fun `los criterios se combinan con and`() {
        val eventos = listOf(
            evento(id = "si", tipo = "sismo", paises = listOf("BO"), magnitud = 6.0),
            evento(id = "otro-pais", tipo = "sismo", paises = listOf("CL"), magnitud = 6.0),
            evento(id = "otro-tipo", tipo = "incendio", paises = listOf("BO")),
        )

        val resultado = eventos.filtrar(
            Filtro(paises = setOf("BO"), tipos = setOf(TipoEvento.SISMO), magnitudMinimaSismo = 5.0)
        )

        assertEquals(listOf("si"), resultado.map { it.id })
    }

    @Test
    fun `ordena de mas reciente a mas antiguo`() {
        val eventos = listOf(
            evento(id = "viejo", fecha = "2026-08-01T00:00:00Z"),
            evento(id = "nuevo", fecha = "2026-08-05T00:00:00Z"),
            evento(id = "medio", fecha = "2026-08-03T00:00:00Z"),
        )

        assertContentEquals(
            listOf("nuevo", "medio", "viejo"),
            eventos.filtrar(Filtro()).map { it.id },
        )
    }

    @Test
    fun `los eventos con fecha ilegible van al final sin desaparecer`() {
        val eventos = listOf(
            evento(id = "roto", fecha = "cualquier cosa"),
            evento(id = "bueno", fecha = "2026-08-05T00:00:00Z"),
        )

        assertContentEquals(listOf("bueno", "roto"), eventos.filtrar(Filtro()).map { it.id })
    }

    @Test
    fun `paisesDisponibles no inventa opciones para el selector`() {
        val disponibles = reales.paisesDisponibles()

        assertEquals(disponibles.sorted(), disponibles, "debe venir ordenado")
        assertEquals(disponibles.distinct(), disponibles, "sin repetidos")
        assertTrue(disponibles.all { codigo -> reales.any { codigo in it.paises } })
    }

    @Test
    fun `conteoPorTipo cuadra con el total`() {
        assertEquals(reales.size, reales.conteoPorTipo().values.sum())
    }
}
