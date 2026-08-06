package com.gustavomix.desastres.core

import java.time.Duration
import java.time.Instant

/**
 * Qué tan viejos son los datos que la app está por mostrar.
 *
 * En una app de desastres esto no es un detalle de UI: mostrar información
 * vieja como si fuera actual es peor que no mostrar nada. La app **tiene** que
 * avisarlo, y por eso vive en :core con tests, no en la pantalla.
 */
sealed interface Frescura {
    /** Dentro de lo esperable para la cadencia del scraper. */
    data class Fresca(val antiguedad: Duration) : Frescura

    /** Se pasó de la ventana: probablemente se salteó una corrida. */
    data class Vieja(val antiguedad: Duration) : Frescura

    /** Hace tanto que hay que asumir que el scraper está caído. */
    data class Critica(val antiguedad: Duration) : Frescura

    /** El feed no trae marca de generación, o es ilegible. */
    data object Desconocida : Frescura

    /** `true` cuando la app debe mostrar la advertencia al usuario. */
    val requiereAviso: Boolean
        get() = this !is Fresca
}

/**
 * Evalúa la frescura del feed.
 *
 * Los umbrales por defecto están atados a la cadencia del cron, que hoy es
 * **semanal** (lunes 06:17 UTC). Si el scraper cambia de cadencia hay que
 * moverlos: con umbrales de horas sobre datos semanales el aviso estaría
 * encendido siempre, y un aviso permanente es uno que la gente aprende a
 * ignorar — peor que no tenerlo.
 *
 * El margen de un día sobre el intervalo evita gritar por una corrida apenas
 * demorada; GitHub Actions rutinariamente atrasa los cron programados.
 */
class EvaluadorDeFrescura(
    private val umbralViejo: Duration = Duration.ofDays(8),
    private val umbralCritico: Duration = Duration.ofDays(15),
) {
    init {
        require(umbralViejo < umbralCritico) {
            "umbralViejo ($umbralViejo) debe ser menor que umbralCritico ($umbralCritico)"
        }
    }

    fun evaluar(feed: Feed, ahora: Instant): Frescura = evaluar(feed.generadoEn, ahora)

    fun evaluar(generado: Instant?, ahora: Instant): Frescura {
        if (generado == null) return Frescura.Desconocida

        // Una marca en el futuro significa relojes desfasados, no datos frescos
        // del futuro. Se trata como recién generado en vez de como negativo.
        val antiguedad = Duration.between(generado, ahora).coerceAtLeast(Duration.ZERO)

        return when {
            antiguedad >= umbralCritico -> Frescura.Critica(antiguedad)
            antiguedad >= umbralViejo -> Frescura.Vieja(antiguedad)
            else -> Frescura.Fresca(antiguedad)
        }
    }
}
