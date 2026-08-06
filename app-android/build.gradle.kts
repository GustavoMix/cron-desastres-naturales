// Sin bloque `plugins` a propósito.
//
// Declarar acá el plugin de Android (aunque sea con `apply false`) obliga a
// Gradle a resolverlo en TODA invocación, incluida `./gradlew :core:test`. Eso
// ataría los tests de :core al SDK de Android y a que `dl.google.com` sea
// alcanzable — justo lo que la separación en módulos busca evitar.
//
// Cada módulo declara sus propios plugins, y `org.gradle.configureondemand`
// (ver gradle.properties) hace que :core se pueda testear sin configurar :app.
