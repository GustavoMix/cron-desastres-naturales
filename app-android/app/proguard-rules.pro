# kotlinx.serialization genera serializadores por reflexión sobre las clases
# @Serializable; sin esto, R8 las renombraría y el parseo del feed fallaría
# solo en release, que es el peor momento para enterarse.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class com.gustavomix.desastres.core.** {
    *** Companion;
}
-keepclasseswithmembers class com.gustavomix.desastres.core.** {
    kotlinx.serialization.KSerializer serializer(...);
}
