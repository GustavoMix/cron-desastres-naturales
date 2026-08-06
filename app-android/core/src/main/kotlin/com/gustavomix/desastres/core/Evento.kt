package com.gustavomix.desastres.core

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Un evento tal como viene en `recientes.json`.
 *
 * Todos los campos salvo los cinco primeros tienen valor por defecto, y el
 * parser ignora las claves que no conoce. Eso no es descuido: el scraper y la
 * app se publican por separado, así que una versión vieja de la app va a estar
 * leyendo feeds más nuevos durante meses. Un campo agregado del lado del
 * scraper no puede tumbar a nadie.
 *
 * `tipo` y `nivelAlerta` se guardan como texto y se exponen tipados más abajo.
 * Si se declararan como enum, un valor nuevo en el scraper reventaría el parseo
 * del feed entero — no solo de ese evento.
 */
@Serializable
data class Evento(
    val id: String,
    val fuente: String,
    val tipo: String,
    val titulo: String,
    @SerialName("fecha_evento") val fechaEvento: String,
    @SerialName("id_agrupado") val idAgrupado: String = "",
    val url: String = "",
    val lugar: String = "",
    /** Texto crudo de la fuente: sirve para mostrar, no para filtrar. */
    val pais: String = "",
    /** Códigos ISO-3166 alfa-2. **Este** es el campo para filtrar por país. */
    val paises: List<String> = emptyList(),
    val magnitud: Double? = null,
    @SerialName("unidad_magnitud") val unidadMagnitud: String = "",
    @SerialName("nivel_alerta") val nivelAlerta: String = "",
    val latitud: Double? = null,
    val longitud: Double? = null,
    @SerialName("profundidad_km") val profundidadKm: Double? = null,
    @SerialName("fecha_actualizacion") val fechaActualizacion: String = "",
    @SerialName("visto_por_primera_vez") val vistoPorPrimeraVez: String = "",
    @SerialName("cambiado_por_ultima_vez") val cambiadoPorUltimaVez: String = "",
) {
    val tipoEvento: TipoEvento get() = TipoEvento.desde(tipo)

    val alerta: NivelAlerta get() = NivelAlerta.desde(nivelAlerta)

    /** Instante del evento, o `null` si la fuente mandó una fecha ilegible. */
    val instante: java.time.Instant? get() = parsearInstante(fechaEvento)

    /**
     * Magnitud lista para mostrar, con su unidad.
     *
     * La unidad importa: en incendios es hectáreas quemadas y en ciclones km/h,
     * así que un número suelto no significa nada.
     */
    val magnitudLegible: String?
        get() {
            val valor = magnitud ?: return null
            val texto = if (valor % 1.0 == 0.0) valor.toInt().toString() else valor.toString()
            return if (unidadMagnitud.isBlank()) texto else "$texto $unidadMagnitud"
        }
}

/** Tipos de amenaza del scraper. `DESCONOCIDO` absorbe los que se agreguen. */
enum class TipoEvento(val clave: String) {
    SISMO("sismo"),
    CICLON("ciclon"),
    INUNDACION("inundacion"),
    VOLCAN("volcan"),
    INCENDIO("incendio"),
    SEQUIA("sequia"),
    OTRO("otro"),
    DESCONOCIDO("");

    companion object {
        fun desde(clave: String?): TipoEvento =
            entries.firstOrNull { it.clave == clave?.trim()?.lowercase() } ?: DESCONOCIDO
    }
}

/**
 * Nivel de alerta, de menor a mayor. `peso` da el orden.
 *
 * La app **nunca** debe comunicar este dato solo con color: naranja y amarilla
 * son casi indistinguibles a simple vista, y con daltonismo verde y roja se
 * confunden. Siempre acompañar con la etiqueta.
 */
enum class NivelAlerta(val clave: String, val peso: Int) {
    SIN_DATO("", 0),
    VERDE("verde", 1),
    AMARILLA("amarilla", 2),
    NARANJA("naranja", 3),
    ROJA("roja", 4);

    companion object {
        fun desde(clave: String?): NivelAlerta =
            entries.firstOrNull { it.clave == clave?.trim()?.lowercase() } ?: SIN_DATO
    }
}
