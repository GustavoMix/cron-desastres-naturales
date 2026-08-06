package com.gustavomix.desastres.ui

import androidx.compose.ui.graphics.Color
import com.gustavomix.desastres.core.Evento
import com.gustavomix.desastres.core.Frescura
import com.gustavomix.desastres.core.NivelAlerta
import com.gustavomix.desastres.core.TipoEvento
import java.time.Duration
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Cómo se ve cada nivel de alerta.
 *
 * El color **nunca** viaja solo: `etiqueta` va siempre al lado. Amarilla y
 * naranja son casi indistinguibles a simple vista (ΔE 13.6, por debajo del piso
 * de 15 para visión normal) y con daltonismo verde y roja se confunden. Si en
 * algún lugar de la UI queda solo el color, ese lugar está mal.
 */
enum class EstiloAlerta(val color: Color, val etiqueta: String) {
    ROJA(Color(0xFFD03B3B), "Alerta roja"),
    NARANJA(Color(0xFFEC835A), "Alerta naranja"),
    AMARILLA(Color(0xFFFAB219), "Alerta amarilla"),
    VERDE(Color(0xFF0CA30C), "Alerta verde"),
    SIN_DATO(Color(0xFF898781), "Sin nivel informado");

    companion object {
        fun de(nivel: NivelAlerta): EstiloAlerta = when (nivel) {
            NivelAlerta.ROJA -> ROJA
            NivelAlerta.NARANJA -> NARANJA
            NivelAlerta.AMARILLA -> AMARILLA
            NivelAlerta.VERDE -> VERDE
            NivelAlerta.SIN_DATO -> SIN_DATO
        }
    }
}

fun TipoEvento.icono(): String = when (this) {
    TipoEvento.SISMO -> "〰️"
    TipoEvento.CICLON -> "🌀"
    TipoEvento.INUNDACION -> "🌊"
    TipoEvento.VOLCAN -> "🌋"
    TipoEvento.INCENDIO -> "🔥"
    TipoEvento.SEQUIA -> "🏜️"
    TipoEvento.OTRO, TipoEvento.DESCONOCIDO -> "◆"
}

fun TipoEvento.etiqueta(): String = when (this) {
    TipoEvento.SISMO -> "Sismo"
    TipoEvento.CICLON -> "Ciclón"
    TipoEvento.INUNDACION -> "Inundación"
    TipoEvento.VOLCAN -> "Volcán"
    TipoEvento.INCENDIO -> "Incendio"
    TipoEvento.SEQUIA -> "Sequía"
    TipoEvento.OTRO -> "Otro"
    TipoEvento.DESCONOCIDO -> "Sin clasificar"
}

private val FORMATO_FECHA: DateTimeFormatter =
    DateTimeFormatter.ofPattern("dd MMM, HH:mm", Locale("es"))

fun Evento.fechaLegible(zona: ZoneId = ZoneId.systemDefault()): String =
    instante?.atZone(zona)?.format(FORMATO_FECHA) ?: "fecha desconocida"

fun Duration.legible(): String = when {
    toHours() < 1 -> "hace ${toMinutes().coerceAtLeast(1)} min"
    toHours() < 48 -> "hace ${toHours()} h"
    else -> "hace ${toDays()} días"
}

/** Texto del aviso de datos viejos, o `null` si no hace falta advertir nada. */
fun Frescura.mensaje(): String? = when (this) {
    is Frescura.Fresca -> null
    is Frescura.Vieja ->
        "Datos desactualizados: la última actualización fue ${antiguedad.legible()}. " +
            "Puede haber eventos recientes que no aparezcan acá."
    is Frescura.Critica ->
        "Datos muy desactualizados: ${antiguedad.legible()}. " +
            "Es probable que el scraper esté caído; no te guíes por esta información."
    Frescura.Desconocida ->
        "No se pudo determinar cuándo se actualizaron estos datos."
}

fun Frescura.colorAviso(): Color = when (this) {
    is Frescura.Critica -> EstiloAlerta.ROJA.color
    is Frescura.Vieja -> EstiloAlerta.AMARILLA.color
    else -> EstiloAlerta.SIN_DATO.color
}
