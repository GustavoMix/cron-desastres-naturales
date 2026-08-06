package com.gustavomix.desastres.ui

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext

/**
 * Tema de la app.
 *
 * Los colores de nivel de alerta **no** salen de acá: viven en [EstiloAlerta] y
 * son fijos a propósito. Son colores de estado, no de marca, y no deben cambiar
 * con el tema dinámico del sistema — un rojo de alerta que se vuelve pastel
 * porque el fondo de pantalla del usuario es rosa deja de comunicar peligro.
 */
@Composable
fun TemaDesastres(
    oscuro: Boolean = isSystemInDarkTheme(),
    contenido: @Composable () -> Unit,
) {
    val contexto = LocalContext.current
    val esquema = when {
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.S ->
            if (oscuro) dynamicDarkColorScheme(contexto) else dynamicLightColorScheme(contexto)
        oscuro -> darkColorScheme()
        else -> lightColorScheme()
    }

    MaterialTheme(colorScheme = esquema, content = contenido)
}
