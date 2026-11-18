"""Qué exportador usa la empresa: el de `configuracion.formato_exportacion`. Cada formato de la
configuración tiene su implementación de `nucleo.exportacion.Exportador`; agregar uno es agregar la
opción en la configuración y su implementación aquí."""
from configuracion.models import FormatoExportacion, configuracion_vigente
from nucleo.exportacion import CsvGenerico, Exportador

EXPORTADORES: dict[str, Exportador] = {
    FormatoExportacion.CSV_GENERICO.value: CsvGenerico(),
}


def exportador_configurado() -> Exportador:
    return EXPORTADORES[configuracion_vigente().formato_exportacion]
