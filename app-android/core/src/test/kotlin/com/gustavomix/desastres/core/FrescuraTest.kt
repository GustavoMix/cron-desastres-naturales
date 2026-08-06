package com.gustavomix.desastres.core

import java.time.Duration
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

class FrescuraTest {

    private val evaluador = EvaluadorDeFrescura()
    private val ahora: Instant = Instant.parse("2026-08-20T12:00:00Z")

    private fun haceDias(dias: Long): Instant = ahora.minus(Duration.ofDays(dias))

    @Test
    fun `datos de esta semana estan frescos`() {
        assertIs<Frescura.Fresca>(evaluador.evaluar(haceDias(3), ahora))
    }

    @Test
    fun `una corrida apenas demorada no dispara el aviso`() {
        // El cron es semanal y Actions atrasa los schedules rutinariamente: el
        // margen del octavo día evita gritar por una demora normal.
        assertIs<Frescura.Fresca>(evaluador.evaluar(haceDias(7), ahora))
    }

    @Test
    fun `pasada la ventana avisa`() {
        assertIs<Frescura.Vieja>(evaluador.evaluar(haceDias(9), ahora))
    }

    @Test
    fun `dos semanas sin datos es critico`() {
        assertIs<Frescura.Critica>(evaluador.evaluar(haceDias(16), ahora))
    }

    @Test
    fun `sin marca de generacion la frescura es desconocida`() {
        assertEquals(Frescura.Desconocida, evaluador.evaluar(generado = null, ahora = ahora))
        assertEquals(Frescura.Desconocida, evaluador.evaluar(Feed(generado = ""), ahora))
        assertEquals(Frescura.Desconocida, evaluador.evaluar(Feed(generado = "meh"), ahora))
    }

    @Test
    fun `solo el caso fresco se muestra sin aviso`() {
        assertFalse(evaluador.evaluar(haceDias(1), ahora).requiereAviso)
        assertTrue(evaluador.evaluar(haceDias(9), ahora).requiereAviso)
        assertTrue(evaluador.evaluar(haceDias(30), ahora).requiereAviso)
        assertTrue(Frescura.Desconocida.requiereAviso)
    }

    @Test
    fun `una marca en el futuro se trata como recien generada`() {
        // Relojes desfasados, no datos del futuro. Sin el clamp la antigüedad
        // saldría negativa y el cálculo de "hace cuánto" mostraría disparates.
        val resultado = evaluador.evaluar(ahora.plus(Duration.ofHours(3)), ahora)

        assertIs<Frescura.Fresca>(resultado)
        assertEquals(Duration.ZERO, resultado.antiguedad)
    }

    @Test
    fun `informa la antiguedad para poder mostrarla`() {
        val resultado = evaluador.evaluar(haceDias(10), ahora)
        assertIs<Frescura.Vieja>(resultado)
        assertEquals(10, resultado.antiguedad.toDays())
    }

    @Test
    fun `los umbrales se pueden ajustar a otra cadencia`() {
        // Si el scraper vuelve a correr cada hora, estos umbrales se mueven acá
        // y no hay que tocar la pantalla.
        val horario = EvaluadorDeFrescura(
            umbralViejo = Duration.ofHours(3),
            umbralCritico = Duration.ofHours(12),
        )

        assertIs<Frescura.Fresca>(horario.evaluar(ahora.minus(Duration.ofHours(1)), ahora))
        assertIs<Frescura.Vieja>(horario.evaluar(ahora.minus(Duration.ofHours(5)), ahora))
        assertIs<Frescura.Critica>(horario.evaluar(ahora.minus(Duration.ofHours(20)), ahora))
    }

    @Test
    fun `umbrales invertidos fallan al construir`() {
        assertFailsWith<IllegalArgumentException> {
            EvaluadorDeFrescura(umbralViejo = Duration.ofDays(10), umbralCritico = Duration.ofDays(2))
        }
    }
}
