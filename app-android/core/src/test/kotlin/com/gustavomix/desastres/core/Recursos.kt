package com.gustavomix.desastres.core

/** Lee un archivo de `src/test/resources`. */
internal fun recursoDePrueba(ruta: String): String =
    checkNotNull(object {}.javaClass.getResourceAsStream(ruta)) { "falta el recurso $ruta" }
        .bufferedReader()
        .use { it.readText() }
