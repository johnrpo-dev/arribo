package co.arribo.arribo_conductor

import android.os.Build
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        // Nombre del celular para el campo `dispositivo_nombre` del ingreso (lib/dispositivo.dart).
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "co.arribo/dispositivo")
            .setMethodCallHandler { llamada, resultado ->
                if (llamada.method == "nombre") {
                    resultado.success(nombreDelCelular())
                } else {
                    resultado.notImplemented()
                }
            }
    }

    private fun nombreDelCelular(): String {
        val fabricante = Build.MANUFACTURER.orEmpty().trim()
        val modelo = Build.MODEL.orEmpty().trim()
        val marca = fabricante.replaceFirstChar { it.uppercase() }
        return when {
            modelo.isEmpty() -> marca
            fabricante.isEmpty() || modelo.startsWith(fabricante, ignoreCase = true) -> modelo
            else -> "$marca $modelo"
        }
    }
}
