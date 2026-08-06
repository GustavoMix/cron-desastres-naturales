rootProject.name = "desastres-naturales"

pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}

// :core es Kotlin/JVM puro a propósito — sin nada de Android. Ahí vive toda la
// lógica que puede fallar (parseo del feed, filtros, frescura) y por eso se
// testea sin emulador ni SDK. :app solo pinta lo que :core decide.
include(":core")
include(":app")
