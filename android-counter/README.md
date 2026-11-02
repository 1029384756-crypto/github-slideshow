# Contador

App Android minimalista para contar (asistentes a conciertos, etc.): fondo blanco, un botón rojo circular al centro que suma 1 por toque, y un botón Reset.

- El conteo se guarda, así que no se pierde si cierras la app.
- La pantalla se mantiene encendida mientras la usas.
- Reset pide confirmación para evitar borrar el conteo por error.

## Compilar
Abrir la carpeta `android-counter` en Android Studio y ejecutar, o `gradle assembleDebug`.
El workflow de GitHub Actions `Build Android APK` genera `app-debug.apk` como artefacto descargable.
