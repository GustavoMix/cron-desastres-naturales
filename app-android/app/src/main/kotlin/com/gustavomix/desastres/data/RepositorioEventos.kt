package com.gustavomix.desastres.data

import com.gustavomix.desastres.core.Feed
import com.gustavomix.desastres.core.FeedParser
import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Cache
import okhttp3.OkHttpClient
import okhttp3.Request

/**
 * Trae `recientes.json` del repo del scraper.
 *
 * El scraper corre una vez por semana, así que el archivo es idéntico entre
 * corrida y corrida. La caché de OkHttp maneja el ETag sola: si no cambió, el
 * servidor contesta `304` y no se baja nada. Sobre datos semanales eso es casi
 * siempre, y en un celular con datos móviles la diferencia importa.
 */
class RepositorioEventos(
    private val cliente: OkHttpClient,
    private val url: String = URL_POR_DEFECTO,
) {
    suspend fun cargar(): Result<Feed> = withContext(Dispatchers.IO) {
        val peticion = Request.Builder().url(url).build()

        try {
            cliente.newCall(peticion).execute().use { respuesta ->
                if (!respuesta.isSuccessful) {
                    return@withContext Result.failure(
                        IOException("El servidor respondió ${respuesta.code}")
                    )
                }
                val cuerpo = respuesta.body?.string()
                    ?: return@withContext Result.failure(IOException("Respuesta vacía"))

                Result.success(FeedParser.parsear(cuerpo))
            }
        } catch (error: IOException) {
            Result.failure(error)
        } catch (error: Exception) {
            // Un feed corrupto no debe tirar la app abajo: se reporta como
            // error y la pantalla muestra el estado correspondiente.
            Result.failure(error)
        }
    }

    companion object {
        /**
         * jsDelivr en vez de `raw.githubusercontent.com`, que no es un CDN y
         * responde 429 bajo carga.
         *
         * OJO: la rama por defecto del repo del scraper es
         * `claude/scraper-cron-j5z2ny`, no `main` — fue la primera que se
         * empujó a un repo vacío. Si se renombra, hay que actualizar esto.
         */
        const val URL_POR_DEFECTO =
            "https://cdn.jsdelivr.net/gh/GustavoMix/cron-desastres-naturales@claude/scraper-cron-j5z2ny/datos/recientes.json"

        private const val TAMANO_CACHE_BYTES = 5L * 1024 * 1024

        fun crearCliente(directorioCache: File): OkHttpClient =
            OkHttpClient.Builder()
                .cache(Cache(File(directorioCache, "feed"), TAMANO_CACHE_BYTES))
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .build()
    }
}
