package com.gustavomix.desastres.core

import java.time.Instant
import java.time.format.DateTimeParseException
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/** El documento completo de `recientes.json`. */
@Serializable
data class Feed(
    val version: Int = 1,
    /** Cuándo corrió el scraper. Vacío si nunca corrió. */
    val generado: String = "",
    val total: Int = 0,
    val eventos: List<Evento> = emptyList(),
) {
    val generadoEn: Instant? get() = parsearInstante(generado)
}

/**
 * Parser del feed.
 *
 * `ignoreUnknownKeys` es deliberado y no debe sacarse: el scraper agrega campos
 * sin coordinarse con la app, y una app publicada no se actualiza al mismo
 * tiempo que el feed. Sin esto, cualquier campo nuevo tumbaría a todos los
 * usuarios que no hayan actualizado.
 */
object FeedParser {
    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = false
        explicitNulls = false
    }

    fun parsear(texto: String): Feed = json.decodeFromString(Feed.serializer(), texto)
}

/** Parsea ISO-8601 UTC (`2026-08-06T01:33:20Z`) tolerando basura. */
internal fun parsearInstante(texto: String): Instant? {
    if (texto.isBlank()) return null
    return try {
        Instant.parse(texto)
    } catch (_: DateTimeParseException) {
        null
    }
}
