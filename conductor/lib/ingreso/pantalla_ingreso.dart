// Pantalla de ingreso: celular y PIN de 6 dígitos. Los errores son los textos del servidor
// (`detalle`); la app no agrega ni revela nada más (por ejemplo, si el celular existe).

import 'dart:async';

import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../comunes.dart';
import '../formato.dart';
import '../tema.dart';
import 'sesion.dart';

final _seisDigitos = RegExp(r'^\d{6}$');

/// Vacío si el PIN sirve; si no, el texto del error.
String? validarPin(String? pin) =>
    pin != null && _seisDigitos.hasMatch(pin) ? null : 'El PIN tiene 6 dígitos.';

String? validarCelular(String? celular) =>
    celular == null || celular.trim().isEmpty ? 'Escriba su número de celular.' : null;

class PantallaIngreso extends StatefulWidget {
  const PantallaIngreso({
    super.key,
    required this.sesion,
    this.servidor = servidorConfigurado,
    this.reloj = DateTime.now,
  });

  final Sesion sesion;

  /// Se muestra pequeño al final, para confirmar a qué servidor apunta la app.
  final String servidor;
  final DateTime Function() reloj;

  @override
  State<PantallaIngreso> createState() => _PantallaIngresoState();
}

class _PantallaIngresoState extends State<PantallaIngreso> {
  final _formulario = GlobalKey<FormState>();
  late final _celular = TextEditingController(text: widget.sesion.conductor?.celular ?? '');
  final _pin = TextEditingController();
  final _focoPin = FocusNode();

  bool _enviando = false;
  bool _verPin = false;
  String? _error;
  Map<String, List<String>> _erroresDeCampo = const {};
  DateTime? _bloqueadoHasta;
  Timer? _finDelBloqueo;

  bool get _bloqueado => _bloqueadoHasta != null;

  @override
  void dispose() {
    _finDelBloqueo?.cancel();
    _celular.dispose();
    _pin.dispose();
    _focoPin.dispose();
    super.dispose();
  }

  Future<void> _ingresar() async {
    if (_enviando || _bloqueado) return;
    setState(() {
      _error = null;
      _erroresDeCampo = const {};
    });
    if (!(_formulario.currentState?.validate() ?? false)) return;
    FocusScope.of(context).unfocus();
    setState(() => _enviando = true);
    try {
      // Si sale bien, la raíz de la app cambia a la lista y esta pantalla se cierra.
      await widget.sesion.ingresar(celular: _celular.text, pin: _pin.text);
    } on ErrorDeContrato catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.detalle;
        _erroresDeCampo = error.campos;
        if (error.codigo != 'datos_invalidos') _pin.clear();
        if (error.codigo == 'demasiados_intentos') {
          _bloquear(error.reintentarEn ?? const Duration(minutes: 15));
        }
      });
    } on ErrorApi catch (error) {
      if (!mounted) return;
      setState(() => _error = error.mensaje);
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  /// El servidor no revisa el PIN durante el bloqueo: el botón se apaga hasta la hora que informó.
  void _bloquear(Duration espera) {
    _bloqueadoHasta = widget.reloj().add(espera);
    _finDelBloqueo?.cancel();
    _finDelBloqueo = Timer(espera, () {
      if (mounted) setState(() => _bloqueadoHasta = null);
    });
  }

  String? _errorDeCampo(String campo) {
    final errores = _erroresDeCampo[campo];
    return errores == null || errores.isEmpty ? null : errores.join(' ');
  }

  @override
  Widget build(BuildContext context) {
    final textos = Theme.of(context).textTheme;
    final aviso = widget.sesion.aviso;
    final bloqueadoHasta = _bloqueadoHasta;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: AutofillGroup(
                child: Form(
                  key: _formulario,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text('Arribo', style: textos.headlineSmall),
                      const SizedBox(height: 8),
                      Text(
                        'Ingrese con su número de celular y el PIN de 6 dígitos que le dio logística.',
                        style: textos.bodyLarge?.copyWith(color: Colores.textoSecundario),
                      ),
                      const SizedBox(height: 24),
                      if (aviso != null) ...[
                        Recuadro(aviso, tipo: TipoRecuadro.info),
                        const SizedBox(height: 16),
                      ],
                      TextFormField(
                        key: const Key('celular'),
                        controller: _celular,
                        enabled: !_enviando,
                        forceErrorText: _errorDeCampo('celular'),
                        decoration: const InputDecoration(labelText: 'Celular'),
                        style: textos.bodyLarge,
                        keyboardType: TextInputType.phone,
                        textInputAction: TextInputAction.next,
                        autofillHints: const [AutofillHints.telephoneNumber],
                        inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9 +\-]'))],
                        validator: validarCelular,
                        onFieldSubmitted: (_) => _focoPin.requestFocus(),
                      ),
                      const SizedBox(height: 16),
                      TextFormField(
                        key: const Key('pin'),
                        controller: _pin,
                        focusNode: _focoPin,
                        forceErrorText: _errorDeCampo('pin'),
                        enabled: !_enviando,
                        decoration: InputDecoration(
                          labelText: 'PIN',
                          helperText: '6 dígitos',
                          suffixIcon: IconButton(
                            tooltip: _verPin ? 'Ocultar el PIN' : 'Mostrar el PIN',
                            icon: Icon(_verPin ? Icons.visibility_off : Icons.visibility),
                            onPressed: () => setState(() => _verPin = !_verPin),
                          ),
                        ),
                        style: textos.bodyLarge?.copyWith(letterSpacing: 4),
                        keyboardType: TextInputType.number,
                        obscureText: !_verPin,
                        enableSuggestions: false,
                        autocorrect: false,
                        textInputAction: TextInputAction.done,
                        inputFormatters: [
                          FilteringTextInputFormatter.digitsOnly,
                          LengthLimitingTextInputFormatter(6),
                        ],
                        validator: validarPin,
                        onFieldSubmitted: (_) => _ingresar(),
                      ),
                      const SizedBox(height: 24),
                      if (_error != null) ...[
                        Recuadro(_error!, tipo: TipoRecuadro.error),
                        const SizedBox(height: 16),
                      ],
                      FilledButton(
                        key: const Key('ingresar'),
                        onPressed: _enviando || _bloqueado ? null : _ingresar,
                        child: _enviando
                            ? const Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  SizedBox.square(
                                    dimension: 20,
                                    child: CircularProgressIndicator(strokeWidth: 2.5),
                                  ),
                                  SizedBox(width: 12),
                                  Flexible(child: Text('Ingresando…')),
                                ],
                              )
                            : Text(
                                bloqueadoHasta == null
                                    ? 'Ingresar'
                                    : 'Espere hasta las ${horaCorta(bloqueadoHasta)}',
                                textAlign: TextAlign.center,
                              ),
                      ),
                      const SizedBox(height: 32),
                      Text(
                        'Servidor: ${widget.servidor}',
                        style: textos.bodySmall?.copyWith(color: Colores.textoSecundario),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
