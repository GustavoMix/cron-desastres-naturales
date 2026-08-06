package com.gustavomix.desastres.core

import java.time.Instant
import java.util.Locale

/**
 * Criterios de la pantalla principal.
 *
 * Los conjuntos vacíos significan "no filtrar por esto", no "no mostrar nada".
 * Es la convención que hace que el filtro por defecto muestre todo.
 */
data class Filtro(
    /** Códigos ISO-3166 alfa-2. Vacío = todos los países. */
    val paises: Set<String> = emptySet(),
    val tipos: Set<TipoEvento> = emptySet(),
    /** Nivel mínimo. `SIN_DATO` incluye a los que no informan nivel. */
    val alertaMinima: NivelAlerta = NivelAlerta.SIN_DATO,
    /** Solo aplica a sismos: ver la nota en [coincide]. */
    val magnitudMinimaSismo: Double = 0.0,
    val texto: String = "",
) {
    private val paisesNormalizados: Set<String> =
        paises.mapTo(mutableSetOf()) { it.trim().uppercase(Locale.ROOT) }

    private val textoNormalizado: String = texto.trim().lowercase(Locale.ROOT)

    fun coincide(evento: Evento): Boolean {
        if (paisesNormalizados.isNotEmpty()) {
            // Un evento sin país resuelto (regiones oceánicas) nunca matchea un
            // filtro de país concreto: es correcto, no sabemos dónde ubicarlo.
            if (evento.paises.none { it.uppercase(Locale.ROOT) in paisesNormalizados }) return false
        }

        if (tipos.isNotEmpty() && evento.tipoEvento !in tipos) return false

        if (evento.alerta.peso < alertaMinima.peso) return false

        // El umbral de magnitud se aplica SOLO a sismos, y solo si la magnitud
        // se conoce. En el resto de los tipos ese número mide otra cosa —
        // hectáreas quemadas en incendios, km/h en ciclones — y compararlo
        // contra una escala sísmica no significa nada.
        if (magnitudMinimaSismo > 0.0 && evento.tipoEvento == TipoEvento.SISMO) {
            val magnitud = evento.magnitud
            if (magnitud != null && magnitud < magnitudMinimaSismo) return false
        }

        if (textoNormalizado.isNotEmpty()) {
            val heno = buildString {
                append(evento.titulo).append(' ')
                append(evento.lugar).append(' ')
                append(evento.pais)
            }.lowercase(Locale.ROOT)
            if (!heno.contains(textoNormalizado)) return false
        }

        return true
    }
}

/** Aplica el filtro y ordena de más reciente a más antiguo. */
fun List<Evento>.filtrar(filtro: Filtro): List<Evento> =
    filter(filtro::coincide).ordenadosPorFecha()

/**
 * Más recientes primero. Los de fecha ilegible van al final en vez de romper el
 * orden o desaparecer; el `id` desempata para que el resultado sea estable.
 */
fun List<Evento>.ordenadosPorFecha(): List<Evento> =
    sortedWith(
        compareByDescending<Evento> { it.instante ?: Instant.MIN }.thenBy { it.id }
    )

/** Países presentes en la lista, para armar el selector sin inventar opciones. */
fun List<Evento>.paisesDisponibles(): List<String> =
    flatMap { it.paises }.map { it.uppercase(Locale.ROOT) }.distinct().sorted()

/** Conteo por tipo, para las etiquetas del selector. */
fun List<Evento>.conteoPorTipo(): Map<TipoEvento, Int> =
    groupingBy { it.tipoEvento }.eachCount()
