// Tareas asíncronas que no se deben cruzar: van una tras otra, en el orden en que se pidieron.

import 'dart:async';

class Fila {
  Future<void>? _ultima;

  /// Ejecuta [tarea] cuando terminen las que se pidieron antes (fallen o no) y devuelve su
  /// resultado. Con la fila vacía, empieza de inmediato.
  Future<T> ejecutar<T>(Future<T> Function() tarea) async {
    final anterior = _ultima;
    final fin = Completer<void>();
    _ultima = fin.future;
    try {
      if (anterior != null) await anterior;
      return await tarea();
    } finally {
      // Con la fila vacía no se guarda nada: la siguiente tarea no espera un Future ya terminado.
      if (identical(_ultima, fin.future)) _ultima = null;
      fin.complete();
    }
  }
}
