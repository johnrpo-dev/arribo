# Propuesta: orden de facturación

Estado: **propuesta, sin aprobar.** No se construye hasta que el dueño la apruebe y responda las
preguntas de `QUESTIONS.md` (sección "Orden de facturación"). Tarea: 1a-19b en
`docs/fase-1a-tareas.md`.

## El problema

Hoy el facturador ve los cobros en Arribo, hace la factura a mano en el programa de facturación y
escribe el número en Arribo. Si copia mal un valor, una placa o el NIT, nadie se entera hasta que
reclama el cliente. Arribo ya tiene todos esos datos y el total correcto.

## Qué se propone

Una **orden de facturación**: un documento interno que Arribo arma con los datos exactos para que el
facturador los pase a su programa, y una verificación al registrar la factura que detecta los
errores de digitación.

No se llama "Factura" a propósito. La factura válida es la electrónica del programa de facturación,
con su consecutivo autorizado por la DIAN. Arribo no numera facturas ni las emite (la factura
electrónica está fuera de alcance en `CLAUDE.md`); si lo hiciera, habría dos numeraciones.

### Parte A: la orden y la verificación (sirve con cualquier programa)

1. **Emitir la orden.** Desde una relación de cobro (varios servicios de un pagador) o desde una
   línea suelta por facturar. La orden lleva:
   - consecutivo propio de Arribo (`OF-0001`), que solo identifica la orden y no es un número de
     factura;
   - pagador: nombre o razón social y NIT, y los demás datos de facturación que se definan;
   - un renglón por servicio: tipo, fecha, placa o VIN, vehículo, origen y destino, número de caso
     y valor;
   - subtotal, impuestos según la regla que se defina, y total. Todo en `Decimal` y calculado por
     Arribo.
2. **Queda congelada.** Mientras la orden está emitida, sus líneas no cambian de valor ni entran en
   otra orden o relación. Cambiar algo exige anular la orden con motivo. Igual que una relación
   armada hoy.
3. **El facturador la ve.** Una pestaña "Órdenes por facturar" en Cobros. Cada dato tiene un botón
   para copiarlo y así evitar volver a escribirlo. La orden se imprime en PDF desde el navegador
   (sin dependencia nueva) si el facturador es alguien de afuera.
4. **Registrar la factura con verificación.** El facturador escribe el número **y el total** de la
   factura que hizo en su programa:
   - si el total no coincide con el de la orden, Arribo no la registra y muestra la diferencia;
   - si ese número de factura ya está registrado en otra orden o línea, Arribo no la registra y
     dice dónde está.

   Si todo cuadra, todas las líneas de la orden quedan facturadas con ese número, con su historial,
   igual que al facturar una relación hoy.
5. **Anular.** Una orden emitida se anula con motivo y sus líneas vuelven a por facturar. Una ya
   facturada se corrige anulando la factura, como hoy.

Reglas que irían a `nucleo/` con sus pruebas: el total de la orden, la verificación del total
digitado, el número de factura repetido y los estados de la orden (emitida → facturada, o anulada).

### Parte B: archivo para el programa de facturación (después)

Si el programa de facturación permite importar los renglones desde un Excel, Arribo genera ese
archivo en el formato exacto del programa, como otro exportador junto al CSV de las relaciones
(ya previsto en `docs/arquitectura.md`: "adaptadores después"). Así el facturador no copia nada a
mano. Depende de saber qué programa usan y de tener un archivo de ejemplo de su plantilla de
importación. No es una integración por API, que sigue fuera de alcance.

## Lo que no hace

- No emite factura electrónica ni la envía a la DIAN.
- No manda correos ni WhatsApp: la orden se ve en Arribo o se imprime.
- No cambia cómo se fija el valor ni el flujo de cobro por línea.

## Cómo lo verificaría el dueño (cuando esté hecha)

1. Armar una relación de un cliente con tres servicios y emitir la orden: los datos coinciden con
   los servicios y el total es la suma.
2. Registrar la factura con un total distinto: Arribo no deja y muestra la diferencia.
3. Registrarla con un número ya usado: Arribo no deja y dice dónde está.
4. Registrarla bien: las tres líneas quedan facturadas con ese número.
