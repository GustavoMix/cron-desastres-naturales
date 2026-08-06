package com.gustavomix.desastres.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class EventoTest {

    private fun evento(magnitud: Double?, unidad: String) = Evento(
        id = "x", fuente = "usgs", tipo = "sismo", titulo = "t",
        fechaEvento = "2026-08-06T00:00:00Z", magnitud = magnitud, unidadMagnitud = unidad,
    )

    @Test
    fun `la magnitud legible siempre lleva su unidad`() {
        // Sin la unidad el número miente: 6568 en un incendio son hectáreas.
        assertEquals("5.4 mww", evento(5.4, "mww").magnitudLegible)
        assertEquals("6568 ha", evento(6568.0, "ha").magnitudLegible)
        assertEquals("185 km/h", evento(185.0, "km/h").magnitudLegible)
    }

    @Test
    fun `sin magnitud no hay nada que mostrar`() {
        assertNull(evento(null, "ha").magnitudLegible)
    }

    @Test
    fun `sin unidad muestra el numero solo`() {
        assertEquals("5.4", evento(5.4, "").magnitudLegible)
    }

    @Test
    fun `los niveles de alerta estan ordenados de menor a mayor`() {
        val pesos = listOf(
            NivelAlerta.SIN_DATO, NivelAlerta.VERDE, NivelAlerta.AMARILLA,
            NivelAlerta.NARANJA, NivelAlerta.ROJA,
        ).map { it.peso }

        assertEquals(pesos.sorted(), pesos)
    }
}
